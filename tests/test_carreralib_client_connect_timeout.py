"""Tests for _construct_control_unit_with_timeout -- the fix for a real bug
hit on real hardware: carreralib.ble.BleakThread.start() waits on a
threading.Event with no timeout of its own, so when the underlying BLE
connect fails/times out inside carreralib's own background thread, the
calling thread (our connect()) blocked forever with no way to retry or
even report an error. See app/cu/carreralib_client.py's docstring on
_construct_control_unit_with_timeout for the full story.
"""
import time

import pytest
from bleak.exc import BleakDeviceNotFoundError

from app.cu.carreralib_client import CarreralibCUClient, _construct_control_unit_with_timeout


def test_returns_control_unit_when_construction_is_fast(monkeypatch):
    sentinel = object()
    monkeypatch.setattr("carreralib.ControlUnit", lambda device: sentinel)
    assert _construct_control_unit_with_timeout("EF:C4:35:38:1A:0B", timeout=1.0) is sentinel


def test_propagates_exception_raised_during_construction(monkeypatch):
    def boom(device):
        raise BleakDeviceNotFoundError(device, "not found")

    monkeypatch.setattr("carreralib.ControlUnit", boom)
    with pytest.raises(BleakDeviceNotFoundError):
        _construct_control_unit_with_timeout("EF:C4:35:38:1A:0B", timeout=1.0)


def test_raises_timeout_error_instead_of_hanging_forever(monkeypatch):
    # Simulates the real-hardware failure mode: carreralib's constructor
    # never returns and never raises (the background BLE thread died
    # silently on its own). Must not block the test suite.
    def hangs_forever(device):
        time.sleep(5)
        return object()

    monkeypatch.setattr("carreralib.ControlUnit", hangs_forever)
    with pytest.raises(TimeoutError, match="did not complete within"):
        _construct_control_unit_with_timeout("EF:C4:35:38:1A:0B", timeout=0.05)


def test_connect_retries_after_timeout_then_succeeds(monkeypatch):
    # connect()'s own retry loop must treat a hung/timed-out BLE connect
    # attempt the same way it already treats BleakDeviceNotFoundError: log
    # it and try again, not propagate immediately.
    calls = {"n": 0}

    def flaky(device):
        calls["n"] += 1
        if calls["n"] < 2:
            time.sleep(5)
            return object()  # never reached within the timeout
        return object()

    monkeypatch.setattr("carreralib.ControlUnit", flaky)
    monkeypatch.setattr("app.cu.carreralib_client._warm_ble_cache", lambda address: None)
    monkeypatch.setattr("app.cu.carreralib_client._construct_control_unit_with_timeout",
                         lambda device, timeout=15.0: _construct_control_unit_with_timeout(device, timeout=0.05))

    client = CarreralibCUClient(device="EF:C4:35:38:1A:0B")
    client.connect(ble_connect_attempts=3)
    assert calls["n"] == 2
