"""Push-to-pass: a temporary top-speed boost the driver triggers from
their own screen, at a heavy fuel/tyre cost (see FuelModel.update's
`boosting` flag), gated by a cooldown so it can't be held on constantly.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OvertakeConfig:
    duration_seconds: float = 5.0
    cooldown_seconds: float = 20.0
    boost_multiplier: float = 1.18  # effective top-speed multiplier while active


class OvertakeSystem:
    def __init__(self, config: OvertakeConfig | None = None):
        self.config = config or OvertakeConfig()
        self._active_until: dict[int, float] = {}
        self._cooldown_until: dict[int, float] = {}

    def trigger(self, address: int, now: float) -> bool:
        """Returns True if the boost actually activated (False if already
        active or still on cooldown)."""
        if self.is_active(address, now) or self.is_on_cooldown(address, now):
            return False
        self._active_until[address] = now + self.config.duration_seconds
        self._cooldown_until[address] = (
            now + self.config.duration_seconds + self.config.cooldown_seconds
        )
        return True

    def is_active(self, address: int, now: float) -> bool:
        return now < self._active_until.get(address, float("-inf"))

    def is_on_cooldown(self, address: int, now: float) -> bool:
        return not self.is_active(address, now) and now < self._cooldown_until.get(address, float("-inf"))

    def seconds_remaining(self, address: int, now: float) -> float:
        return max(0.0, self._active_until.get(address, 0.0) - now)

    def cooldown_remaining(self, address: int, now: float) -> float:
        return max(0.0, self._cooldown_until.get(address, 0.0) - now)
