"""Simulated CU for development/testing without real Carrera hardware.

Cars loop a virtual track; lap duration scales inversely with the last
commanded speed (0..15). Time is driven explicitly via `tick(now)` rather
than a hidden background clock, so the simulation is deterministic and
trivially unit-testable.
"""
from __future__ import annotations

import time
from typing import Callable

from app.cu.base import CUClient
from app.cu.protocol import (
    START_ENTER_BUTTON_ID,
    START_RACING,
    START_STOPPED,
    Status,
    TimerEvent,
)

REFERENCE_SPEED = 10
DEFAULT_SPEED = 10


class MockCUClient(CUClient):
    def __init__(self, addresses: list[int], base_lap_time: float = 5.0,
                 clock: Callable[[], float] = time.monotonic):
        self.addresses = list(addresses)
        self.base_lap_time = base_lap_time
        self.clock = clock
        self._speed: dict[int, int] = {a: DEFAULT_SPEED for a in addresses}
        self._brake: dict[int, int] = {a: 0 for a in addresses}
        self._fuel: dict[int, int] = {a: 15 for a in addresses}
        self._fuel_override: dict[int, int] = {}
        self._pit: dict[int, bool] = {a: False for a in addresses}
        self._next_crossing: dict[int, float] = {}
        self._now = 0.0
        self._connected = False
        self.start_call_count = 0  # lets tests confirm the CU's start/pause is actually commanded
        # Mock begins "stopped" -- matches the real CU's likely power-on
        # state. See protocol.py's START_LABELS for the confirmed meaning
        # of these values; the mock only simulates the two endpoints (0
        # racing / 1 stopped), skipping the real 2..7 light-sequence
        # animation since its exact timing doesn't matter for testing the
        # UI wiring against a mock.
        self._start_value = START_STOPPED
        self._mode = 0
        self._ignore_mask = 0
        self.last_button_pressed: int | None = None
        self.press_count = 0

    def describe(self) -> str:
        return "MOCK (simulated CU -- no real hardware connected)"

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def _lap_duration(self, address: int) -> float:
        speed = max(1, self._speed[address])
        return self.base_lap_time * (REFERENCE_SPEED / speed)

    def arm(self, now: float) -> None:
        """Schedule each car's first crossing relative to `now` (call when
        the race goes green)."""
        self._now = now
        for a in self.addresses:
            self._next_crossing[a] = now + self._lap_duration(a)

    def tick(self, now: float) -> list[TimerEvent]:
        self._now = now
        events: list[TimerEvent] = []
        for a in self.addresses:
            next_t = self._next_crossing.get(a)
            if next_t is None:
                continue
            while next_t <= now:
                events.append(TimerEvent(address=a, timestamp=next_t, sector=0))
                next_t += self._lap_duration(a)
            self._next_crossing[a] = next_t
        return events

    def set_pit(self, address: int, in_pit: bool) -> None:
        self._pit[address] = in_pit

    # -- CUClient interface -------------------------------------------------

    def read_status(self) -> Status:
        fuel = tuple(self._fuel_override.get(a, self._fuel[a]) for a in self.addresses)
        pit = tuple(self._pit[a] for a in self.addresses)
        return Status(fuel=fuel, pit=pit, start=self._start_value, mode=self._mode,
                       display=len(self.addresses))

    def poll_timer(self) -> list[TimerEvent]:
        return self.tick(self.clock())

    def set_speed(self, address: int, value: int) -> None:
        self._speed[address] = max(0, min(15, value))

    def set_brake(self, address: int, value: int) -> None:
        self._brake[address] = max(0, min(15, value))

    def set_fuel_display(self, address: int, value: int) -> None:
        self._fuel_override[address] = max(0, min(15, value))

    def press(self, button_id: int) -> None:
        self.press_count += 1
        self.last_button_pressed = button_id
        if button_id == START_ENTER_BUTTON_ID:
            self.start_call_count += 1
            if self._start_value == START_RACING:
                self._start_value = START_STOPPED
                self._next_crossing.clear()
            else:
                self._start_value = START_RACING
                self.arm(self.clock())
        # Other buttons (PACE_CAR_ESC/SPEED/BRAKE/FUEL/CODE) have nothing
        # local to simulate -- only real hardware has a physical response
        # to observe for those.

    def ignore(self, mask: int) -> None:
        self._ignore_mask = mask

    def reset(self) -> None:
        pass

    def set_position(self, address: int, position: int) -> None:
        pass

    def set_lap(self, value: int) -> None:
        pass

    def clear_position(self) -> None:
        pass

    def version(self) -> str:
        return "mock-1.0"
