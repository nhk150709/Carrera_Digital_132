import pytest

from app.race.engine import RaceEngine
from app.race.models import RaceMode


def test_qualifying_ranks_by_best_lap_like_time_attack():
    engine = RaceEngine(addresses=[0, 1], mode=RaceMode.QUALIFYING)
    engine.go(now=0.0)
    engine.handle_timer_event(0, timestamp=0.0, sector=0)  # baseline
    engine.handle_timer_event(1, timestamp=0.0, sector=0)  # baseline
    engine.handle_timer_event(0, timestamp=10.0, sector=0)
    engine.handle_timer_event(1, timestamp=9.0, sector=0)
    ranking = engine.rankings()
    assert ranking[0].address == 1


def test_grid_order_fastest_first():
    engine = RaceEngine(addresses=[0, 1, 2], mode=RaceMode.QUALIFYING)
    engine.go(now=0.0)
    engine.handle_timer_event(0, timestamp=0.0, sector=0)  # baseline
    engine.handle_timer_event(1, timestamp=0.0, sector=0)  # baseline
    engine.handle_timer_event(0, timestamp=12.0, sector=0)
    engine.handle_timer_event(1, timestamp=9.0, sector=0)
    # car 2 never sets a lap time
    assert engine.grid_order() == [1, 0, 2]


def test_grid_order_with_no_laps_falls_back_to_address_order():
    engine = RaceEngine(addresses=[2, 0, 1])
    assert engine.grid_order() == [0, 1, 2]
