"""Ghost delta: compares this race's lap-by-lap cumulative time against a
previously recorded session's lap times, for a "gap to your own best lap"
readout.

Honest limitation: the CU only reports discrete lap/sector crossing
timestamps, not continuous car position, so this can only update at each
lap (or sector, if Check Lanes are configured) boundary -- not smoothly
every fraction of a second like a telemetry-based delta bar in a sim.
Genuinely continuous ghost tracking would need either Check Lane sector
splits (finer, but still discrete) or a continuous position source (e.g.
a camera-based tracking system) to interpolate between crossings.
"""
from __future__ import annotations

from app.race.recorder import EventType, Recording


class GhostComparator:
    def __init__(self, recording: Recording):
        self.lap_times: dict[int, float] = {
            int(e.value): e.t for e in recording.events if e.type == EventType.LAP
        }

    def delta_at_lap(self, lap_number: int, elapsed_at_lap: float) -> float | None:
        """Positive = slower than the ghost through this lap, negative =
        faster. None if the ghost recording has no data for this lap."""
        ghost_t = self.lap_times.get(lap_number)
        if ghost_t is None:
            return None
        return elapsed_at_lap - ghost_t
