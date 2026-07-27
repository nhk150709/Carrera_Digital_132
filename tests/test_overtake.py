from app.race.overtake import OvertakeConfig, OvertakeSystem


def test_trigger_activates_and_expires():
    system = OvertakeSystem(OvertakeConfig(duration_seconds=5.0, cooldown_seconds=10.0))
    assert system.trigger(0, now=0.0) is True
    assert system.is_active(0, now=2.0) is True
    assert system.is_active(0, now=5.1) is False


def test_cannot_retrigger_while_active():
    system = OvertakeSystem(OvertakeConfig(duration_seconds=5.0, cooldown_seconds=10.0))
    system.trigger(0, now=0.0)
    assert system.trigger(0, now=2.0) is False


def test_cannot_trigger_during_cooldown():
    system = OvertakeSystem(OvertakeConfig(duration_seconds=5.0, cooldown_seconds=10.0))
    system.trigger(0, now=0.0)
    assert system.is_on_cooldown(0, now=6.0) is True
    assert system.trigger(0, now=6.0) is False


def test_can_trigger_again_after_cooldown_expires():
    system = OvertakeSystem(OvertakeConfig(duration_seconds=5.0, cooldown_seconds=10.0))
    system.trigger(0, now=0.0)
    assert system.trigger(0, now=15.1) is True


def test_cars_are_independent():
    system = OvertakeSystem()
    system.trigger(0, now=0.0)
    assert system.is_active(1, now=0.0) is False
