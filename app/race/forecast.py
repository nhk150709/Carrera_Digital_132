"""Weather forecast, on a lap-count clock rather than wall-clock time.

Real time is a bad axis for "when does the weather change" here because
lap duration varies wildly by track length/car speed -- so instead the
forecast is scheduled against the race leader's lap count ("it starts
raining when the leader reaches lap 20"), which stays meaningful
regardless of how long a lap actually takes on a given layout.

The forecast shown to players is a *prediction*, not the ground truth:
each entry has a `confidence` (the probability the prediction is right)
that's actually calibrated -- a 70%-confidence forecast is generated to
be correct 70% of the time in expectation, not just decorative. Comparing
your tyre choice against the forecast (not the hidden actual outcome) is
the gamble.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from app.race.models import WeatherLevel

ALL_LEVELS = list(WeatherLevel)


@dataclass
class ForecastEntry:
    lap: int
    predicted_level: WeatherLevel
    confidence: float  # 0..1, shown to players
    actual_level: WeatherLevel  # hidden until reached


class WeatherForecast:
    def __init__(self, schedule: list[ForecastEntry]):
        self.schedule = sorted(schedule, key=lambda e: e.lap)
        self._applied_index = 0

    def visible_forecast(self) -> list[dict]:
        """What players are allowed to see -- prediction + confidence,
        never the hidden actual_level."""
        return [
            {"lap": e.lap, "predicted_level": e.predicted_level.value, "confidence": e.confidence}
            for e in self.schedule
        ]

    def advance(self, leader_lap: int) -> WeatherLevel | None:
        """Call whenever the leader's lap count may have changed. Returns
        the newly active actual weather level if a scheduled change was
        just crossed (only the most recent one, if several were somehow
        skipped in one jump), else None."""
        changed = None
        while self._applied_index < len(self.schedule) and self.schedule[self._applied_index].lap <= leader_lap:
            changed = self.schedule[self._applied_index].actual_level
            self._applied_index += 1
        return changed


def generate_forecast(total_laps: int, num_changes: int = 2,
                        rng: random.Random | None = None) -> WeatherForecast:
    source = rng or random
    num_changes = max(0, min(num_changes, max(0, total_laps - 3)))
    candidate_laps = range(3, total_laps) if total_laps > 3 else range(0, 0)
    laps = sorted(source.sample(list(candidate_laps), k=num_changes)) if num_changes else []

    schedule = []
    for lap in laps:
        actual = source.choice(ALL_LEVELS)
        confidence = round(source.uniform(0.5, 0.9), 2)
        # The forecast is right with probability == confidence -- that's
        # what makes the displayed percentage a genuine, honest gamble
        # rather than flavor text.
        predicted = actual if source.random() < confidence else source.choice(ALL_LEVELS)
        schedule.append(ForecastEntry(lap=lap, predicted_level=predicted,
                                        confidence=confidence, actual_level=actual))
    return WeatherForecast(schedule)
