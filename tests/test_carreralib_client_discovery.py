"""Tests the name-based BLE auto-discovery ("CARRERA_RMS_CU_DEVICE=auto"),
which scans for a device advertising the CU's known name instead of
requiring a hardcoded, machine-specific MAC/UUID."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.cu.carreralib_client import (
    AUTO_DISCOVER_SENTINEL,
    CarreralibCUClient,
    discover_cu_address,
)


def _device(address: str, name: str | None) -> SimpleNamespace:
    return SimpleNamespace(address=address, name=name)


def test_discover_finds_matching_device_by_name():
    devices = [
        _device("11:11:11:11:11:11", "Other Thing"),
        _device("EF:C4:35:38:1A:0B", "Control_Unit"),
    ]
    with patch("bleak.BleakScanner.discover", new=AsyncMock(return_value=devices)):
        address = discover_cu_address()
    assert address == "EF:C4:35:38:1A:0B"


def test_discover_raises_clear_error_when_not_found():
    devices = [_device("11:11:11:11:11:11", "Other Thing"), _device("22:22:22:22:22:22", None)]
    with patch("bleak.BleakScanner.discover", new=AsyncMock(return_value=devices)):
        with pytest.raises(RuntimeError, match="no BLE device advertising name"):
            discover_cu_address(timeout=0.01)


def test_discover_respects_custom_name():
    devices = [_device("33:33:33:33:33:33", "MyOtherCU")]
    with patch("bleak.BleakScanner.discover", new=AsyncMock(return_value=devices)):
        address = discover_cu_address(name="MyOtherCU")
    assert address == "33:33:33:33:33:33"


def test_discover_works_from_inside_a_running_event_loop():
    """Same nesting hazard as _warm_ble_cache -- must work when called
    from FastAPI/uvicorn's already-running loop, not just standalone."""
    async def scenario() -> None:
        devices = [_device("EF:C4:35:38:1A:0B", "Control_Unit")]
        with patch("bleak.BleakScanner.discover", new=AsyncMock(return_value=devices)):
            address = discover_cu_address()
        assert address == "EF:C4:35:38:1A:0B"

    asyncio.run(scenario())


def test_connect_resolves_auto_sentinel_before_connecting():
    client = CarreralibCUClient(device=AUTO_DISCOVER_SENTINEL)
    with patch("app.cu.carreralib_client.discover_cu_address", return_value="EF:C4:35:38:1A:0B") as discover, \
         patch("app.cu.carreralib_client._warm_ble_cache"), \
         patch("carreralib.ControlUnit") as control_unit:
        client.connect()
        discover.assert_called_once()
        control_unit.assert_called_once_with("EF:C4:35:38:1A:0B")
        assert client.device == "EF:C4:35:38:1A:0B"  # resolved, not left as "auto"


def test_connect_skips_redundant_warmup_scan_right_after_auto_discovery():
    """Confirmed on real hardware: a bare `carreralib.ControlUnit(addr)`
    call right after discover_cu_address()'s own scan connects cleanly,
    while adding a second, immediate, redundant _warm_ble_cache() scan
    (as connect() used to do unconditionally) reliably caused BlueZ
    errors ("br-connection-canceled", "failed to discover services") on
    the very first attempt. The scan discover_cu_address() itself just
    did is fresh enough -- don't scan again before the first connect."""
    client = CarreralibCUClient(device=AUTO_DISCOVER_SENTINEL)
    with patch("app.cu.carreralib_client.discover_cu_address", return_value="EF:C4:35:38:1A:0B"), \
         patch("app.cu.carreralib_client._warm_ble_cache") as warm, \
         patch("carreralib.ControlUnit") as control_unit:
        client.connect()
        warm.assert_not_called()
        control_unit.assert_called_once_with("EF:C4:35:38:1A:0B")


def test_connect_warms_cache_on_retry_after_auto_discovery_first_attempt_fails():
    from bleak.exc import BleakDeviceNotFoundError

    client = CarreralibCUClient(device=AUTO_DISCOVER_SENTINEL)
    with patch("app.cu.carreralib_client.discover_cu_address", return_value="EF:C4:35:38:1A:0B"), \
         patch("app.cu.carreralib_client._warm_ble_cache") as warm, \
         patch("carreralib.ControlUnit") as control_unit:
        control_unit.side_effect = [BleakDeviceNotFoundError("EF:C4:35:38:1A:0B", "not found"), object()]
        client.connect(ble_connect_attempts=2)
        # First attempt skips the redundant scan (just discovered); the
        # retry, potentially stale by then, warms the cache once.
        warm.assert_called_once_with("EF:C4:35:38:1A:0B")
        assert control_unit.call_count == 2
