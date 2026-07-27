"""Arduino-facing serial bridge.

Deliberately a compact newline-delimited text protocol, not JSON, so a
bare Arduino (no ArduinoJson dependency, limited RAM) can parse it with
`String.indexOf`/`split` on ':' and ','. See arduino/ for example sketches
that speak this protocol on the microcontroller side.

Outbound (Pi -> Arduino), one line each, written every tick:
  STATE <idle|countdown|running|paused|finished>
  FUEL <addr>:<pct>,<addr>:<pct>,...         pct is 0-100
  PIT <addr>:<0|1>,...
  RANK <addr>:<safe-name>:<position>,...
  JUMP <addr>                                sent once, on the rising edge only

Outbound, event-driven (start-light sequencing, not tick-driven):
  START <ARMED|L1|L2|L3|L4|L5|GO>

Inbound (Arduino -> Pi), one line each:
  BTN STOP <addr>        physical stop button for that car/player
  EARLY <addr>           start-line sensor saw movement before green
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.race.session import RaceSession

logger = logging.getLogger("carrera_rms.arduino")


def _safe_name(name: str) -> str:
    cleaned = (name or "").replace(":", "_").replace(",", "_").replace(" ", "_")
    return cleaned or "-"


class ArduinoBridge:
    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self._serial = None
        self._inbound: "queue.Queue[str]" = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._stop_reader = threading.Event()
        self._last_jump_state: dict[int, bool] = {}

    def open(self) -> None:
        import serial  # pyserial; only required when Arduino support is enabled

        self._serial = serial.Serial(self.port, self.baudrate, timeout=1)
        logger.info("Arduino bridge connected on %s @ %d baud", self.port, self.baudrate)

    def close(self) -> None:
        self._stop_reader.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2)
        if self._serial is not None:
            self._serial.close()

    def start_reader(self, session: "RaceSession") -> None:
        def _run() -> None:
            while not self._stop_reader.is_set():
                try:
                    raw = self._serial.readline()
                except Exception:
                    continue
                line = raw.decode("ascii", errors="ignore").strip()
                if line:
                    self._inbound.put(line)

        self._reader_thread = threading.Thread(target=_run, daemon=True, name="arduino-reader")
        self._reader_thread.start()

    def _apply_inbound(self, session: "RaceSession") -> None:
        while True:
            try:
                line = self._inbound.get_nowait()
            except queue.Empty:
                break
            self._handle_line(line, session)

    def _handle_line(self, line: str, session: "RaceSession") -> None:
        parts = line.split()
        try:
            if parts[:2] == ["BTN", "STOP"] and len(parts) == 3:
                session.stop(triggered_by=int(parts[2]))
            elif parts and parts[0] == "EARLY" and len(parts) == 2:
                session.engine.report_early_movement(int(parts[1]), session.clock())
            elif parts:
                logger.warning("unrecognized line from Arduino: %r", line)
        except (ValueError, IndexError):
            logger.warning("malformed line from Arduino: %r", line)

    def _write(self, line: str) -> None:
        if self._serial is None:
            return
        try:
            self._serial.write((line + "\n").encode("ascii"))
        except Exception:
            logger.exception("failed writing to Arduino serial port")

    def publish_start_phase(self, phase: str) -> None:
        self._write(f"START {phase}")

    def sync(self, session: "RaceSession") -> None:
        """Call once per tick: drains inbound events into the session, then
        writes the current outbound state."""
        self._apply_inbound(session)

        engine = session.engine
        self._write(f"STATE {engine.state.value}")

        fuel_parts = ",".join(f"{addr}:{round(car.fuel)}" for addr, car in engine.cars.items())
        self._write(f"FUEL {fuel_parts}")

        pit_parts = ",".join(f"{addr}:{1 if car.in_pit else 0}" for addr, car in engine.cars.items())
        self._write(f"PIT {pit_parts}")

        rank_parts = ",".join(
            f"{r.address}:{_safe_name(r.name)}:{r.position}" for r in engine.rankings()
        )
        self._write(f"RANK {rank_parts}")

        for addr, car in engine.cars.items():
            was_flagged = self._last_jump_state.get(addr, False)
            if car.jump_start and not was_flagged:
                self._write(f"JUMP {addr}")
            self._last_jump_state[addr] = car.jump_start
