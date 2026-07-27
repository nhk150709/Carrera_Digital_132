import random

from app.race.safety_car import SafetyCarConfig, SafetyCarSystem


def test_inactive_by_default_does_not_cap_speed():
    system = SafetyCarSystem()
    assert system.cap_speed(15) == 15


def test_trigger_caps_field_speed():
    system = SafetyCarSystem(config=SafetyCarConfig(field_speed_cap=5))
    system.trigger()
    assert system.cap_speed(15) == 5
    assert system.cap_speed(3) == 3  # already below cap, unaffected


def test_end_removes_cap():
    system = SafetyCarSystem()
    system.trigger()
    system.end()
    assert system.cap_speed(15) == 15


def test_physically_present_flag_is_just_data_the_caller_uses():
    virtual = SafetyCarSystem(physically_present=False)
    real = SafetyCarSystem(physically_present=True)
    assert virtual.physically_present is False
    assert real.physically_present is True


def test_random_trigger_respects_probability():
    system = SafetyCarSystem(config=SafetyCarConfig(random_trigger_chance_per_lap=1.0))
    assert system.maybe_random_trigger(rng=random.Random(1)) is True
    assert system.active is True


def test_random_trigger_never_fires_at_zero_probability():
    system = SafetyCarSystem(config=SafetyCarConfig(random_trigger_chance_per_lap=0.0))
    for _ in range(50):
        system.maybe_random_trigger(rng=random.Random())
    assert system.active is False
