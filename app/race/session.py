"""Composition root: wires the CU client, race engine, fuel/tyre model,
weather, overtake, safety car, reliability, strategy, recorder/ghost, and
player controllers into one running loop. This is the "glue" layer --
app/race/engine.py etc. stay pure and hardware-free; this is where
hardware/timing reality meets them.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable

from app.controllers.base import InputController
from app.cu.base import CUClient, UnsupportedCommand
from app.race.engine import RaceEngine, RaceEngineConfig
from app.race.forecast import WeatherForecast
from app.race.fuel import FuelModel, weather_match_multiplier
from app.race.ghost import GhostComparator
from app.race.models import RaceMode, RaceState
from app.race.overtake import OvertakeSystem
from app.race.pace_car import PaceCarPlayback
from app.race.recorder import EventType, InputRecorder
from app.race.reliability import ReliabilitySystem
from app.race.safety_car import SafetyCarSystem
from app.race.strategy import RaceStrategy, StrategyBook
from app.race.weather import WeatherMode

MAX_SPEED = 15
EARLY_MOVEMENT_THRESHOLD = 0.05


@dataclass
class SessionConfig:
    addresses: list[int] = field(default_factory=lambda: list(range(6)))
    mode: RaceMode = RaceMode.RACE
    engine_config: RaceEngineConfig = field(default_factory=RaceEngineConfig)
    safety_car_physically_present: bool = False


class RaceSession:
    def __init__(self, cu: CUClient, config: SessionConfig | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None):
        self.cu = cu
        self.config = config or SessionConfig()
        self.clock = clock
        self._rng = rng or random.Random()
        self.engine = RaceEngine(self.config.addresses, self.config.mode, self.config.engine_config)
        self.fuel = FuelModel(self.config.addresses)
        self.weather = WeatherMode()
        self.overtake = OvertakeSystem()
        self.safety_car = SafetyCarSystem(physically_present=self.config.safety_car_physically_present)
        self.reliability = ReliabilitySystem()
        self.forecast: WeatherForecast | None = None
        self.strategy_book = StrategyBook()
        self.recorder = InputRecorder()
        self.ghosts: dict[int, GhostComparator] = {}
        self.controllers: dict[int, InputController] = {}
        self.pace_playback: PaceCarPlayback | None = None
        self._pace_start_time: float | None = None
        self.debug_log: list[str] = []
        self.events: list[dict] = []
        self.last_input: dict[int, tuple[float, float]] = {}  # address -> (throttle, brake)
        self.start_phase: str | None = None  # "ARMED" | "L1".."L5" | "GO" | None
        self._last_tick: float | None = None
        self._final_lap_announced = False
        self._race_won_announced = False

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

    def apply_strategy(self, strategy: RaceStrategy) -> None:
        """Meant to be called pre-race: sets the car's starting fuel load
        and tyre compound to match the plan. Calling it mid-race will
        reset fuel/tyres to the plan's values, which is only useful for
        setup/testing, not a real mid-race feature."""
        self.strategy_book.set(strategy)
        self.fuel.set_starting_load(strategy.address, strategy.fuel_load)
        self.fuel.set_compound(strategy.address, strategy.compound)

    def set_forecast(self, forecast: WeatherForecast | None) -> None:
        self.forecast = forecast

    def set_ghost(self, address: int, recording_name: str) -> None:
        recording = self.recorder.load(recording_name)
        self.ghosts[address] = GhostComparator(recording)

    def clear_ghost(self, address: int) -> None:
        self.ghosts.pop(address, None)

    def set_in_pit(self, address: int, in_pit: bool) -> None:
        car = self.engine.cars.get(address)
        if car is None:
            return
        was_in_pit = car.in_pit
        car.in_pit = in_pit
        if in_pit and not was_in_pit:
            self.fuel.change_tyres(address)
            self.events.append({"type": "tyre_change", "address": address})

    def set_start_phase(self, phase: str | None) -> None:
        self.start_phase = phase

    def begin_countdown(self) -> None:
        self._final_lap_announced = False
        self._race_won_announced = False
        self.start_phase = None
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

    def _maybe_announce_final_lap(self, address: int, lap_number: int) -> None:
        target = self.engine.config.target_laps
        if target is None or target < 2 or self._final_lap_announced:
            return
        if lap_number == target - 1:
            self._final_lap_announced = True
            self.events.append({"type": "final_lap", "address": address})

    def tick(self) -> None:
        now = self.clock()
        dt = 0.0 if self._last_tick is None else max(0.0, now - self._last_tick)
        self._last_tick = now
        self.events = []

        for event in self.cu.poll_timer():
            record = self.engine.handle_timer_event(event.address, event.timestamp, event.sector)
            if record is not None:
                record.fuel_at_lap = self.fuel.fuel(event.address)
                record.tyre_wear_at_lap = self.fuel.tyre_wear(event.address)
                if self.recorder.is_recording(event.address):
                    self.recorder.record(event.address, EventType.LAP, float(record.lap_number), now)
                self._maybe_announce_final_lap(event.address, record.lap_number)
                self.safety_car.maybe_random_trigger(rng=self._rng)

        if self.forecast is not None:
            leader_lap = max((c.lap_count for c in self.engine.cars.values()), default=0)
            new_level = self.forecast.advance(leader_lap)
            if new_level is not None:
                self.weather.set_level(new_level)
                self.events.append({"type": "weather_change", "level": new_level.value})

        if self.engine.state == RaceState.FINISHED and not self._race_won_announced:
            self._race_won_announced = True
            ranking = self.engine.rankings()
            if ranking:
                self.events.append({"type": "race_won", "address": ranking[0].address, "name": ranking[0].name})

        for address, controller in list(self.controllers.items()):
            car = self.engine.cars.get(address)
            if car is None:
                continue
            inp = controller.poll()
            self.last_input[address] = (inp.throttle, inp.brake)

            if self.engine.state == RaceState.COUNTDOWN and inp.throttle > EARLY_MOVEMENT_THRESHOLD:
                self.engine.report_early_movement(address, now)

            if self.reliability.is_broken_down(address):
                if self.reliability.tick_repair(address, car.in_pit, dt):
                    self.events.append({"type": "repair_complete", "address": address})

            if self.engine.state != RaceState.RUNNING:
                continue

            if inp.stop_pressed:
                self.stop(triggered_by=address)
                continue

            if inp.overtake_pressed and self.overtake.trigger(address, now):
                self.events.append({"type": "overtake_activated", "address": address})
            boosting = self.overtake.is_active(address, now)

            broken_down = self.reliability.is_broken_down(address)
            if not broken_down and self.reliability.maybe_break_down(address, dt, rng=self._rng):
                broken_down = True
                self.events.append({"type": "breakdown", "address": address})

            if broken_down:
                effective_speed = 0
                effective_brake_units = 0
            else:
                match_mult = weather_match_multiplier(self.fuel.compound(address), self.weather.level)
                if boosting:
                    multiplier = self.overtake.config.boost_multiplier * match_mult
                else:
                    multiplier = (self.fuel.weight_penalty_multiplier(address)
                                  * self.fuel.tyre_performance_multiplier(address)
                                  * match_mult)
                requested = inp.throttle * MAX_SPEED * multiplier
                capped = self.weather.cap_speed(round(requested))
                effective_speed = self.safety_car.cap_speed(capped)

                brake_effectiveness = self.fuel.brake_effectiveness_multiplier(address) * match_mult
                effective_brake_units = round(inp.brake * MAX_SPEED * brake_effectiveness)

            try:
                self.cu.set_speed(address, effective_speed)
            except UnsupportedCommand as exc:
                self._log(f"set_speed rejected for address={address}: {exc}")

            try:
                self.cu.set_brake(address, effective_brake_units)
            except UnsupportedCommand as exc:
                self._log(f"set_brake rejected for address={address}: {exc}")

            if not broken_down:
                self.fuel.update(address, inp.throttle, inp.brake, dt, boosting=boosting)
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

    def ghost_delta(self, address: int) -> float | None:
        ghost = self.ghosts.get(address)
        car = self.engine.cars.get(address)
        if ghost is None or car is None or not car.laps:
            return None
        last_lap = car.laps[-1]
        elapsed = sum(lap.lap_time for lap in car.laps)
        return ghost.delta_at_lap(last_lap.lap_number, elapsed)
