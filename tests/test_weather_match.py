from app.race.fuel import TyreCompound, weather_match_multiplier
from app.race.models import WeatherLevel


def test_matched_compound_gets_bonus():
    assert weather_match_multiplier(TyreCompound.SOFT, WeatherLevel.DRY) > 1.0
    assert weather_match_multiplier(TyreCompound.MEDIUM, WeatherLevel.DAMP) > 1.0
    assert weather_match_multiplier(TyreCompound.HARD, WeatherLevel.WET) > 1.0


def test_worst_mismatch_is_worse_than_one_step_off():
    one_step = weather_match_multiplier(TyreCompound.MEDIUM, WeatherLevel.WET)
    two_steps = weather_match_multiplier(TyreCompound.SOFT, WeatherLevel.WET)
    assert two_steps < one_step < 1.0 + 1e-9


def test_multiplier_never_drops_below_floor():
    assert weather_match_multiplier(TyreCompound.SOFT, WeatherLevel.WET) >= 0.4
