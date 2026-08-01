"""Hardware-agnostic shapes for CU data. Both the mock and the real
(carreralib-backed) client produce these, so the rest of the app never
touches carreralib's namedtuples or wire-protocol details directly.

Note on sector numbering: the real CU protocol reports sector=1 for a
start/finish crossing and 2/3 for Check Lane splits (confirmed against
carreralib 1.0.3 source). This app translates 1 -> 0 at the CU adapter
boundary (app/cu/carreralib_client.py) so "0 = lap completed" is the one
convention used everywhere upstream of it. The mock client emits 0
directly since it has no real protocol to imitate.
"""
from __future__ import annotations

from dataclasses import dataclass

# Status.mode bit flags (confirmed from carreralib.cu.ControlUnit.Status).
# PIT_LANE_MODE in particular matters beyond just decoding the bitmask for
# display: it tells you whether a physical pit-lane adapter is actually
# connected at all, i.e. whether Status.pit[] means anything, or is just
# a meaningless all-False array because there's no adapter to report it.
FUEL_MODE = 0x1
REAL_MODE = 0x2
PIT_LANE_MODE = 0x4
LAP_COUNTER_MODE = 0x8

# Status.start values -- CONFIRMED by directly watching this field during a
# real countdown on real hardware (not carreralib's docs, which only say
# "0..9 start light indicator" with no per-value meaning): 0 = racing
# (green -- also the value pressing START/ENTER returns to once the
# sequence finishes), 1 = stopped, 2..7 = the light sequence stepping up
# after START/ENTER is pressed while stopped, with 7 being the last step
# before it drops back to 0. Values 8/9 have not been observed -- carreralib
# documents the field as 0..9 but 8/9 may be unreachable in normal use, or
# may appear under a condition not yet tested (e.g. a false start, or
# pace-car/safety-car mode -- see START_LABELS below and the open question
# in CLAUDE.md).
START_RACING = 0
START_STOPPED = 1
START_LIGHT_SEQUENCE = frozenset(range(2, 8))  # 2..7

START_LABELS: dict[int, str] = {
    0: "RACING",
    1: "STOPPED",
    2: "light sequence 1/6",
    3: "light sequence 2/6",
    4: "light sequence 3/6",
    5: "light sequence 4/6",
    6: "light sequence 5/6",
    7: "light sequence 6/6 (about to go)",
}


def describe_start(value: int) -> str:
    return START_LABELS.get(value, f"unknown ({value}) -- not seen/documented before, please report")


# CU physical button IDs, for press(button_id) (confirmed from carreralib.
# cu.ControlUnit's own class constants -- see docstrings there for what
# each one does on real hardware, not independently re-confirmed here
# except START_ENTER_BUTTON_ID's effect on the start field above).
PACE_CAR_ESC_BUTTON_ID = 1
START_ENTER_BUTTON_ID = 2
SPEED_BUTTON_ID = 5
BRAKE_BUTTON_ID = 6
FUEL_BUTTON_ID = 7
CODE_BUTTON_ID = 8


@dataclass
class Status:
    fuel: tuple[int, ...]  # 8 values, 0..15 on real hardware
    pit: tuple[bool, ...]  # 8 values
    start: int  # CU start-light state, 0..9 on real hardware -- see START_LABELS above
    mode: int  # 4-bit mode bitmask
    display: int


@dataclass
class TimerEvent:
    address: int  # 0-5 controllers, 6 autonomous, 7 pace car
    timestamp: float  # seconds
    sector: int  # 0 = lap completed (start/finish); see module docstring
