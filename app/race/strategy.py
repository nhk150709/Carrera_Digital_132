"""Pre-race strategy plan per car: starting fuel load, tyre compound, and
planned pit-stop laps -- the F1-management-game style plan the driver sets
before the green light, plus a lap-by-lap fuel/tyre projection so the UI
can plot it against what actually happens during the race.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.race.fuel import COMPOUND_PROFILES, FuelConfig, TyreCompound


@dataclass
class RaceStrategy:
    address: int
    fuel_load: float = 100.0  # 0..fuel_capacity
    compound: TyreCompound = TyreCompound.MEDIUM
    planned_pit_laps: list[int] = field(default_factory=list)


@dataclass
class ProjectedPoint:
    lap: int
    fuel: float
    tyre_wear: float


def _per_lap_rates(compound: TyreCompound, avg_lap_seconds: float, config: FuelConfig,
                     typical_throttle: float, typical_brake: float) -> tuple[float, float]:
    """Shared steady-state fuel/tyre-wear-per-lap estimate, used by both
    project_plan() and recommend_strategy() so the projected planning line
    and the recommended fuel load are always assuming the same driving
    style -- otherwise the graph could show a "recommended" plan running
    out of fuel before the finish, which would just be a modeling bug.
    """
    profile = COMPOUND_PROFILES[compound]
    fuel_per_lap = (
        config.base_drain_per_second
        + (typical_throttle ** config.throttle_drain_exponent) * config.base_drain_per_second * 2
    ) * avg_lap_seconds
    wear_per_lap = (
        typical_throttle * config.accel_wear_per_second + typical_brake * config.brake_wear_per_second
    ) * profile.wear_rate_multiplier * avg_lap_seconds
    return fuel_per_lap, wear_per_lap


def project_plan(strategy: RaceStrategy, total_laps: int, avg_lap_seconds: float,
                   config: FuelConfig | None = None,
                   typical_throttle: float = 0.75, typical_brake: float = 0.35) -> list[ProjectedPoint]:
    """Straight-line projection of fuel/tyre remaining per lap at
    "typical" (not full-throttle-100%-of-the-time) steady-state driving,
    with a tyre change on every planned pit lap. This is a planning aid,
    not a prediction of exact race telemetry -- actual values (tracked
    separately per lap as the race runs) will differ once real driving
    input is involved.
    """
    cfg = config or FuelConfig()
    fuel_per_lap, wear_per_lap = _per_lap_rates(strategy.compound, avg_lap_seconds, cfg,
                                                   typical_throttle, typical_brake)

    fuel = strategy.fuel_load
    tyre_wear = 0.0
    points = [ProjectedPoint(lap=0, fuel=fuel, tyre_wear=tyre_wear)]
    for lap in range(1, total_laps + 1):
        fuel = max(0.0, fuel - fuel_per_lap)
        tyre_wear = min(cfg.tyre_wear_cap, tyre_wear + wear_per_lap)
        if lap in strategy.planned_pit_laps:
            tyre_wear = 0.0
        points.append(ProjectedPoint(lap=lap, fuel=fuel, tyre_wear=tyre_wear))
    return points


RECOMMENDED_TYRE_CHANGE_WEAR = 65.0  # suggest a pit once projected wear crosses this


def recommend_strategy(address: int, total_laps: int, avg_lap_seconds: float,
                         config: FuelConfig | None = None,
                         typical_throttle: float = 0.75,
                         typical_brake: float = 0.35) -> RaceStrategy:
    """A sensible, balanced default plan for a newcomer who isn't going to
    use overtake boosts: enough fuel load to just cover the full race
    distance at "typical" (not full-throttle-100%-of-the-time) driving,
    medium compound, and one suggested pit lap at the point the same
    typical-driving assumption would cross the tyre-performance-cliff
    wear threshold. Derived directly from the live FuelModel constants
    (not independently tuned numbers), so it stays consistent with
    whatever the simulation actually does at runtime.
    """
    cfg = config or FuelConfig()
    compound = TyreCompound.MEDIUM
    fuel_per_lap, wear_per_lap = _per_lap_rates(compound, avg_lap_seconds, cfg,
                                                   typical_throttle, typical_brake)

    fuel_needed = fuel_per_lap * total_laps
    fuel_load = min(cfg.fuel_capacity, max(10.0, round(fuel_needed, 1)))

    planned_pit_laps: list[int] = []
    if wear_per_lap > 0 and total_laps > 1:
        lap_at_threshold = RECOMMENDED_TYRE_CHANGE_WEAR / wear_per_lap
        pit_lap = max(1, min(total_laps - 1, round(lap_at_threshold)))
        planned_pit_laps = [pit_lap]

    return RaceStrategy(address=address, fuel_load=fuel_load, compound=compound,
                          planned_pit_laps=planned_pit_laps)


class StrategyBook:
    """Holds each car's plan for the current session."""

    def __init__(self) -> None:
        self._plans: dict[int, RaceStrategy] = {}

    def set(self, strategy: RaceStrategy) -> None:
        self._plans[strategy.address] = strategy

    def get(self, address: int) -> RaceStrategy | None:
        return self._plans.get(address)

    def all(self) -> dict[int, RaceStrategy]:
        return dict(self._plans)
