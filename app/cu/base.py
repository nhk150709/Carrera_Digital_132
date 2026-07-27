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
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def read_status(self) -> Status: ...

    @abstractmethod
    def poll_timer(self) -> list[TimerEvent]:
        """Return any Timer events available right now. Non-blocking;
        meant to be called on a tight loop by the session driver."""

    @abstractmethod
    def set_speed(self, address: int, value: int) -> None:
        """value in 0..15."""

    @abstractmethod
    def set_fuel_display(self, address: int, value: int) -> None:
        """Override the CU's own displayed fuel value for `address`
        (0..15) -- lets our own tyre/acceleration-based fuel model drive
        what the physical CU and any Carrera fuel LEDs show."""

    @abstractmethod
    def start(self) -> None:
        """Simulate pressing the CU's own START/ENTER button."""
