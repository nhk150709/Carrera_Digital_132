"""Fuel + tyre resource model.

Design, per explicit request:
- Fuel is never rechargeable mid-race (no pit refuel). The only strategic
  fuel choice is how much to *start* with (fuel load), chosen pre-race.
  More starting fuel = more range but a heavier car (weight penalty
  reduces effective speed while that fuel is still on board -- burns off
  as the tank empties, so a heavy full-tank car gets faster over a stint,
  same trade-off real endurance racing has).
- Tyres are the only pit-serviceable resource: heavy braking wears them,
  heavy acceleration burns fuel. Worn tyres don't just change fuel drain
  rate anymore -- they meaningfully cut top speed and braking
  effectiveness (see performance_multiplier/brake_multiplier below), so a
  driver has a real reason to pit even with fuel to spare.
- Tyre compounds trade peak grip for wear rate (soft = faster but wears
  quicker; hard = slower but lasts).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.race.models import WeatherLevel


class TyreCompound(str, Enum):
    SOFT = "soft"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class CompoundProfile:
    grip_multiplier: float  # applied to effective speed cap
    wear_rate_multiplier: float  # applied to tyre wear accumulation
    label: str


COMPOUND_PROFILES: dict[TyreCompound, CompoundProfile] = {
    TyreCompound.SOFT: CompoundProfile(1.05, 1.6, "Soft"),
    TyreCompound.MEDIUM: CompoundProfile(1.0, 1.0, "Medium"),
    TyreCompound.HARD: CompoundProfile(0.93, 0.6, "Hard"),
}

# Which compound is the "right call" for each weather condition -- soft
# for dry grip, hard for wet stability, medium in between. This is a
# simplified 3-compound model (no dedicated wet tyre), not a claim about
# how real slicks behave in the rain.
WEATHER_COMPOUND_MATCH: dict[WeatherLevel, TyreCompound] = {
    WeatherLevel.DRY: TyreCompound.SOFT,
    WeatherLevel.DAMP: TyreCompound.MEDIUM,
    WeatherLevel.WET: TyreCompound.HARD,
}

_COMPOUND_ORDER = {TyreCompound.SOFT: 0, TyreCompound.MEDIUM: 1, TyreCompound.HARD: 2}
_WEATHER_ORDER = {WeatherLevel.DRY: 0, WeatherLevel.DAMP: 1, WeatherLevel.WET: 2}


def weather_match_multiplier(compound: TyreCompound, weather: WeatherLevel,
                               match_bonus: float = 0.08,
                               mismatch_penalty_per_step: float = 0.12) -> float:
    """>1.0 if the compound is the right call for the current weather,
    <1.0 the further off it is (e.g. soft tyres in the wet is the worst
    mismatch, 2 steps away). Applied to both speed and braking."""
    steps = abs(_COMPOUND_ORDER[compound] - _WEATHER_ORDER[weather])
    if steps == 0:
        return 1.0 + match_bonus
    return max(0.4, 1.0 - mismatch_penalty_per_step * steps)


@dataclass
class FuelConfig:
    fuel_capacity: float = 100.0  # a "full tank" -- also the max fuel_load
    base_drain_per_second: float = 0.6
    throttle_drain_exponent: float = 1.5
    tyre_wear_cap: float = 100.0
    accel_wear_per_second: float = 0.9
    brake_wear_per_second: float = 0.6
    pit_tyre_change_rate: float = 60.0  # tyre_wear units removed per second in pit

    # Weight penalty: a full tank costs this much of the speed multiplier;
    # it burns off linearly as fuel is consumed (0 penalty at empty).
    max_weight_penalty: float = 0.08

    # Tyre performance cliff: multiplier drops by up to this fraction as
    # wear approaches the cap, on a quadratic curve (degrades slowly at
    # first, then falls off a cliff near full wear -- how real tyres feel).
    max_tyre_performance_drop: float = 0.5
    max_tyre_brake_drop: float = 0.35

    # Push-to-pass cost multipliers, applied on top of normal drain/wear
    # while the overtake boost is active.
    boost_fuel_multiplier: float = 2.5
    boost_tyre_wear_multiplier: float = 2.0


class FuelModel:
    def __init__(self, addresses: list[int], config: FuelConfig | None = None):
        self.config = config or FuelConfig()
        self._fuel: dict[int, float] = {a: self.config.fuel_capacity for a in addresses}
        self._tyre_wear: dict[int, float] = {a: 0.0 for a in addresses}
        self._compound: dict[int, TyreCompound] = {a: TyreCompound.MEDIUM for a in addresses}

    def fuel(self, address: int) -> float:
        return self._fuel[address]

    def tyre_wear(self, address: int) -> float:
        return self._tyre_wear[address]

    def compound(self, address: int) -> TyreCompound:
        return self._compound[address]

    def set_starting_load(self, address: int, fuel_load: float) -> None:
        """Pre-race choice: how much fuel to start with, 0..fuel_capacity."""
        self._fuel[address] = max(0.0, min(self.config.fuel_capacity, fuel_load))

    def set_compound(self, address: int, compound: TyreCompound) -> None:
        self._compound[address] = compound

    def change_tyres(self, address: int) -> None:
        """Instant tyre change -- call once, e.g. on pit entry, rather than
        every tick (unlike the old drip-refuel model, a tyre change is a
        discrete pit-stop event, not a continuous-while-in-pit effect)."""
        self._tyre_wear[address] = 0.0

    def update(self, address: int, throttle: float, brake: float, dt: float,
                boosting: bool = False) -> None:
        """Advance simulation for one car by dt seconds. No `in_pit`
        parameter anymore -- fuel never regenerates, and tyre wear only
        resets via the explicit change_tyres() event. `boosting` applies
        the push-to-pass fuel/wear cost multipliers."""
        throttle = max(0.0, min(1.0, throttle))
        brake = max(0.0, min(1.0, brake))
        cfg = self.config
        compound = COMPOUND_PROFILES[self._compound[address]]

        drain = cfg.base_drain_per_second
        drain += (throttle ** cfg.throttle_drain_exponent) * cfg.base_drain_per_second * 2
        if boosting:
            drain *= cfg.boost_fuel_multiplier
        self._fuel[address] = max(0.0, self._fuel[address] - drain * dt)

        wear_gain = (throttle * cfg.accel_wear_per_second + brake * cfg.brake_wear_per_second)
        wear_gain *= compound.wear_rate_multiplier
        if boosting:
            wear_gain *= cfg.boost_tyre_wear_multiplier
        self._tyre_wear[address] = min(cfg.tyre_wear_cap, self._tyre_wear[address] + wear_gain * dt)

    def is_empty(self, address: int) -> bool:
        return self._fuel[address] <= 0.0

    def weight_penalty_multiplier(self, address: int) -> float:
        """1.0 = no penalty; drops toward (1 - max_weight_penalty) as the
        tank gets fuller. Burns off as fuel is used."""
        fraction = self._fuel[address] / self.config.fuel_capacity
        return 1.0 - self.config.max_weight_penalty * fraction

    def tyre_performance_multiplier(self, address: int) -> float:
        """Effective top-speed multiplier from tyre wear + compound grip."""
        cfg = self.config
        wear_fraction = self._tyre_wear[address] / cfg.tyre_wear_cap
        wear_multiplier = 1.0 - cfg.max_tyre_performance_drop * (wear_fraction ** 2)
        compound = COMPOUND_PROFILES[self._compound[address]]
        return wear_multiplier * compound.grip_multiplier

    def brake_effectiveness_multiplier(self, address: int) -> float:
        cfg = self.config
        wear_fraction = self._tyre_wear[address] / cfg.tyre_wear_cap
        return 1.0 - cfg.max_tyre_brake_drop * (wear_fraction ** 2)
