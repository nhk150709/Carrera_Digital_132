from app.race.fuel import FuelConfig, TyreCompound
from app.race.strategy import RECOMMENDED_TYRE_CHANGE_WEAR, project_plan, recommend_strategy


def test_recommended_fuel_load_covers_the_full_race_distance():
    plan = recommend_strategy(address=0, total_laps=20, avg_lap_seconds=6.0)
    # Simulate the exact typical-driving assumption used to derive it and
    # confirm the tank doesn't run dry before the finish.
    projected = project_plan(plan, total_laps=20, avg_lap_seconds=6.0)
    assert projected[-1].fuel >= 0.0
    assert projected[10].fuel > 0.0  # not dry halfway through either


def test_recommended_pit_lap_is_within_race_distance():
    plan = recommend_strategy(address=0, total_laps=20, avg_lap_seconds=6.0)
    assert plan.planned_pit_laps
    pit_lap = plan.planned_pit_laps[0]
    assert 1 <= pit_lap < 20


def test_recommended_pit_lap_roughly_matches_wear_threshold_crossing():
    total_laps, avg_lap = 20, 6.0
    plan = recommend_strategy(address=0, total_laps=total_laps, avg_lap_seconds=avg_lap)
    cfg = FuelConfig()
    from app.race.fuel import COMPOUND_PROFILES
    wear_per_lap = (0.75 * cfg.accel_wear_per_second + 0.35 * cfg.brake_wear_per_second) \
        * COMPOUND_PROFILES[TyreCompound.MEDIUM].wear_rate_multiplier * avg_lap
    expected_lap = round(RECOMMENDED_TYRE_CHANGE_WEAR / wear_per_lap)
    assert plan.planned_pit_laps[0] == max(1, min(total_laps - 1, expected_lap))


def test_short_race_still_produces_a_usable_plan():
    plan = recommend_strategy(address=0, total_laps=2, avg_lap_seconds=6.0)
    assert plan.fuel_load > 0
    assert plan.compound == TyreCompound.MEDIUM
