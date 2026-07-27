"""Penalty rules engine. Pure logic, operates on CarState objects."""
from __future__ import annotations

from app.race.models import CarState, PenaltyRecord

JUMP_START_PENALTY_SECONDS = 5.0
RACE_STOP_PENALTY_SECONDS = 10.0


class PenaltyEngine:
    def apply(self, car: CarState, seconds: float, reason: str, timestamp: float) -> None:
        car.penalties.append(PenaltyRecord(seconds=seconds, reason=reason, timestamp=timestamp))

    def jump_start(self, car: CarState, timestamp: float) -> None:
        car.jump_start = True
        self.apply(car, JUMP_START_PENALTY_SECONDS, "jump_start", timestamp)

    def race_stopped_by(self, car: CarState, timestamp: float) -> None:
        """Penalize the player who triggered a race stop (e.g. a false derail call)."""
        self.apply(car, RACE_STOP_PENALTY_SECONDS, "triggered_stop", timestamp)

    def custom(self, car: CarState, seconds: float, reason: str, timestamp: float) -> None:
        self.apply(car, seconds, reason, timestamp)
