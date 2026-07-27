"""Custom fuel model driven by throttle input and tyre wear.

This is deliberately independent of the CU's own built-in fuel simulation
(which, per SmartRace's docs, is purely lap-time-deviation based). Here fuel
drains as a function of how hard the car is being driven (throttle) and how
worn the tyres are, and tyre wear itself accumulates from hard
acceleration/braking. A pit-lane stop refuels and can reset tyre wear.

None of this depends on the CU/hardware layer -- it only needs a stream of
(address, throttle, brake, dt) samples, which can come from a real
controller, a recorded replay, or a test.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FuelConfig:
    fuel_capacity: float = 100.0
    base_drain_per_second: float = 0.6
    throttle_drain_exponent: float = 1.5
    tyre_wear_drain_multiplier: float = 0.8
    accel_wear_per_second: float = 0.9
    brake_wear_per_second: float = 0.6
    tyre_wear_cap: float = 100.0
    pit_refuel_per_second: float = 20.0
    pit_tyre_change_rate: float = 60.0  # tyre_wear units removed per second in pit


class FuelModel:
    def __init__(self, addresses: list[int], config: FuelConfig | None = None):
        self.config = config or FuelConfig()
        self._fuel: dict[int, float] = {a: self.config.fuel_capacity for a in addresses}
        self._tyre_wear: dict[int, float] = {a: 0.0 for a in addresses}

    def fuel(self, address: int) -> float:
        return self._fuel[address]

    def tyre_wear(self, address: int) -> float:
        return self._tyre_wear[address]

    def set_fuel(self, address: int, value: float) -> None:
        self._fuel[address] = max(0.0, min(self.config.fuel_capacity, value))

    def update(self, address: int, throttle: float, brake: float, dt: float, in_pit: bool = False) -> None:
        """Advance simulation for one car by dt seconds.

        throttle/brake are expected in [0, 1].
        """
        throttle = max(0.0, min(1.0, throttle))
        brake = max(0.0, min(1.0, brake))
        cfg = self.config

        if in_pit:
            self._fuel[address] = min(cfg.fuel_capacity, self._fuel[address] + cfg.pit_refuel_per_second * dt)
            self._tyre_wear[address] = max(0.0, self._tyre_wear[address] - cfg.pit_tyre_change_rate * dt)
            return

        wear = self._tyre_wear[address] / cfg.tyre_wear_cap  # 0..1
        drain = cfg.base_drain_per_second
        drain += (throttle ** cfg.throttle_drain_exponent) * cfg.base_drain_per_second * 2
        drain *= 1.0 + wear * cfg.tyre_wear_drain_multiplier
        self._fuel[address] = max(0.0, self._fuel[address] - drain * dt)

        wear_gain = throttle * cfg.accel_wear_per_second + brake * cfg.brake_wear_per_second
        self._tyre_wear[address] = min(cfg.tyre_wear_cap, self._tyre_wear[address] + wear_gain * dt)

    def is_empty(self, address: int) -> bool:
        return self._fuel[address] <= 0.0
