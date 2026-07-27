from app.race.models import CarState
from app.race.penalties import PenaltyEngine, JUMP_START_PENALTY_SECONDS, RACE_STOP_PENALTY_SECONDS


def test_jump_start_flags_and_penalizes():
    car = CarState(address=0)
    engine = PenaltyEngine()
    engine.jump_start(car, timestamp=1.0)
    assert car.jump_start is True
    assert car.total_penalty_seconds == JUMP_START_PENALTY_SECONDS


def test_multiple_penalties_accumulate():
    car = CarState(address=0)
    engine = PenaltyEngine()
    engine.jump_start(car, timestamp=1.0)
    engine.race_stopped_by(car, timestamp=5.0)
    engine.custom(car, 2.5, "cutting_track", timestamp=10.0)
    assert car.total_penalty_seconds == JUMP_START_PENALTY_SECONDS + RACE_STOP_PENALTY_SECONDS + 2.5
    assert [p.reason for p in car.penalties] == ["jump_start", "triggered_stop", "cutting_track"]


def test_penalty_affects_elapsed_time():
    car = CarState(address=0)
    from app.race.models import LapRecord
    car.laps.append(LapRecord(lap_number=1, lap_time=10.0, timestamp=10.0))
    assert car.elapsed_time == 10.0
    PenaltyEngine().custom(car, 5.0, "test", timestamp=10.0)
    assert car.elapsed_time == 15.0
