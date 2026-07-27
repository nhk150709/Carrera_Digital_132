import random

from app.race.reliability import ReliabilityConfig, ReliabilitySystem


def test_zero_chance_never_breaks_down():
    system = ReliabilitySystem(ReliabilityConfig(breakdown_chance_per_second=0.0))
    for _ in range(100):
        system.maybe_break_down(0, dt=1.0, rng=random.Random())
    assert not system.is_broken_down(0)


def test_certain_chance_breaks_down_immediately():
    system = ReliabilitySystem(ReliabilityConfig(breakdown_chance_per_second=1.0))
    assert system.maybe_break_down(0, dt=1.0, rng=random.Random(1)) is True
    assert system.is_broken_down(0)


def test_repair_only_progresses_while_in_pit():
    system = ReliabilitySystem(ReliabilityConfig(repair_seconds=10.0))
    system._broken_down.add(0)
    system._repaired_seconds[0] = 0.0

    system.tick_repair(0, in_pit=False, dt=5.0)
    assert system.repair_progress(0) == 0.0

    system.tick_repair(0, in_pit=True, dt=5.0)
    assert system.repair_progress(0) == 0.5


def test_repair_pauses_not_resets_when_leaving_pit_early():
    system = ReliabilitySystem(ReliabilityConfig(repair_seconds=10.0))
    system._broken_down.add(0)
    system._repaired_seconds[0] = 0.0

    system.tick_repair(0, in_pit=True, dt=4.0)
    system.tick_repair(0, in_pit=False, dt=100.0)  # left the pit, time passes
    system.tick_repair(0, in_pit=True, dt=6.0)
    assert system.repair_progress(0) == 1.0
    assert not system.is_broken_down(0)


def test_repair_completes_and_clears_broken_down_flag():
    system = ReliabilitySystem(ReliabilityConfig(repair_seconds=5.0))
    system._broken_down.add(0)
    system._repaired_seconds[0] = 0.0
    completed = system.tick_repair(0, in_pit=True, dt=5.0)
    assert completed is True
    assert not system.is_broken_down(0)
