"""Real-hardware CU client, wrapping the third-party `carreralib` package
(MIT licensed, https://github.com/tkem/carreralib, confirmed against
version 1.0.3 installed in this repo's environment).

`device` follows carreralib's own convention: a serial device path (e.g.
"/dev/ttyUSB0", "COM3") or, for the AppConnect BLE adapter, its MAC
address ("aa:bb:cc:dd:ee:ff").

Confirmed from carreralib.cu.ControlUnit source:
  - poll() returns either a Status(fuel, start, mode, pit, display) or a
    Timer(address, timestamp, sector); fuel/values are 0..15, not 0..100.
  - Timer.sector == 1 for a start/finish crossing, 2/3 for Check Lane
    splits -- translated to this app's own sector==0-means-lap convention
    here, at the boundary (see app/cu/protocol.py).
  - setspeed(address, value) / setbrake(address, value) / setfuel(address,
    value) all accept address 0..7 with no further restriction *in the
    library*. That does NOT confirm the CU firmware itself honors a write
    for addresses 0-5 (real controller slots) versus just reporting
    whatever the physical/wireless controller attached to that slot is
    doing -- this is unconfirmed and should be tested empirically before
    relying on it (see docs/reference/protocol-notes.md). Addresses 6
    (autonomous car) and 7 (pace car) have no physical controller and are
    the confirmed-safe targets for software speed control.
  - start() presses the CU's own START/ENTER button.
"""
from __future__ import annotations

import time

from app.cu.base import CUClient, UnsupportedCommand
from app.cu.protocol import Status, TimerEvent

CONTROLLER_ADDRESSES = set(range(6))  # 0-5: real controller slots


class CarreralibCUClient(CUClient):
    def __init__(self, device: str, allow_unconfirmed_controller_writes: bool = False):
        self.device = device
        self.allow_unconfirmed_controller_writes = allow_unconfirmed_controller_writes
        self._cu = None
        self._clock_offset_ms: float | None = None

    def connect(self) -> None:
        import carreralib  # lazy import: not a hard dependency for mock-mode use

        self._cu = carreralib.ControlUnit(self.device)
        # CU timestamps are a free-running 32-bit millisecond counter with
        # no defined epoch; anchor it to our own monotonic clock on connect
        # so downstream code can treat TimerEvent.timestamp as seconds
        # comparable across the session.
        self._clock_offset_ms = None

    def disconnect(self) -> None:
        if self._cu is not None:
            self._cu.close()
        self._cu = None

    def _to_seconds(self, cu_timestamp_ms: int) -> float:
        if self._clock_offset_ms is None:
            self._clock_offset_ms = cu_timestamp_ms
        # Handles the 32-bit counter wrapping by working purely in deltas
        # from the first observed value; still monotonic within a session.
        return (cu_timestamp_ms - self._clock_offset_ms) / 1000.0

    def read_status(self) -> Status:
        assert self._cu is not None, "not connected"
        result = self._cu.poll()
        # poll() can return a pending Timer instead of Status; callers
        # should prefer draining poll_timer() in the same loop iteration
        # and only trust read_status() shortly after, or call this in a
        # retry loop. Kept simple here: try a few times.
        for _ in range(8):
            if hasattr(result, "fuel"):
                return Status(fuel=tuple(result.fuel), pit=tuple(result.pit),
                               start=result.start, mode=result.mode, display=result.display)
            result = self._cu.poll()
        raise RuntimeError("CU did not return a Status message")

    def poll_timer(self) -> list[TimerEvent]:
        assert self._cu is not None, "not connected"
        events: list[TimerEvent] = []
        result = self._cu.poll()
        if result is not None and hasattr(result, "sector"):
            sector = 0 if result.sector == 1 else result.sector
            events.append(TimerEvent(address=result.address,
                                       timestamp=self._to_seconds(result.timestamp),
                                       sector=sector))
        return events

    def set_speed(self, address: int, value: int) -> None:
        if address in CONTROLLER_ADDRESSES and not self.allow_unconfirmed_controller_writes:
            raise UnsupportedCommand(
                f"set_speed to controller address {address} is unconfirmed against real "
                "hardware; pass allow_unconfirmed_controller_writes=True to try it anyway"
            )
        assert self._cu is not None, "not connected"
        self._cu.setspeed(address, max(0, min(15, value)))

    def set_brake(self, address: int, value: int) -> None:
        if address in CONTROLLER_ADDRESSES and not self.allow_unconfirmed_controller_writes:
            raise UnsupportedCommand(
                f"set_brake to controller address {address} is unconfirmed against real "
                "hardware; pass allow_unconfirmed_controller_writes=True to try it anyway"
            )
        assert self._cu is not None, "not connected"
        self._cu.setbrake(address, max(0, min(15, value)))

    def set_fuel_display(self, address: int, value: int) -> None:
        assert self._cu is not None, "not connected"
        self._cu.setfuel(address, max(0, min(15, value)))

    def start(self) -> None:
        assert self._cu is not None, "not connected"
        self._cu.start()

    def press_pace_car_esc(self) -> None:
        assert self._cu is not None, "not connected"
        self._cu.press(self._cu.PACE_CAR_ESC_BUTTON_ID)

    def set_position(self, address: int, position: int) -> None:
        """Drive an official Carrera Position Tower accessory, if attached."""
        assert self._cu is not None, "not connected"
        self._cu.setpos(address, position)

    def version(self) -> str:
        assert self._cu is not None, "not connected"
        return self._cu.version()
