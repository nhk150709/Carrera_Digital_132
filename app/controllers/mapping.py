"""Per-player sensitivity curves for throttle/brake response.

exponent > 1 makes the low end of the stick/trigger less sensitive (easier
to modulate finely, harder to floor it by accident); exponent < 1 makes it
more twitchy near zero. gain scales the whole curve, letting a player cap
their own max effective throttle/brake independent of the exponent shape.
"""
from __future__ import annotations

from dataclasses import dataclass


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class SensitivityCurve:
    throttle_exponent: float = 1.0
    throttle_gain: float = 1.0
    brake_exponent: float = 1.0
    brake_gain: float = 1.0

    def apply_throttle(self, raw: float) -> float:
        raw = _clamp01(raw)
        return _clamp01((raw ** self.throttle_exponent) * self.throttle_gain)

    def apply_brake(self, raw: float) -> float:
        raw = _clamp01(raw)
        return _clamp01((raw ** self.brake_exponent) * self.brake_gain)
