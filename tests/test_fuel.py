from app.race.fuel import FuelConfig, FuelModel


def test_full_throttle_drains_faster_than_no_throttle():
    model = FuelModel([0, 1])
    for _ in range(100):
        model.update(0, throttle=1.0, brake=0.0, dt=0.1)
        model.update(1, throttle=0.0, brake=0.0, dt=0.1)
    assert model.fuel(0) < model.fuel(1)


def test_worn_tyres_increase_drain_rate():
    cfg = FuelConfig()
    model = FuelModel([0, 1], config=cfg)
    # Wear car 1's tyres heavily first.
    for _ in range(200):
        model.update(1, throttle=1.0, brake=1.0, dt=0.1)
    assert model.tyre_wear(1) > 0
    fuel_before = {0: model.fuel(0), 1: model.fuel(1)}
    model.set_fuel(0, cfg.fuel_capacity)
    model.set_fuel(1, cfg.fuel_capacity)
    for _ in range(50):
        model.update(0, throttle=0.5, brake=0.0, dt=0.1)
        model.update(1, throttle=0.5, brake=0.0, dt=0.1)
    assert model.fuel(1) < model.fuel(0)
    assert fuel_before  # sanity: dict used


def test_pit_refuels_and_resets_tyre_wear():
    model = FuelModel([0])
    model.set_fuel(0, 10.0)
    for _ in range(50):
        model.update(0, throttle=1.0, brake=1.0, dt=0.1)
    assert model.tyre_wear(0) > 0
    for _ in range(50):
        model.update(0, throttle=0.0, brake=0.0, dt=0.1, in_pit=True)
    assert model.fuel(0) == FuelConfig().fuel_capacity
    assert model.tyre_wear(0) == 0.0


def test_fuel_never_goes_negative():
    model = FuelModel([0])
    model.set_fuel(0, 1.0)
    for _ in range(1000):
        model.update(0, throttle=1.0, brake=0.0, dt=1.0)
    assert model.fuel(0) == 0.0
    assert model.is_empty(0)
