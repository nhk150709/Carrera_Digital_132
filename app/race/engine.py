"""Core race engine: state machine, lap tracking, ranking, delta time,
penalties, jump-start flagging.

Deliberately has no knowledge of the CU, controllers, or the network layer
-- it only reacts to explicit calls (handle_timer_event, report_early_
movement, stop/start/etc.), which makes it fully unit-testable without any
hardware or web framework. app/race/session.py wires this up to the real
world.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.race.models import CarState, LapRecord, RaceMode, RaceState, RankingEntry
from app.race.penalties import PenaltyEngine


@dataclass
class RaceEngineConfig:
    target_laps: int | None = None
    stop_on_leader_finish: bool = True


class RaceEngine:
    def __init__(self, addresses: list[int], mode: RaceMode = RaceMode.RACE,
                 config: RaceEngineConfig | None = None):
        self.mode = mode
        self.config = config or RaceEngineConfig()
        self.state = RaceState.IDLE
        self.cars: dict[int, CarState] = {a: CarState(address=a) for a in addresses}
        self.penalty_engine = PenaltyEngine()
        self.go_timestamp: float | None = None
        self.finish_order: list[int] = []
        self.log: list[str] = []

    def _emit(self, message: str) -> None:
        self.log.append(message)
        if len(self.log) > 500:
            self.log = self.log[-500:]

    def assign(self, address: int, name: str = "", controller_id: str | None = None) -> None:
        car = self.cars[address]
        if name:
            car.name = name
        if controller_id is not None:
            car.controller_id = controller_id
        self._emit(f"assigned address={address} name={car.name!r} controller={car.controller_id!r}")

    def reset(self, now: float) -> None:
        for car in self.cars.values():
            car.laps.clear()
            car.penalties.clear()
            car.jump_start = False
            car.last_crossing_timestamp = None
        self.state = RaceState.IDLE
        self.go_timestamp = None
        self.finish_order.clear()
        self._emit("race reset")

    def begin_countdown(self, now: float) -> None:
        self.state = RaceState.COUNTDOWN
        self._emit(f"countdown armed at t={now:.2f}")

    def go(self, now: float) -> None:
        self.state = RaceState.RUNNING
        self.go_timestamp = now
        for car in self.cars.values():
            car.last_crossing_timestamp = now
        self._emit(f"race started at t={now:.2f}")

    def report_early_movement(self, address: int, now: float) -> None:
        """A car moved before the green light. Only meaningful during the
        countdown; ignored otherwise since driving mid-race isn't a jump
        start. See docs/reference/protocol-notes.md for how this signal
        can actually be sourced (CU live-throttle telemetry for addresses
        0-5 is unconfirmed -- this is fed either from a locally-attached
        controller's raw input, or a dedicated Arduino start-line sensor).
        """
        if self.state != RaceState.COUNTDOWN:
            return
        car = self.cars.get(address)
        if car is None or car.jump_start:
            return
        self.penalty_engine.jump_start(car, now)
        self._emit(f"jump start detected: address={address}")

    def stop(self, now: float, triggered_by: int | None = None, penalize_trigger: bool = False,
              reason: str = "manual") -> None:
        if self.state not in (RaceState.RUNNING, RaceState.COUNTDOWN):
            return
        self.state = RaceState.PAUSED
        self._emit(f"race stopped ({reason}) at t={now:.2f} by address={triggered_by}")
        if penalize_trigger and triggered_by is not None and triggered_by in self.cars:
            self.penalty_engine.race_stopped_by(self.cars[triggered_by], now)
            self._emit(f"penalty applied to address={triggered_by} for triggering stop")

    def resume(self, now: float) -> None:
        if self.state != RaceState.PAUSED:
            return
        self.state = RaceState.RUNNING
        # Re-baseline crossing timestamps so the paused duration isn't
        # counted as part of anyone's next lap time.
        for car in self.cars.values():
            car.last_crossing_timestamp = now
        self._emit(f"race resumed at t={now:.2f}")

    def finish(self, now: float) -> None:
        self.state = RaceState.FINISHED
        self._emit(f"race finished at t={now:.2f}")

    def add_penalty(self, address: int, seconds: float, reason: str, now: float) -> None:
        car = self.cars.get(address)
        if car is None:
            return
        self.penalty_engine.custom(car, seconds, reason, now)
        self._emit(f"penalty {seconds}s applied to address={address} ({reason})")

    def handle_timer_event(self, address: int, timestamp: float, sector: int = 0) -> LapRecord | None:
        """Feed in a Timer message (address, timestamp, sector) from the CU
        (or the mock CU). sector == 0 is treated as a start/finish crossing
        (a full lap); nonzero sectors are recorded but don't complete a lap.

        `go()` seeds every car's crossing baseline at the green light, so
        the first sector-0 crossing after go() is lap 1, timed from the
        start -- there's no separate "baseline" event to send.
        """
        car = self.cars.get(address)
        if car is None or self.state != RaceState.RUNNING:
            return None
        if car.last_crossing_timestamp is None:
            # Defensive fallback: shouldn't happen since go() seeds this,
            # but avoids a bogus huge lap time if it's ever missed.
            car.last_crossing_timestamp = timestamp
            return None
        if sector != 0:
            # Sector split (e.g. a Check Lane) -- not a lap completion.
            return None

        lap_time = timestamp - car.last_crossing_timestamp
        car.last_crossing_timestamp = timestamp
        record = LapRecord(lap_number=car.lap_count + 1, lap_time=lap_time, timestamp=timestamp, sector=sector)
        car.laps.append(record)
        self._emit(f"lap: address={address} lap={record.lap_number} time={lap_time:.3f}s")

        self._maybe_finish(address, timestamp)
        return record

    def _maybe_finish(self, address: int, now: float) -> None:
        target = self.config.target_laps
        if target is None:
            return
        car = self.cars[address]
        if car.lap_count >= target and address not in self.finish_order:
            self.finish_order.append(address)
            self._emit(f"address={address} reached target laps ({target})")
            if self.config.stop_on_leader_finish and len(self.finish_order) == 1:
                self.finish(now)

    def _session_best_lap(self) -> float | None:
        best = None
        for car in self.cars.values():
            b = car.best_lap
            if b is not None and (best is None or b < best):
                best = b
        return best

    def rankings(self) -> list[RankingEntry]:
        cars = list(self.cars.values())
        session_best = self._session_best_lap()

        if self.mode == RaceMode.TIME_ATTACK:
            ranked = sorted(
                cars,
                key=lambda c: (c.best_lap is None, c.best_lap if c.best_lap is not None else float("inf")),
            )
            leader_best = ranked[0].best_lap if ranked and ranked[0].best_lap is not None else None
            entries = []
            for i, car in enumerate(ranked):
                last_lap = car.laps[-1].lap_time if car.laps else None
                gap = (car.best_lap - leader_best) if (car.best_lap is not None and leader_best is not None) else None
                delta = (last_lap - session_best) if (last_lap is not None and session_best is not None) else None
                entries.append(RankingEntry(
                    address=car.address, name=car.name, position=i + 1, lap_count=car.lap_count,
                    laps_down=0, best_lap=car.best_lap, last_lap=last_lap, gap_to_leader=gap,
                    delta_vs_best=delta, penalty_seconds=car.total_penalty_seconds, fuel=car.fuel,
                    jump_start=car.jump_start,
                ))
            return entries

        # RACE mode: most laps first, then least elapsed (race) time.
        ranked = sorted(cars, key=lambda c: (-c.lap_count, c.elapsed_time))
        leader = ranked[0] if ranked else None
        entries = []
        for i, car in enumerate(ranked):
            last_lap = car.laps[-1].lap_time if car.laps else None
            laps_down = (leader.lap_count - car.lap_count) if leader else 0
            gap = (car.elapsed_time - leader.elapsed_time) if (leader and laps_down == 0 and car is not leader) else None
            delta = (last_lap - session_best) if (last_lap is not None and session_best is not None) else None
            entries.append(RankingEntry(
                address=car.address, name=car.name, position=i + 1, lap_count=car.lap_count,
                laps_down=laps_down, best_lap=car.best_lap, last_lap=last_lap, gap_to_leader=gap,
                delta_vs_best=delta, penalty_seconds=car.total_penalty_seconds, fuel=car.fuel,
                jump_start=car.jump_start,
            ))
        return entries
