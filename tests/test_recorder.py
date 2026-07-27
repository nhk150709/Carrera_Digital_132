from app.race.recorder import EventType, InputRecorder, Recording


def test_record_relative_timestamps(tmp_path):
    recorder = InputRecorder(storage_dir=tmp_path)
    recorder.start(address=0, name="lap1", now=100.0)
    recorder.record(0, EventType.THROTTLE, 0.5, now=100.5)
    recorder.record(0, EventType.THROTTLE, 1.0, now=101.0)
    recording = recorder.stop(0)
    assert recording is not None
    assert [e.t for e in recording.events] == [0.5, 1.0]
    assert not recorder.is_recording(0)


def test_save_and_load_round_trip(tmp_path):
    recorder = InputRecorder(storage_dir=tmp_path)
    recorder.start(address=6, name="ghost", now=0.0)
    recorder.record(6, EventType.THROTTLE, 0.8, now=1.0)
    recorder.record(6, EventType.LAP, 1, now=12.0)
    recording = recorder.stop(6)
    path = recorder.save(recording)
    assert path.exists()

    loaded = recorder.load("ghost")
    assert loaded.address == 6
    assert len(loaded.events) == 2
    assert loaded.events[0].type == EventType.THROTTLE
    assert loaded.events[1].type == EventType.LAP


def test_list_recordings(tmp_path):
    recorder = InputRecorder(storage_dir=tmp_path)
    recorder.start(0, "a", now=0.0)
    recorder.save(recorder.stop(0))
    recorder.start(0, "b", now=0.0)
    recorder.save(recorder.stop(0))
    assert recorder.list_recordings() == ["a", "b"]


def test_recording_not_active_ignored(tmp_path):
    recorder = InputRecorder(storage_dir=tmp_path)
    recorder.record(0, EventType.THROTTLE, 1.0, now=5.0)  # no active recording
    assert recorder.stop(0) is None
