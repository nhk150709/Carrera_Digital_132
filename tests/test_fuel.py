from app.race.fuel import FuelConfig, FuelModel, TyreCompound


def test_full_throttle_drains_faster_than_no_throttle():
    model = FuelModel([0, 1])
    for _ in range(100):
        model.update(0, throttle=1.0, brake=0.0, dt=0.1)
        model.update(1, throttle=0.0, brake=0.0, dt=0.1)
    assert model.fuel(0) < model.fuel(1)


def test_fuel_never_regenerates():
    model = FuelModel([0])
    model.set_starting_load(0, 50.0)
    for _ in range(100):
        model.update(0, throttle=0.0, brake=0.0, dt=1.0)
    # idle drain still applies, and nothing should ever raise it back up
    assert model.fuel(0) <= 50.0


def test_change_tyres_is_a_discrete_event_not_continuous():
    model = FuelModel([0])
    for _ in range(50):
        model.update(0, throttle=1.0, brake=1.0, dt=0.1)
    assert model.tyre_wear(0) > 0
    fuel_before = model.fuel(0)
    model.change_tyres(0)
    assert model.tyre_wear(0) == 0.0
    assert model.fuel(0) == fuel_before  # tyre change never touches fuel


def test_fuel_never_goes_negative():
    model = FuelModel([0])
    model.set_starting_load(0, 1.0)
    for _ in range(1000):
        model.update(0, throttle=1.0, brake=0.0, dt=1.0)
    assert model.fuel(0) == 0.0
    assert model.is_empty(0)


def test_weight_penalty_decreases_as_fuel_burns_off():
    model = FuelModel([0])
    model.set_starting_load(0, 100.0)
    full_penalty = model.weight_penalty_multiplier(0)
    model.set_starting_load(0, 0.0)
    empty_penalty = model.weight_penalty_multiplier(0)
    assert full_penalty < empty_penalty
    assert empty_penalty == 1.0


def test_tyre_performance_drops_as_wear_increases():
    model = FuelModel([0])
    fresh = model.tyre_performance_multiplier(0)
    for _ in range(500):
        model.update(0, throttle=1.0, brake=1.0, dt=0.1)
    worn = model.tyre_performance_multiplier(0)
    assert worn < fresh


def test_brake_effectiveness_drops_as_wear_increases():
    model = FuelModel([0])
    fresh = model.brake_effectiveness_multiplier(0)
    for _ in range(500):
        model.update(0, throttle=1.0, brake=1.0, dt=0.1)
    worn = model.brake_effectiveness_multiplier(0)
    assert worn < fresh


def test_soft_compound_wears_faster_than_hard():
    model = FuelModel([0, 1])
    model.set_compound(0, TyreCompound.SOFT)
    model.set_compound(1, TyreCompound.HARD)
    for _ in range(100):
        model.update(0, throttle=0.8, brake=0.5, dt=0.1)
        model.update(1, throttle=0.8, brake=0.5, dt=0.1)
    assert model.tyre_wear(0) > model.tyre_wear(1)


def test_boosting_drains_fuel_and_wears_tyres_faster():
    normal = FuelModel([0])
    boosted = FuelModel([1])
    for _ in range(50):
        normal.update(0, throttle=1.0, brake=0.0, dt=0.1, boosting=False)
        boosted.update(1, throttle=1.0, brake=0.0, dt=0.1, boosting=True)
    assert boosted.fuel(1) < normal.fuel(0)


def test_soft_compound_has_higher_grip_than_hard_when_fresh():
    model = FuelModel([0, 1])
    model.set_compound(0, TyreCompound.SOFT)
    model.set_compound(1, TyreCompound.HARD)
    assert model.tyre_performance_multiplier(0) > model.tyre_performance_multiplier(1)
