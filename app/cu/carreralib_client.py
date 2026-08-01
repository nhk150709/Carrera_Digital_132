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
  - press(START_ENTER_BUTTON_ID) presses the CU's own START/ENTER button.
    Its effect on Status.start is CONFIRMED by direct observation on real
    hardware: 0 = racing, 1 = stopped, 2..7 = the light sequence stepping
    up after pressing it while stopped, then back to 0 -- see
    app/cu/protocol.py's START_LABELS/describe_start().
"""
from __future__ import annotations

import time

from app.cu.base import CUClient, UnsupportedCommand
from app.cu.protocol import Status, TimerEvent

CONTROLLER_ADDRESSES = set(range(6))  # 0-5: real controller slots


AUTO_DISCOVER_SENTINEL = "auto"
DEFAULT_CU_BLE_NAME = "Control_Unit"  # confirmed advertised name of the AppConnect adapter


def _looks_like_ble_address(device: str) -> bool:
    """Matches carreralib.connection.open()'s own check for which
    transport a device string selects."""
    return len(device.split(":")) == 6 or len(device.split("-")) == 5


def discover_cu_address(name: str = DEFAULT_CU_BLE_NAME, timeout: float = 6.0) -> str:
    """Scans for a BLE device advertising the given name (the CU/AppConnect
    adapter's own name, confirmed "Control_Unit" in practice) and returns
    its address -- so you don't have to re-scan by hand and hardcode a MAC
    every time. Works the same way regardless of whether the caller
    already has an event loop running (see _warm_ble_cache's docstring for
    why that matters). Raises RuntimeError if no matching device is found.
    """
    import asyncio
    import threading

    from bleak import BleakScanner

    found: dict[str, str] = {}

    async def scan() -> None:
        for d in await BleakScanner.discover(timeout=timeout):
            if d.name == name:
                found["address"] = d.address
                return

    def run_in_new_loop() -> None:
        asyncio.run(scan())

    thread = threading.Thread(target=run_in_new_loop)
    thread.start()
    thread.join()

    if "address" not in found:
        raise RuntimeError(
            f"no BLE device advertising name {name!r} found in a {timeout}s scan "
            "-- make sure it's powered on and not already connected to something else"
        )
    return found["address"]


def _warm_ble_cache(address: str, timeout: float = 4.0) -> None:
    """On Linux, bleak's BlueZ backend can only connect to a device BlueZ
    has *recently* seen via a scan -- it resolves the address against
    BlueZ's own D-Bus device cache rather than scanning itself, so a
    direct connect some time after the last scan fails with
    BleakDeviceNotFoundError even though the device is right there and
    working (observed in practice: works immediately after a manual scan,
    fails a minute later). A short scan immediately before connecting
    keeps that cache fresh and avoids the failure.

    connect() (and therefore this) needs to work whether it's called from
    plain synchronous code (a standalone test script) or, as in the real
    app, from inside FastAPI/uvicorn's already-running event loop during
    startup -- asyncio.run() cannot be nested inside a running loop, so
    the scan runs in its own dedicated thread with its own fresh loop
    (the same pattern carreralib's own BLE connection uses internally),
    which works safely in either case.
    """
    import asyncio
    import threading

    from bleak import BleakScanner

    async def scan() -> None:
        await BleakScanner.discover(timeout=timeout)

    def run_in_new_loop() -> None:
        asyncio.run(scan())

    thread = threading.Thread(target=run_in_new_loop)
    thread.start()
    thread.join()


class CarreralibCUClient(CUClient):
    def __init__(self, device: str, allow_unconfirmed_controller_writes: bool = False):
        self.device = device
        self.allow_unconfirmed_controller_writes = allow_unconfirmed_controller_writes
        self._cu = None
        self._clock_offset_ms: float | None = None
        self._latest_status: Status | None = None

    def describe(self) -> str:
        # self.device is resolved from "auto" to a real address inside
        # connect(), so this reports the actual address once connected.
        return f"REAL (carreralib, device={self.device})"

    def connect(self, ble_connect_attempts: int = 4) -> None:
        import carreralib  # lazy import: not a hard dependency for mock-mode use

        if self.device == AUTO_DISCOVER_SENTINEL:
            self.device = discover_cu_address()

        if not _looks_like_ble_address(self.device):
            self._cu = carreralib.ControlUnit(self.device)
            self._clock_offset_ms = None
            return

        # Even immediately after a scan, BlueZ can apparently still drop
        # the device from its cache before carreralib's own connection
        # attempt reaches it (observed in practice) -- so in addition to
        # warming the cache, retry the whole scan+connect sequence a
        # few times rather than failing on the first race.
        from bleak.exc import BleakDeviceNotFoundError

        last_error: Exception | None = None
        for attempt in range(1, ble_connect_attempts + 1):
            _warm_ble_cache(self.device)
            try:
                self._cu = carreralib.ControlUnit(self.device)
                self._clock_offset_ms = None
                return
            except BleakDeviceNotFoundError as exc:
                last_error = exc
        raise RuntimeError(
            f"could not connect to BLE device {self.device} after "
            f"{ble_connect_attempts} scan+connect attempts"
        ) from last_error

    def disconnect(self) -> None:
        if self._cu is not None:
            self._cu.close()
        self._cu = None
        self._latest_status = None

    def _to_seconds(self, cu_timestamp_ms: int) -> float:
        if self._clock_offset_ms is None:
            self._clock_offset_ms = cu_timestamp_ms
        # Handles the 32-bit counter wrapping by working purely in deltas
        # from the first observed value; still monotonic within a session.
        return (cu_timestamp_ms - self._clock_offset_ms) / 1000.0

    def read_status(self) -> Status:
        """Returns the most recently observed Status -- does NOT poll the
        CU itself. carreralib's poll() returns either a pending Timer or a
        Status on each call, never both, and the CU only has one request/
        response channel -- calling poll() separately here as well as in
        poll_timer() would double the round-trips per tick and let the two
        calls race each other. Instead, poll_timer() (the one call per
        tick the session loop already makes) opportunistically caches
        whatever Status it happens to see interleaved with Timer messages,
        and this just returns that cache. Note this means Status can lag
        during a stretch of heavy lap-crossing traffic, when the CU may
        keep returning pending Timer messages ahead of a fresh Status --
        fine for a debug/monitoring view, not guaranteed fresh every tick.

        Raises RuntimeError if no Status has been observed yet (e.g.
        called immediately after connect(), before the first tick).
        """
        if self._latest_status is None:
            raise RuntimeError("no Status message received from the CU yet -- call poll_timer() first")
        return self._latest_status

    def poll_timer(self) -> list[TimerEvent]:
        assert self._cu is not None, "not connected"
        events: list[TimerEvent] = []
        result = self._cu.poll()
        if result is not None and hasattr(result, "sector"):
            sector = 0 if result.sector == 1 else result.sector
            events.append(TimerEvent(address=result.address,
                                       timestamp=self._to_seconds(result.timestamp),
                                       sector=sector))
        elif result is not None and hasattr(result, "fuel"):
            self._latest_status = Status(fuel=tuple(result.fuel), pit=tuple(result.pit),
                                           start=result.start, mode=result.mode, display=result.display)
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

    def press(self, button_id: int) -> None:
        assert self._cu is not None, "not connected"
        self._cu.press(button_id)

    def ignore(self, mask: int) -> None:
        assert self._cu is not None, "not connected"
        self._cu.ignore(mask)

    def reset(self) -> None:
        assert self._cu is not None, "not connected"
        self._cu.reset()

    def set_position(self, address: int, position: int) -> None:
        assert self._cu is not None, "not connected"
        self._cu.setpos(address, position)

    def set_lap(self, value: int) -> None:
        assert self._cu is not None, "not connected"
        self._cu.setlap(value)

    def clear_position(self) -> None:
        assert self._cu is not None, "not connected"
        self._cu.clrpos()

    def version(self) -> str:
        assert self._cu is not None, "not connected"
        return self._cu.version()
