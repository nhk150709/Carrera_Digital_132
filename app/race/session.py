"""Composition root: wires the CU client, race engine, fuel model, weather,
recorder, and player controllers into one running loop. This is the
"glue" layer -- app/race/engine.py etc. stay pure and hardware-free;
this is where hardware/timing reality meets them.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from app.controllers.base import InputController
from app.cu.base import CUClient, UnsupportedCommand
from app.race.engine import RaceEngine, RaceEngineConfig
from app.race.fuel import FuelModel
from app.race.models import PACE_CAR_ADDRESS, RaceMode, RaceState
from app.race.pace_car import PaceCarPlayback
from app.race.penalties import PenaltyEngine
from app.race.recorder import EventType, InputRecorder
from app.race.weather import WeatherMode

MAX_SPEED = 15
EARLY_MOVEMENT_THRESHOLD = 0.05


@dataclass
class SessionConfig:
    addresses: list[int] = field(default_factory=lambda: list(range(6)))
    mode: RaceMode = RaceMode.RACE
    engine_config: RaceEngineConfig = field(default_factory=RaceEngineConfig)


class RaceSession:
    def __init__(self, cu: CUClient, config: SessionConfig | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.cu = cu
        self.config = config or SessionConfig()
        self.clock = clock
        self.engine = RaceEngine(self.config.addresses, self.config.mode, self.config.engine_config)
        self.fuel = FuelModel(self.config.addresses)
        self.weather = WeatherMode()
        self.recorder = InputRecorder()
        self.controllers: dict[int, InputController] = {}
        self.pace_playback: PaceCarPlayback | None = None
        self._pace_start_time: float | None = None
        self.debug_log: list[str] = []
        self._last_tick: float | None = None
        self.last_input: dict[int, tuple[float, float]] = {}  # address -> (throttle, brake)

    def _log(self, message: str) -> None:
        self.debug_log.append(f"{self.clock():.2f} {message}")
        if len(self.debug_log) > 1000:
            self.debug_log = self.debug_log[-1000:]

    def assign_controller(self, address: int, controller: InputController) -> None:
        self.controllers[address] = controller
        self.engine.assign(address, controller_id=controller.controller_id)

    def unassign_controller(self, address: int) -> None:
        self.controllers.pop(address, None)
        self.engine.assign(address, controller_id=None)

    def begin_countdown(self) -> None:
        self.engine.begin_countdown(self.clock())

    def go(self) -> None:
        now = self.clock()
        self.engine.go(now)
        self.cu.start()

    def stop(self, triggered_by: int | None = None, penalize_trigger: bool = False) -> None:
        self.engine.stop(self.clock(), triggered_by=triggered_by, penalize_trigger=penalize_trigger)

    def resume(self) -> None:
        self.engine.resume(self.clock())

    def start_pace_car(self, playback: PaceCarPlayback) -> None:
        self.pace_playback = playback
        self._pace_start_time = self.clock()

    def stop_pace_car(self) -> None:
        self.pace_playback = None
        self._pace_start_time = None

    def tick(self) -> None:
        now = self.clock()
        dt = 0.0 if self._last_tick is None else max(0.0, now - self._last_tick)
        self._last_tick = now

        for event in self.cu.poll_timer():
            self.engine.handle_timer_event(event.address, event.timestamp, event.sector)

        for address, controller in list(self.controllers.items()):
            car = self.engine.cars.get(address)
            if car is None:
                continue
            inp = controller.poll()
            self.last_input[address] = (inp.throttle, inp.brake)

            if self.engine.state == RaceState.COUNTDOWN and inp.throttle > EARLY_MOVEMENT_THRESHOLD:
                self.engine.report_early_movement(address, now)

            if self.engine.state == RaceState.RUNNING:
                if inp.stop_pressed:
                    self.stop(triggered_by=address)
                    continue
                requested = round(inp.throttle * MAX_SPEED)
                capped = self.weather.cap_speed(requested)
                try:
                    self.cu.set_speed(address, capped)
                except UnsupportedCommand as exc:
                    self._log(f"set_speed rejected for address={address}: {exc}")

                self.fuel.update(address, inp.throttle, inp.brake, dt,
                                   in_pit=car.in_pit)
                car.fuel = self.fuel.fuel(address)
                car.tyre_wear = self.fuel.tyre_wear(address)
                try:
                    self.cu.set_fuel_display(address, round(car.fuel / 100 * 15))
                except UnsupportedCommand as exc:
                    self._log(f"set_fuel_display rejected for address={address}: {exc}")

                if self.recorder.is_recording(address):
                    self.recorder.record(address, EventType.THROTTLE, inp.throttle, now)
                    if inp.brake > 0:
                        self.recorder.record(address, EventType.BRAKE, inp.brake, now)
                    if inp.lane_change:
                        self.recorder.record(address, EventType.LANE_CHANGE, 1.0, now)

        if self.pace_playback is not None and self._pace_start_time is not None:
            elapsed = now - self._pace_start_time
            self.pace_playback.tick(elapsed, self._send_pace_speed)
            if self.pace_playback.finished and not self.pace_playback.loop:
                self.stop_pace_car()

    def _send_pace_speed(self, address: int, value: int) -> None:
        try:
            self.cu.set_speed(address, value)
        except UnsupportedCommand as exc:
            self._log(f"pace car set_speed rejected: {exc}")
