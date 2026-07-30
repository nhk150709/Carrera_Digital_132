"""Tests only the BLE-vs-serial detection and warm-up call wiring, which
doesn't require real Bluetooth hardware or the `bleak` library actually
doing anything -- see test_carreralib_client_guard.py for the other
guard-logic tests, and the module docstring in
app/cu/carreralib_client.py for why this warm-up exists at all.
"""
from unittest.mock import patch

from app.cu.carreralib_client import CarreralibCUClient, _looks_like_ble_address


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
