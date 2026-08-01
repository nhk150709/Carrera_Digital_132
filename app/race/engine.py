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
        self.last_stop_triggered_by: int | None = None

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
        self.last_stop_triggered_by = None
        self._emit("race reset")

    def begin_countdown(self, now: float) -> None:
        self.state = RaceState.COUNTDOWN
        self.last_stop_triggered_by = None
        self._emit(f"countdown armed at t={now:.2f}")

    def go(self, now: float) -> None:
        self.state = RaceState.RUNNING
        self.go_timestamp = now
        for car in self.cars.values():
            # Deliberately not seeded with `now`: `now` is this app's own
            # clock, but a real CU's Timer timestamps come back in a
            # completely different, CU-internal clock domain (see
            # app/cu/carreralib_client.py's _to_seconds()) that has no
            # fixed relationship to when go() was called. Subtracting one
            # domain from the other produces nonsense lap times (observed
            # in practice: huge negative numbers). Leaving this None makes
            # the first crossing after go() an unrecorded baseline instead
            # -- standard lap-timer behavior, and safe regardless of which
            # CU backend's clock domain is in play.
            car.last_crossing_timestamp = None
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
        self.last_stop_triggered_by = triggered_by
        self._emit(f"race stopped ({reason}) at t={now:.2f} by address={triggered_by}")
        if penalize_trigger and triggered_by is not None and triggered_by in self.cars:
            self.penalty_engine.race_stopped_by(self.cars[triggered_by], now)
            self._emit(f"penalty applied to address={triggered_by} for triggering stop")

    def resume(self, now: float) -> None:
        if self.state != RaceState.PAUSED:
            return
        self.state = RaceState.RUNNING
        # Same reasoning as go(): can't seed with `now` (this app's clock)
        # since it doesn't share a domain with the CU's own Timer
        # timestamps. The next crossing after resume() becomes a fresh
        # unrecorded baseline instead, same as after go().
        for car in self.cars.values():
            car.last_crossing_timestamp = None
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
        (a full lap); nonzero sectors are recorded but don't complete a lap
        and never establish the baseline either (only a real start/finish
        crossing should anchor lap timing, not a mid-lap Check Lane split
        that happens to arrive first).

        The first sector-0 crossing after go()/resume() is an unrecorded
        baseline (car.last_crossing_timestamp starts at None then); the
        *next* sector-0 crossing is lap 1, timed from that baseline.
        """
        car = self.cars.get(address)
        if car is None or self.state != RaceState.RUNNING:
            return None
        if sector != 0:
            # Sector split (e.g. a Check Lane) -- not a lap completion,
            # and must not consume/set the baseline.
            return None
        if car.last_crossing_timestamp is None:
            car.last_crossing_timestamp = timestamp
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

    def grid_order(self) -> list[int]:
        """Addresses sorted by best lap, fastest first -- the starting
        grid a QUALIFYING session produces, for display when carried into
        a following RACE session. Cars with no timed lap sort last, in
        address order."""
        cars = list(self.cars.values())
        ranked = sorted(
            cars,
            key=lambda c: (c.best_lap is None, c.best_lap if c.best_lap is not None else float("inf"), c.address),
        )
        return [c.address for c in ranked]

    def rankings(self) -> list[RankingEntry]:
        cars = list(self.cars.values())
        session_best = self._session_best_lap()

        if self.mode in (RaceMode.TIME_ATTACK, RaceMode.QUALIFYING):
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
