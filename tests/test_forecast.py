import random

from app.race.forecast import ForecastEntry, WeatherForecast, generate_forecast
from app.race.models import WeatherLevel


def test_advance_returns_none_before_scheduled_lap():
    forecast = WeatherForecast([ForecastEntry(lap=10, predicted_level=WeatherLevel.WET,
                                                 confidence=0.7, actual_level=WeatherLevel.WET)])
    assert forecast.advance(leader_lap=5) is None


def test_advance_triggers_at_scheduled_lap():
    forecast = WeatherForecast([ForecastEntry(lap=10, predicted_level=WeatherLevel.WET,
                                                 confidence=0.7, actual_level=WeatherLevel.WET)])
    assert forecast.advance(leader_lap=10) == WeatherLevel.WET
    assert forecast.advance(leader_lap=11) is None  # already applied, not re-triggered


def test_advance_applies_multiple_skipped_entries_returns_latest():
    forecast = WeatherForecast([
        ForecastEntry(lap=5, predicted_level=WeatherLevel.DAMP, confidence=0.6, actual_level=WeatherLevel.DAMP),
        ForecastEntry(lap=10, predicted_level=WeatherLevel.WET, confidence=0.6, actual_level=WeatherLevel.WET),
    ])
    assert forecast.advance(leader_lap=12) == WeatherLevel.WET


def test_visible_forecast_never_leaks_actual_level():
    forecast = WeatherForecast([
        ForecastEntry(lap=5, predicted_level=WeatherLevel.DRY, confidence=0.8, actual_level=WeatherLevel.WET),
    ])
    visible = forecast.visible_forecast()
    assert "actual_level" not in visible[0]
    assert visible[0]["predicted_level"] == "dry"


def test_generate_forecast_produces_requested_number_of_entries():
    forecast = generate_forecast(total_laps=30, num_changes=3, rng=random.Random(1))
    assert len(forecast.schedule) == 3
    laps = [e.lap for e in forecast.schedule]
    assert laps == sorted(laps)
    assert len(set(laps)) == len(laps)


def test_generate_forecast_confidence_is_roughly_calibrated_over_many_draws():
    rng = random.Random(42)
    correct = 0
    total = 2000
    for _ in range(total):
        forecast = generate_forecast(total_laps=50, num_changes=1, rng=rng)
        entry = forecast.schedule[0]
        if entry.predicted_level == entry.actual_level:
            correct += 1
    # Average confidence used is uniform(0.5, 0.9) -> mean 0.7; allow slack.
    rate = correct / total
    assert 0.6 < rate < 0.8


def test_generate_forecast_handles_short_races_gracefully():
    forecast = generate_forecast(total_laps=2, num_changes=3, rng=random.Random(1))
    assert forecast.schedule == []
