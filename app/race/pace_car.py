"""Replays a recorded throttle session as speed commands to the pace-car /
autonomous-car address, optionally scaled faster or slower than the
original lap -- this is the "variable-speed pace car" / ghost car feature.

The actual CU write happens through a caller-supplied `send_speed(address,
value)` callable so this module has no hardware dependency and is unit
testable: you can capture calls into a list and assert on their timing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.race.models import PACE_CAR_ADDRESS
from app.race.recorder import EventType, Recording

SpeedSender = Callable[[int, int], None]

MAX_SPEED = 15
MIN_COMMAND_INTERVAL = 0.075  # CU rate limit, ~75ms between speed updates


@dataclass
class PaceCarPlayback:
    recording: Recording
    address: int = PACE_CAR_ADDRESS
    speed_scale: float = 1.0  # >1 = faster pace car, <1 = slower
    loop: bool = False

    def __post_init__(self) -> None:
        self._throttle_events = [e for e in self.recording.events if e.type == EventType.THROTTLE]
        self._cursor = 0
        self._last_sent_at = -1.0
        self.finished = not self._throttle_events

    def _scaled_time(self, event_t: float) -> float:
        return event_t / self.speed_scale if self.speed_scale else event_t

    def tick(self, elapsed: float, send: SpeedSender) -> None:
        """Call repeatedly (e.g. every server tick) with elapsed seconds since
        playback started. Sends at most one command per MIN_COMMAND_INTERVAL.
        """
        if self.finished or not self._throttle_events:
            return
        if elapsed - self._last_sent_at < MIN_COMMAND_INTERVAL:
            return

        while (self._cursor < len(self._throttle_events) - 1
               and self._scaled_time(self._throttle_events[self._cursor + 1].t) <= elapsed):
            self._cursor += 1

        event = self._throttle_events[self._cursor]
        speed = round(max(0.0, min(1.0, event.value)) * MAX_SPEED)
        send(self.address, speed)
        self._last_sent_at = elapsed

        if self._scaled_time(self._throttle_events[-1].t) <= elapsed:
            if self.loop:
                self._cursor = 0
                self._last_sent_at = -1.0
            else:
                self.finished = True
