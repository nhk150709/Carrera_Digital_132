import pytest

from app.race.engine import RaceEngine, RaceEngineConfig
from app.race.models import RaceMode, RaceState


def test_state_machine_happy_path():
    engine = RaceEngine(addresses=[0, 1])
    assert engine.state == RaceState.IDLE
    engine.begin_countdown(now=0.0)
    assert engine.state == RaceState.COUNTDOWN
    engine.go(now=3.0)
    assert engine.state == RaceState.RUNNING
    engine.stop(now=10.0)
    assert engine.state == RaceState.PAUSED
    engine.resume(now=11.0)
    assert engine.state == RaceState.RUNNING
    engine.finish(now=20.0)
    assert engine.state == RaceState.FINISHED


def test_go_seeds_baseline_so_first_crossing_is_lap_one():
    engine = RaceEngine(addresses=[0])
    engine.go(now=100.0)
    record = engine.handle_timer_event(address=0, timestamp=112.5, sector=0)
    assert record is not None
    assert record.lap_number == 1
    assert record.lap_time == pytest.approx(12.5)


def test_lap_time_computed_from_consecutive_crossings():
    engine = RaceEngine(addresses=[0])
    engine.go(now=100.0)
    engine.handle_timer_event(0, timestamp=112.5, sector=0)  # lap 1: 12.5s
    record = engine.handle_timer_event(0, timestamp=120.0, sector=0)  # lap 2: 7.5s
    assert record.lap_number == 2
    assert record.lap_time == pytest.approx(7.5)


def test_nonzero_sector_does_not_complete_a_lap():
    engine = RaceEngine(addresses=[0])
    engine.go(now=0.0)
    result = engine.handle_timer_event(0, timestamp=5.0, sector=1)
    assert result is None
    assert engine.cars[0].lap_count == 0


def test_sector_split_does_not_reset_lap_baseline():
    engine = RaceEngine(addresses=[0])
    engine.go(now=0.0)
    engine.handle_timer_event(0, timestamp=5.0, sector=1)  # mid-lap split, ignored for laps
    record = engine.handle_timer_event(0, timestamp=10.0, sector=0)
    assert record.lap_time == pytest.approx(10.0)  # still measured from go(), not from the split


def test_timer_events_ignored_when_not_running():
    engine = RaceEngine(addresses=[0])
    result = engine.handle_timer_event(0, timestamp=5.0, sector=0)
    assert result is None


def test_jump_start_only_during_countdown():
    engine = RaceEngine(addresses=[0])
    engine.begin_countdown(now=0.0)
    engine.report_early_movement(0, now=1.0)
    assert engine.cars[0].jump_start is True

    engine2 = RaceEngine(addresses=[0])
    engine2.go(now=0.0)
    engine2.report_early_movement(0, now=1.0)
    assert engine2.cars[0].jump_start is False


def test_race_mode_ranking_by_laps_then_time():
    engine = RaceEngine(addresses=[0, 1], mode=RaceMode.RACE)
    engine.go(now=0.0)
    # Car 0: two laps, 10s and 11s.
    engine.handle_timer_event(0, timestamp=10.0, sector=0)
    engine.handle_timer_event(0, timestamp=21.0, sector=0)
    # Car 1: one lap, 9s (fewer laps, should still rank behind).
    engine.handle_timer_event(1, timestamp=9.0, sector=0)

    ranking = engine.rankings()
    assert [r.address for r in ranking] == [0, 1]
    assert ranking[0].position == 1
    assert ranking[1].laps_down == 1
    assert ranking[1].gap_to_leader is None  # not on the same lap


def test_race_mode_gap_when_same_lap_count():
    engine = RaceEngine(addresses=[0, 1], mode=RaceMode.RACE)
    engine.go(now=0.0)
    engine.handle_timer_event(0, timestamp=10.0, sector=0)
    engine.handle_timer_event(1, timestamp=12.0, sector=0)

    ranking = engine.rankings()
    leader, second = ranking[0], ranking[1]
    assert leader.address == 0
    assert second.laps_down == 0
    assert second.gap_to_leader == pytest.approx(2.0)


def test_penalty_changes_race_ranking():
    engine = RaceEngine(addresses=[0, 1], mode=RaceMode.RACE)
    engine.go(now=0.0)
    engine.handle_timer_event(0, timestamp=10.0, sector=0)  # car 0: 10s
    engine.handle_timer_event(1, timestamp=11.0, sector=0)  # car 1: 11s, behind

    assert engine.rankings()[0].address == 0
    engine.add_penalty(0, seconds=5.0, reason="test", now=10.0)  # 10 + 5 = 15 > 11
    ranking = engine.rankings()
    assert ranking[0].address == 1


def test_time_attack_ranking_by_best_lap():
    engine = RaceEngine(addresses=[0, 1], mode=RaceMode.TIME_ATTACK)
    engine.go(now=0.0)
    engine.handle_timer_event(0, timestamp=10.0, sector=0)  # 10s lap
    engine.handle_timer_event(0, timestamp=18.0, sector=0)  # 8s lap (best)
    engine.handle_timer_event(1, timestamp=9.0, sector=0)   # 9s lap (best for car 1)

    ranking = engine.rankings()
    assert ranking[0].address == 0
    assert ranking[0].best_lap == pytest.approx(8.0)
    assert ranking[1].gap_to_leader == pytest.approx(1.0)


def test_target_laps_finishes_race_when_leader_reaches_target():
    engine = RaceEngine(addresses=[0], config=RaceEngineConfig(target_laps=2))
    engine.go(now=0.0)
    engine.handle_timer_event(0, timestamp=10.0, sector=0)
    assert engine.state == RaceState.RUNNING
    engine.handle_timer_event(0, timestamp=20.0, sector=0)
    assert engine.state == RaceState.FINISHED
    assert engine.finish_order == [0]


def test_resume_rebaselines_crossing_timestamp_so_pause_not_counted():
    engine = RaceEngine(addresses=[0])
    engine.go(now=0.0)
    engine.stop(now=5.0)
    engine.resume(now=50.0)  # 45s pause
    record = engine.handle_timer_event(0, timestamp=60.0, sector=0)
    assert record.lap_time == pytest.approx(10.0)
