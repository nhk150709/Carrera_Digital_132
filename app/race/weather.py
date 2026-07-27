"""Software-side weather simulation.

The CU has no way to change physical track grip, so "weather" here is a
speed-cap / grip multiplier applied in software to any commanded speed --
the same trick SmartRace's own "weather" event almost certainly uses
(see docs/reference/protocol-notes.md). It also scales tyre wear and fuel
drain, so wet conditions matter beyond just a top-speed cap.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.race.models import WeatherLevel

MAX_SPEED = 15  # Carrera speed command range is 0-15 per the CU protocol


@dataclass
class WeatherProfile:
    grip_multiplier: float  # applied to max commandable speed
    wear_multiplier: float  # applied to tyre wear accumulation
    label: str


PROFILES: dict[WeatherLevel, WeatherProfile] = {
    WeatherLevel.DRY: WeatherProfile(1.0, 1.0, "Dry"),
    WeatherLevel.DAMP: WeatherProfile(0.8, 1.3, "Damp"),
    WeatherLevel.WET: WeatherProfile(0.6, 1.6, "Wet"),
}


class WeatherMode:
    def __init__(self, level: WeatherLevel = WeatherLevel.DRY):
        self.level = level

    @property
    def profile(self) -> WeatherProfile:
        return PROFILES[self.level]

    def set_level(self, level: WeatherLevel) -> None:
        self.level = level

    def cap_speed(self, requested_speed: int) -> int:
        capped = requested_speed * self.profile.grip_multiplier
        return max(0, min(MAX_SPEED, round(capped)))

    def wear_multiplier(self) -> float:
        return self.profile.wear_multiplier
