"""Tests _run_cu_synced_start, the coroutine behind the GO button that now
presses the CU's own START/ENTER button and waits for its `start` status
field to signal the sequence finished (instead of running an independent
software 5-light countdown) -- see app/network/server.py."""
import asyncio
from types import SimpleNamespace

import pytest

import app.network.server as server_module
from app.cu.base import CUClient
from app.cu.protocol import Status, TimerEvent
from app.race.models import RaceState
from app.race.session import RaceSession, SessionConfig


class FakeCU(CUClient):
    """A CU whose `start` status field is scripted call-by-call, so tests
    can simulate the CU's own light sequence without real timing."""

    def __init__(self, start_sequence: list[int]):
        self._start_sequence = list(start_sequence)
        self.start_call_count = 0

    def describe(self) -> str:
        return "FAKE (test stub)"

    def connect(self) -> None: pass

    def disconnect(self) -> None: pass

    def read_status(self) -> Status:
        value = self._start_sequence.pop(0) if len(self._start_sequence) > 1 else self._start_sequence[0]
        return Status(fuel=(15,), pit=(False,), start=value, mode=0, display=1)

    def poll_timer(self) -> list[TimerEvent]:
        return []

    def set_speed(self, address: int, value: int) -> None: pass

    def set_brake(self, address: int, value: int) -> None: pass

    def set_fuel_display(self, address: int, value: int) -> None: pass

    def start(self) -> None:
        self.start_call_count += 1


def make_fake_app(cu: CUClient) -> SimpleNamespace:
    session = RaceSession(cu, SessionConfig(addresses=[0]))
    session.begin_countdown()
    state = SimpleNamespace(session=session, arduino_bridge=None)
    return SimpleNamespace(state=state)


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    # Real values are tuned for real hardware timing (0.1s poll, 20s
    # timeout); tests use trivially small ones so they run instantly.
    monkeypatch.setattr(server_module, "CU_START_SYNC_POLL_INTERVAL", 0.001)
    monkeypatch.setattr(server_module, "CU_START_SYNC_TIMEOUT_SECONDS", 0.01)


def test_presses_cu_start_button_immediately():
    cu = FakeCU(start_sequence=[0])
    fake_app = make_fake_app(cu)
    asyncio.run(server_module._run_cu_synced_start(fake_app))
    assert cu.start_call_count == 1


def test_go_fires_on_nonzero_to_zero_transition():
    cu = FakeCU(start_sequence=[0, 3, 3, 0, 0])
    fake_app = make_fake_app(cu)
    asyncio.run(server_module._run_cu_synced_start(fake_app))
    assert fake_app.state.session.engine.state == RaceState.RUNNING


def test_falls_back_to_timeout_when_start_field_never_moves():
    # Same as the real mock CU: `start` is always 0, so the nonzero->0
    # transition this heuristic looks for can never happen.
    cu = FakeCU(start_sequence=[0])
    fake_app = make_fake_app(cu)
    asyncio.run(server_module._run_cu_synced_start(fake_app))
    assert fake_app.state.session.engine.state == RaceState.RUNNING
    assert any("timed out" in line for line in fake_app.state.session.debug_log)


def test_aborted_countdown_does_not_call_go():
    cu = FakeCU(start_sequence=[0, 3, 3])
    fake_app = make_fake_app(cu)
    fake_app.state.session.engine.stop(fake_app.state.session.clock())  # abort out of COUNTDOWN
    asyncio.run(server_module._run_cu_synced_start(fake_app))
    assert fake_app.state.session.engine.state != RaceState.RUNNING
