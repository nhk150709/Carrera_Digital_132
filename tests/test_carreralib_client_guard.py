"""Tests only the address-write guard logic, which doesn't require a real
CU connection. Full hardware behavior is untestable in this environment by
definition -- see the module docstring in app/cu/carreralib_client.py.
"""
import pytest

from app.cu.base import UnsupportedCommand
from app.cu.carreralib_client import CarreralibCUClient


@pytest.mark.parametrize("address", [0, 1, 2, 3, 4, 5])
def test_controller_addresses_blocked_by_default(address):
    client = CarreralibCUClient(device="/dev/ttyUSB0")
    with pytest.raises(UnsupportedCommand):
        client.set_speed(address, 10)


@pytest.mark.parametrize("address", [6, 7])
def test_autonomous_and_pace_car_addresses_not_blocked_by_guard(address):
    client = CarreralibCUClient(device="/dev/ttyUSB0")
    # No real connection is made in this test; we only assert the address
    # guard doesn't reject these -- it should fail later on the "not
    # connected" assertion instead, proving the guard itself passed.
    with pytest.raises(AssertionError, match="not connected"):
        client.set_speed(address, 10)


def test_controller_address_allowed_when_explicitly_overridden():
    client = CarreralibCUClient(device="/dev/ttyUSB0", allow_unconfirmed_controller_writes=True)
    with pytest.raises(AssertionError, match="not connected"):
        client.set_speed(2, 10)
