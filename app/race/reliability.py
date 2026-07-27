"""Random mechanical breakdowns: a low-probability, per-tick chance of a
car breaking down while running, forcing it to a dead stop until it's
been serviced in the pit for `repair_seconds`. Independent of the normal
fuel/tyre wear model -- a random reliability event, not something driving
style affects.

Repair progress only accumulates while the car is actually in the pit
(caller-supplied `in_pit` flag) and pauses (doesn't reset) if it leaves
before finishing -- matching how a real pit stop can't be half-done.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class ReliabilityConfig:
    breakdown_chance_per_second: float = 0.0008
    repair_seconds: float = 8.0


class ReliabilitySystem:
    def __init__(self, config: ReliabilityConfig | None = None):
        self.config = config or ReliabilityConfig()
        self._broken_down: set[int] = set()
        self._repaired_seconds: dict[int, float] = {}

    def maybe_break_down(self, address: int, dt: float, rng: random.Random | None = None) -> bool:
        """Call once per tick for a running, non-broken-down car. Returns
        True if it just broke down this call."""
        source = rng or random
        if address in self._broken_down:
            return False
        if source.random() < self.config.breakdown_chance_per_second * dt:
            self._broken_down.add(address)
            self._repaired_seconds[address] = 0.0
            return True
        return False

    def is_broken_down(self, address: int) -> bool:
        return address in self._broken_down

    def tick_repair(self, address: int, in_pit: bool, dt: float) -> bool:
        """Call once per tick for a broken-down car. Returns True if this
        call just completed the repair."""
        if address not in self._broken_down:
            return False
        if in_pit:
            self._repaired_seconds[address] = self._repaired_seconds.get(address, 0.0) + dt
            if self._repaired_seconds[address] >= self.config.repair_seconds:
                self._broken_down.discard(address)
                self._repaired_seconds.pop(address, None)
                return True
        return False

    def repair_progress(self, address: int) -> float:
        """0..1, meaningless (returns 1.0) if not currently broken down."""
        if address not in self._broken_down:
            return 1.0
        return min(1.0, self._repaired_seconds.get(address, 0.0) / self.config.repair_seconds)
