"""Safety car / full-course caution.

Two independent effects:
1. A "virtual" caution: cap every racing car's effective speed while
   active. Needs zero extra hardware -- this is almost certainly how
   SmartRace's own caution-style events work too, since the CU has no way
   to physically move or place anything on the track on its own.
2. Commanding an actual physical safety car via the CU's pace-car address
   (7) -- but only if a real car is actually sitting on the track
   occupying that slot. The CU cannot place a car onto the track by
   itself; a human has to physically put a pace car in a lane before the
   race for this to mean anything. `physically_present` records whether
   that's true for this session; when False, triggering the safety car
   only applies the field-wide slowdown (the "virtual" case above).
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class SafetyCarConfig:
    field_speed_cap: int = 5  # 0..15, applied to every racing car while active
    pace_car_speed: int = 6  # 0..15, sent to the physical pace car if present
    random_trigger_chance_per_lap: float = 0.0  # 0..1, e.g. 0.05 = 5% per completed lap


class SafetyCarSystem:
    def __init__(self, physically_present: bool = False, config: SafetyCarConfig | None = None):
        self.physically_present = physically_present
        self.config = config or SafetyCarConfig()
        self.active = False

    def trigger(self) -> None:
        self.active = True

    def end(self) -> None:
        self.active = False

    def maybe_random_trigger(self, rng: random.Random | None = None) -> bool:
        """Call once per completed lap; may trigger randomly. Returns True
        if it just triggered."""
        source = rng or random
        if not self.active and source.random() < self.config.random_trigger_chance_per_lap:
            self.trigger()
            return True
        return False

    def cap_speed(self, requested_speed: int) -> int:
        if not self.active:
            return requested_speed
        return min(requested_speed, self.config.field_speed_cap)
