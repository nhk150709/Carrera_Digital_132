"""Tests read_status()/poll_timer()'s Status-caching behavior, which
avoids a second poll() round-trip per tick -- see the docstring on
read_status() in app/cu/carreralib_client.py for why that matters (the CU
has one request/response channel; calling poll() twice per tick would
race against poll_timer()'s own call).
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.cu.carreralib_client import CarreralibCUClient


def make_connected_client() -> CarreralibCUClient:
    client = CarreralibCUClient(device="/dev/ttyUSB0")
    with patch("carreralib.ControlUnit"):
        client.connect()
    return client


def test_read_status_raises_before_any_status_seen():
    client = make_connected_client()
    with pytest.raises(RuntimeError, match="no Status message"):
        client.read_status()


def test_poll_timer_caches_status_without_returning_it_as_a_timer_event():
    client = make_connected_client()
    status = SimpleNamespace(fuel=[10] * 8, pit=[False] * 8, start=0, mode=0, display=6)
    client._cu.poll.return_value = status

    events = client.poll_timer()

    assert events == []  # a Status isn't a Timer event
    cached = client.read_status()
    assert cached.fuel == (10,) * 8
    assert cached.display == 6


def test_read_status_does_not_call_poll_itself():
    client = make_connected_client()
    status = SimpleNamespace(fuel=[5] * 8, pit=[False] * 8, start=0, mode=0, display=6)
    client._cu.poll.return_value = status
    client.poll_timer()
    client._cu.poll.reset_mock()

    client.read_status()

    client._cu.poll.assert_not_called()


def test_poll_timer_still_returns_timer_events_and_leaves_status_cache_untouched():
    client = make_connected_client()
    status = SimpleNamespace(fuel=[8] * 8, pit=[False] * 8, start=0, mode=0, display=6)
    client._cu.poll.return_value = status
    client.poll_timer()

    timer = SimpleNamespace(address=0, timestamp=1000, sector=1)
    client._cu.poll.return_value = timer
    events = client.poll_timer()

    assert len(events) == 1
    assert events[0].address == 0
    assert events[0].sector == 0  # sector 1 (wire) -> 0 (this app's "lap" convention)
    assert client.read_status().fuel == (8,) * 8  # unchanged, still the last real Status


def test_disconnect_clears_cached_status():
    client = make_connected_client()
    status = SimpleNamespace(fuel=[1] * 8, pit=[False] * 8, start=0, mode=0, display=6)
    client._cu.poll.return_value = status
    client.poll_timer()
    assert client.read_status() is not None

    client.disconnect()

    client._cu = SimpleNamespace(poll=lambda: None)  # re-attach a stub just to call read_status safely
    with pytest.raises(RuntimeError):
        client.read_status()
