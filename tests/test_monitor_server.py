import logging

import pytest
from fastapi.testclient import TestClient

import app.network.server as server_module
from app.cu.base import CUClient
from app.cu.mock_client import MockCUClient
from app.cu.protocol import (
    FUEL_MODE,
    LAP_COUNTER_MODE,
    PIT_LANE_MODE,
    REAL_MODE,
    Status,
    TimerEvent,
)


def test_build_cu_client_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("CARRERA_RMS_CU_DEVICE", raising=False)
    cu, device = server_module.build_cu_client()
    assert isinstance(cu, MockCUClient)
    assert device == "mock"


def test_build_cu_client_uses_real_when_device_set(monkeypatch):
    monkeypatch.setenv("CARRERA_RMS_CU_DEVICE", "aa:bb:cc:dd:ee:ff")
    cu, device = server_module.build_cu_client()
    assert cu.describe().startswith("REAL")
    assert device == "aa:bb:cc:dd:ee:ff"


def test_decode_mode_reports_set_flags():
    assert server_module._decode_mode(0) == []
    assert server_module._decode_mode(FUEL_MODE | PIT_LANE_MODE) == ["FUEL_MODE", "PIT_LANE_MODE"]
    assert server_module._decode_mode(REAL_MODE | LAP_COUNTER_MODE) == ["REAL_MODE", "LAP_COUNTER_MODE"]


def test_raw_log_handler_captures_records():
    handler = server_module.RawLogHandler(maxlen=10)
    logger = logging.getLogger("test.raw.capture")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.debug("Received message %r", b"\x01\x02")
    assert len(handler.entries) == 1
    assert "Received message" in handler.entries[0]["message"]
    logger.removeHandler(handler)


def test_raw_log_handler_is_bounded():
    handler = server_module.RawLogHandler(maxlen=3)
    logger = logging.getLogger("test.raw.bounded")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    for i in range(10):
        logger.debug("message %d", i)
    assert len(handler.entries) == 3
    logger.removeHandler(handler)


class FakeCU(CUClient):
    """Scriptable CU stub for MonitorState tests."""

    def __init__(self, timer_events=None, status=None, fail_poll=False, fail_connect=False):
        self._timer_events = timer_events or []
        self._status = status
        self.fail_poll = fail_poll
        self.fail_connect = fail_connect
        self.connect_calls = 0

    def describe(self): return "FAKE (test stub)"

    def connect(self):
        self.connect_calls += 1
        if self.fail_connect:
            raise RuntimeError("simulated connect failure")

    def disconnect(self): pass

    def read_status(self):
        if self._status is None:
            raise RuntimeError("no Status seen yet")
        return self._status

    def poll_timer(self):
        if self.fail_poll:
            raise RuntimeError("simulated poll failure")
        events, self._timer_events = self._timer_events, []
        return events

    def set_speed(self, address, value): pass
    def set_brake(self, address, value): pass
    def set_fuel_display(self, address, value): pass
    def start(self): pass


def make_state(cu: CUClient) -> server_module.MonitorState:
    state = server_module.MonitorState.__new__(server_module.MonitorState)
    state.cu = cu
    state.requested_device = "test"
    state.connected = False
    state.last_error = None
    state.last_status = None
    state.timer_log = __import__("collections").deque(maxlen=10)
    state.connect_attempts = 0
    state._last_connect_attempt = 0.0
    return state


def test_try_connect_success_marks_connected():
    state = make_state(FakeCU())
    state.try_connect(force=True)
    assert state.connected is True
    assert state.last_error is None


def test_try_connect_failure_sets_last_error():
    state = make_state(FakeCU(fail_connect=True))
    state.try_connect(force=True)
    assert state.connected is False
    assert "simulated connect failure" in state.last_error


def test_try_connect_respects_retry_interval_unless_forced():
    cu = FakeCU()
    state = make_state(cu)
    state.try_connect(force=True)
    assert cu.connect_calls == 1
    state.connected = False  # pretend it dropped
    state.try_connect()  # not forced, too soon -- should be throttled
    assert cu.connect_calls == 1
    state.try_connect(force=True)
    assert cu.connect_calls == 2


def test_poll_once_populates_status_and_timer_log():
    status = Status(fuel=(15, 10), pit=(False, True), start=3, mode=PIT_LANE_MODE, display=2)
    events = [TimerEvent(address=0, timestamp=1.5, sector=0), TimerEvent(address=1, timestamp=2.0, sector=2)]
    cu = FakeCU(timer_events=events, status=status)
    state = make_state(cu)
    state.connected = True
    state.poll_once()
    assert state.last_status["fuel"] == [15, 10]
    assert state.last_status["pit"] == [False, True]
    assert state.last_status["mode_flags"] == ["PIT_LANE_MODE"]
    assert len(state.timer_log) == 2
    # appendleft() during the loop -- most-recently-processed event ends
    # up at index 0 (newest first), so the second event (sector=2) is
    # last in and therefore first in the deque.
    assert state.timer_log[0]["sector_label"] == "check lane 2"
    assert state.timer_log[1]["sector_label"] == "start/finish"


def test_poll_once_marks_disconnected_on_failure():
    cu = FakeCU(fail_poll=True)
    state = make_state(cu)
    state.connected = True
    state.poll_once()
    assert state.connected is False
    assert "simulated poll failure" in state.last_error


def test_poll_once_tolerates_no_status_yet():
    cu = FakeCU(status=None)  # read_status() raises RuntimeError until a Status is seen
    state = make_state(cu)
    state.connected = True
    state.poll_once()  # must not raise, and must not mark disconnected
    assert state.connected is True
    assert state.last_status is None


def test_snapshot_shape():
    state = make_state(MockCUClient(addresses=[0]))
    state.connected = True
    snap = state.snapshot()
    assert set(snap.keys()) == {
        "backend", "requested_device", "connected", "last_error",
        "connect_attempts", "status", "timer_log", "raw_log",
    }


def make_client() -> TestClient:
    return TestClient(server_module.app)


def test_index_serves_ui():
    with make_client() as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Carrera CU Monitor" in resp.content


def test_state_endpoint_reports_mock_backend():
    with make_client() as client:
        resp = client.get("/api/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["backend"].startswith("MOCK")
        assert data["requested_device"] == "mock"


def test_reconnect_endpoint():
    with make_client() as client:
        resp = client.post("/api/reconnect")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


def test_websocket_sends_initial_snapshot():
    with make_client() as client:
        with client.websocket_connect("/ws") as ws:
            data = ws.receive_json()
            assert "backend" in data
            assert "connected" in data
