from app.race.pace_car import PaceCarPlayback, MIN_COMMAND_INTERVAL
from app.race.recorder import EventType, Recording, RecordedEvent


def make_recording():
    events = [
        RecordedEvent(t=0.0, address=6, type=EventType.THROTTLE, value=0.2),
        RecordedEvent(t=1.0, address=6, type=EventType.THROTTLE, value=0.6),
        RecordedEvent(t=2.0, address=6, type=EventType.THROTTLE, value=1.0),
    ]
    return Recording(name="test", address=6, events=events)


def test_playback_sends_scaled_speed():
    playback = PaceCarPlayback(recording=make_recording(), address=7)
    sent = []
    playback.tick(0.0, lambda addr, val: sent.append((addr, val)))
    assert sent == [(7, 3)]  # 0.2 * 15 rounded


def test_playback_respects_rate_limit():
    playback = PaceCarPlayback(recording=make_recording())
    sent = []
    playback.tick(0.0, lambda a, v: sent.append((a, v)))
    playback.tick(0.01, lambda a, v: sent.append((a, v)))  # too soon
    assert len(sent) == 1


def test_playback_advances_through_events():
    playback = PaceCarPlayback(recording=make_recording())
    sent = []
    t = 0.0
    while not playback.finished and t < 5.0:
        playback.tick(t, lambda a, v: sent.append((a, v)))
        t += MIN_COMMAND_INTERVAL
    values = [v for _, v in sent]
    assert values[0] == 3   # ~0.2 * 15
    assert values[-1] == 15  # last event value 1.0 * 15
    assert playback.finished


def test_speed_scale_faster_pace_car_finishes_sooner():
    slow = PaceCarPlayback(recording=make_recording(), speed_scale=1.0)
    fast = PaceCarPlayback(recording=make_recording(), speed_scale=2.0)
    t = 0.0
    while not fast.finished and t < 10.0:
        fast.tick(t, lambda a, v: None)
        t += MIN_COMMAND_INTERVAL
    fast_finish_t = t
    t = 0.0
    while not slow.finished and t < 10.0:
        slow.tick(t, lambda a, v: None)
        t += MIN_COMMAND_INTERVAL
    assert fast_finish_t < t
