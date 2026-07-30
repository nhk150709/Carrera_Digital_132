"""Tests only the BLE-vs-serial detection and warm-up call wiring, which
doesn't require real Bluetooth hardware or the `bleak` library actually
doing anything -- see test_carreralib_client_guard.py for the other
guard-logic tests, and the module docstring in
app/cu/carreralib_client.py for why this warm-up exists at all.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from app.cu.carreralib_client import CarreralibCUClient, _looks_like_ble_address, _warm_ble_cache


def test_colon_separated_mac_looks_like_ble():
    assert _looks_like_ble_address("aa:bb:cc:dd:ee:ff") is True


def test_macos_style_uuid_looks_like_ble():
    # carreralib's dash check matches a 5-group macOS BLE UUID
    # (8-4-4-4-12 hex), not a dash-separated 6-octet MAC.
    assert _looks_like_ble_address("12345678-1234-1234-1234-123456789abc") is True


def test_serial_device_path_does_not_look_like_ble():
    assert _looks_like_ble_address("/dev/ttyUSB0") is False


def test_connect_warms_ble_cache_for_mac_address():
    client = CarreralibCUClient(device="EF:C4:35:38:1A:0B")
    with patch("app.cu.carreralib_client._warm_ble_cache") as warm, \
         patch("carreralib.ControlUnit") as control_unit:
        client.connect()
        warm.assert_called_once_with("EF:C4:35:38:1A:0B")
        control_unit.assert_called_once_with("EF:C4:35:38:1A:0B")


def test_connect_skips_warmup_for_serial_device():
    client = CarreralibCUClient(device="/dev/ttyUSB0")
    with patch("app.cu.carreralib_client._warm_ble_cache") as warm, \
         patch("carreralib.ControlUnit") as control_unit:
        client.connect()
        warm.assert_not_called()
        control_unit.assert_called_once_with("/dev/ttyUSB0")


def test_warm_ble_cache_works_from_inside_a_running_event_loop():
    """Reproduces the actual bug hit on real hardware: FastAPI/uvicorn's
    startup calls connect() synchronously from inside an *already
    running* event loop. The original implementation called
    asyncio.run() directly, which raises "asyncio.run() cannot be called
    from a running event loop" in exactly that situation -- caught here
    by actually running inside asyncio.run() ourselves, not just mocking
    the function away like the tests above do.
    """
    async def scenario() -> None:
        with patch("bleak.BleakScanner.discover", new=AsyncMock(return_value=[])):
            _warm_ble_cache("EF:C4:35:38:1A:0B", timeout=0.01)  # must not raise

    asyncio.run(scenario())


def test_connect_works_from_inside_a_running_event_loop():
    async def scenario() -> None:
        client = CarreralibCUClient(device="EF:C4:35:38:1A:0B")
        with patch("bleak.BleakScanner.discover", new=AsyncMock(return_value=[])), \
             patch("carreralib.ControlUnit") as control_unit:
            client.connect()  # must not raise
            control_unit.assert_called_once_with("EF:C4:35:38:1A:0B")

    asyncio.run(scenario())
