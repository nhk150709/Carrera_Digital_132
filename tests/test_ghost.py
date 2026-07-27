from app.race.ghost import GhostComparator
from app.race.recorder import EventType, RecordedEvent, Recording


def make_recording():
    events = [
        RecordedEvent(t=10.0, address=0, type=EventType.LAP, value=1),
        RecordedEvent(t=21.0, address=0, type=EventType.LAP, value=2),
    ]
    return Recording(name="ghost", address=0, events=events)


def test_negative_delta_means_faster_than_ghost():
    ghost = GhostComparator(make_recording())
    assert ghost.delta_at_lap(1, elapsed_at_lap=9.0) == -1.0


def test_positive_delta_means_slower_than_ghost():
    ghost = GhostComparator(make_recording())
    assert ghost.delta_at_lap(2, elapsed_at_lap=22.0) == 1.0


def test_unknown_lap_returns_none():
    ghost = GhostComparator(make_recording())
    assert ghost.delta_at_lap(5, elapsed_at_lap=50.0) is None
