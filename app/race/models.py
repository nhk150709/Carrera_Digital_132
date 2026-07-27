"""Pure data models for the race engine. No external dependencies on purpose,
so this module (and everything built only on it) is unit-testable without
FastAPI/pygame/carreralib installed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RaceMode(str, Enum):
    RACE = "race"
    TIME_ATTACK = "time_attack"
    QUALIFYING = "qualifying"


class RaceState(str, Enum):
    IDLE = "idle"
    COUNTDOWN = "countdown"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"


class WeatherLevel(str, Enum):
    DRY = "dry"
    DAMP = "damp"
    WET = "wet"


# CU addressing, per docs/reference/protocol-notes.md: 0-5 controllers 1-6,
# 6 autonomous car, 7 pace car.
AUTONOMOUS_ADDRESS = 6
PACE_CAR_ADDRESS = 7
MAX_ADDRESS = 7


@dataclass
class LapRecord:
    lap_number: int
    lap_time: float  # seconds
    timestamp: float  # engine-clock seconds since race start
    sector: int = 0
    fuel_at_lap: float = 0.0
    tyre_wear_at_lap: float = 0.0


@dataclass
class PenaltyRecord:
    seconds: float
    reason: str
    timestamp: float


@dataclass
class CarState:
    address: int
    name: str = ""
    controller_id: str | None = None
    fuel: float = 100.0
    tyre_wear: float = 0.0
    in_pit: bool = False

    laps: list[LapRecord] = field(default_factory=list)
    penalties: list[PenaltyRecord] = field(default_factory=list)
    jump_start: bool = False
    last_crossing_timestamp: float | None = None
    connected: bool = False

    @property
    def lap_count(self) -> int:
        return len(self.laps)

    @property
    def best_lap(self) -> float | None:
        if not self.laps:
            return None
        return min(lap.lap_time for lap in self.laps)

    @property
    def total_penalty_seconds(self) -> float:
        return sum(p.seconds for p in self.penalties)

    @property
    def elapsed_time(self) -> float:
        """Sum of lap times plus penalties -- used for RACE-mode ranking."""
        return sum(lap.lap_time for lap in self.laps) + self.total_penalty_seconds


@dataclass
class RankingEntry:
    address: int
    name: str
    position: int
    lap_count: int
    laps_down: int  # 0 for cars on the leader's lap
    best_lap: float | None
    last_lap: float | None
    gap_to_leader: float | None  # seconds; meaningful only when laps_down == 0
    delta_vs_best: float | None  # last lap minus fastest lap of the session (any car)
    penalty_seconds: float
    fuel: float
    jump_start: bool
