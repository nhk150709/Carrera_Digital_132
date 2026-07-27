"""Hardware-agnostic shapes for CU data. Both the mock and the real
(carreralib-backed) client produce these, so the rest of the app never
touches carreralib's namedtuples or wire-protocol details directly.

Note on sector numbering: the real CU protocol reports sector=1 for a
start/finish crossing and 2/3 for Check Lane splits (confirmed against
carreralib 1.0.3 source). app.race.engine uses sector=0 to mean "lap
completed" for its own internal simplicity/testability -- the CU adapter
(app/cu/carreralib_client.py) is responsible for translating 1 -> 0 at the
boundary. The mock client emits 0 directly since it has no real protocol
to imitate.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Status:
    fuel: tuple[int, ...]  # 8 values, 0..15 on real hardware
    pit: tuple[bool, ...]  # 8 values
    start: int  # CU start-light state, 0..9 on real hardware
    mode: int  # 4-bit mode bitmask
    display: int


@dataclass
class TimerEvent:
    address: int  # 0-5 controllers, 6 autonomous, 7 pace car
    timestamp: float  # seconds
    sector: int  # 0 = lap completed (start/finish); see module docstring
