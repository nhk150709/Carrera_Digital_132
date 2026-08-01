from __future__ import annotations

from abc import ABC, abstractmethod

from app.cu.protocol import Status, TimerEvent


class UnsupportedCommand(RuntimeError):
    """Raised when a CU backend can't/won't perform a requested write.

    In particular: carreralib's setspeed()/setbrake() place no address
    restriction beyond the protocol's own 0-7 range, so the *library*
    happily sends a "set speed" command for addresses 0-5 (the six
    controller slots). Whether the real CU *firmware* actually honors that
    for a slot with a live physical/wireless controller attached -- versus
    just reporting whatever that controller is doing -- is unconfirmed
    (see docs/reference/protocol-notes.md). CarreralibCUClient raises this
    for 0-5 unless explicitly overridden, so a build fails loudly instead
    of silently sending commands that may be ignored by the hardware.
    """


class CUClient(ABC):
    @abstractmethod
    def describe(self) -> str:
        """Short human-readable identity string (mock vs. real, and which
        device) -- surfaced in startup logs and the debug tab so it's never
        ambiguous which backend a running session is actually talking to."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def read_status(self) -> Status: ...

    @abstractmethod
    def poll_timer(self) -> list[TimerEvent]:
        """Return any Timer events available right now. Non-blocking;
        meant to be called on a tight loop by the session driver."""

    # -- Writes. Every one of these is a real CU protocol command (see
    # app/cu/protocol.py and carreralib.cu.ControlUnit) -- exposed here so
    # the monitor can let a human trigger any of them manually to see what
    # happens, since several are unconfirmed against real hardware and the
    # only way to confirm them is to try them and watch the track/status.

    @abstractmethod
    def set_speed(self, address: int, value: int) -> None:
        """value in 0..15. Addresses 0-5 (real controller slots) are
        guarded (see UnsupportedCommand) since whether the CU firmware
        honors an external override there, vs. the live controller's own
        input winning, is unconfirmed. 6 (autonomous) and 7 (pace car)
        are always allowed."""

    @abstractmethod
    def set_brake(self, address: int, value: int) -> None:
        """value in 0..15. Same address guard as set_speed."""

    @abstractmethod
    def set_fuel_display(self, address: int, value: int) -> None:
        """Override the CU's own displayed fuel value for `address`
        (0..15) -- confirmed to work for any address, no guard."""

    @abstractmethod
    def press(self, button_id: int) -> None:
        """Simulate pressing one of the CU's own physical buttons -- see
        the *_BUTTON_ID constants in app/cu/protocol.py. START_ENTER's
        effect on the `start` status field is confirmed (see
        protocol.START_LABELS); the others' real-hardware effects are
        documented from carreralib's docstrings only, not independently
        re-confirmed here."""

    @abstractmethod
    def ignore(self, mask: int) -> None:
        """8-bit bitmask (bit N = address N) telling the CU to ignore
        those controllers' own physical/wireless input entirely. Not
        independently confirmed against real hardware."""

    @abstractmethod
    def reset(self) -> None:
        """Reset the CU's own internal timer."""

    @abstractmethod
    def set_position(self, address: int, position: int) -> None:
        """Drive an official Carrera Position Tower accessory (1..8), if
        one is attached. No-op-observable without that accessory."""

    @abstractmethod
    def set_lap(self, value: int) -> None:
        """Set the current lap shown on a Position Tower accessory."""

    @abstractmethod
    def clear_position(self) -> None:
        """Clear/reset the Position Tower display."""

    @abstractmethod
    def version(self) -> str:
        """CU firmware version string."""
