"""Carrera Digital Control Unit monitor + manual command console.

Connects to the real CU (serial or the AppConnect BLE adapter, via
carreralib) or the built-in mock simulator. Two halves:

1. Monitoring -- streams every piece of data the protocol exposes to a
   live-updating browser page: decoded Status (fuel[]/pit[]/start/mode/
   display, mode bitmask decoded, start field labeled with its confirmed
   meaning), decoded Timer events as they arrive, and the raw wire-level
   message log (carreralib's own DEBUG logging of send/receive bytes over
   serial, or BLE notification payloads) -- the actual "raw data stream
   from Bluetooth", not just parsed fields. Connection status (MOCK vs
   REAL + device, connected/disconnected, retry count) is always shown.

2. Manual commands -- every CU write the protocol supports (set_speed,
   set_brake, set_fuel_display, press() for any button, ignore(), reset(),
   Position Tower controls) is reachable as a one-shot POST endpoint, so a
   human can trigger any of them and watch what happens on the physical
   track/status -- since several (writing speed/brake to a live
   controller address, ignore()) are unconfirmed against real hardware and
   the only way to find out is to try them. Every attempt (and whether it
   succeeded or was rejected) is logged and shown, same as the read-side
   logs. There is still no automated driving loop of any kind here --
   nothing calls these on its own; they only fire when a human clicks a
   button. See CLAUDE.md's "Race manager (removed, logic preserved for
   reintegration)" section for the automated-driving layer's design --
   recoverable from git history if/when it's reintegrated.
"""
from __future__ import annotations

import asyncio
import collections
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.cu.base import CUClient, UnsupportedCommand
from app.cu.mock_client import MockCUClient
from app.cu.protocol import FUEL_MODE, LAP_COUNTER_MODE, PIT_LANE_MODE, REAL_MODE, describe_start
from app.network import schemas

logger = logging.getLogger("carrera_monitor")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

POLL_INTERVAL_SECONDS = 0.05  # ~20Hz; the CU's write rate-limit (~75ms) doesn't apply to reads
RECONNECT_RETRY_SECONDS = 5.0
RAW_LOG_MAXLEN = 500
TIMER_LOG_MAXLEN = 200
COMMAND_LOG_MAXLEN = 200


class RawLogHandler(logging.Handler):
    """Captures carreralib's own DEBUG-level wire logging -- raw send/
    receive byte buffers over serial, or raw BLE notification payloads --
    into a bounded deque. This is the actual raw-bytes data stream, not
    a paraphrase: it's carreralib's own instrumentation, just captured
    instead of only printed to a log file."""

    def __init__(self, maxlen: int = RAW_LOG_MAXLEN) -> None:
        super().__init__()
        self.entries: collections.deque[dict] = collections.deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        self.entries.append({
            "time": round(time.time(), 3),
            "logger": record.name,
            "message": record.getMessage(),
        })


raw_log_handler = RawLogHandler()


def _install_raw_logging() -> None:
    for name in ("carreralib.cu", "carreralib.ble", "carreralib.connection", "carreralib.serial"):
        lib_logger = logging.getLogger(name)
        lib_logger.setLevel(logging.DEBUG)
        lib_logger.addHandler(raw_log_handler)


def _decode_mode(mode: int) -> list[str]:
    flags = []
    if mode & FUEL_MODE:
        flags.append("FUEL_MODE")
    if mode & REAL_MODE:
        flags.append("REAL_MODE")
    if mode & PIT_LANE_MODE:
        flags.append("PIT_LANE_MODE")
    if mode & LAP_COUNTER_MODE:
        flags.append("LAP_COUNTER_MODE")
    return flags


def build_cu_client() -> tuple[CUClient, str]:
    """Real hardware if CARRERA_RMS_CU_DEVICE is set (a serial device path,
    a BLE MAC/UUID, or "auto" to scan for a device named Control_Unit).
    Falls back to the mock simulator otherwise. Returns (client,
    requested_device_string) -- connect() is NOT called here; the
    MonitorState poll loop owns connect/reconnect so a startup failure
    doesn't prevent the monitor UI itself from coming up.

    CARRERA_RMS_CU_ALLOW_CONTROLLER_WRITES=1 lets set_speed()/set_brake()
    attempt addresses 0-5 (the six controller slots) despite it being
    unconfirmed whether the CU firmware honors an external override for a
    slot with a live physical/wireless controller attached -- leave unset
    to keep those two blocked (UnsupportedCommand, logged in the command
    log) while addresses 6/7 (autonomous/pace car) stay always-allowed.
    """
    device = os.environ.get("CARRERA_RMS_CU_DEVICE")
    if device:
        from app.cu.carreralib_client import CarreralibCUClient
        allow_writes = os.environ.get("CARRERA_RMS_CU_ALLOW_CONTROLLER_WRITES") == "1"
        return CarreralibCUClient(device, allow_unconfirmed_controller_writes=allow_writes), device
    return MockCUClient(addresses=list(range(6))), "mock"


class MonitorState:
    def __init__(self) -> None:
        self.cu, self.requested_device = build_cu_client()
        self.connected = False
        self.last_error: str | None = None
        self.last_status: dict | None = None
        self.timer_log: collections.deque[dict] = collections.deque(maxlen=TIMER_LOG_MAXLEN)
        self.command_log: collections.deque[dict] = collections.deque(maxlen=COMMAND_LOG_MAXLEN)
        self.connect_attempts = 0
        self._last_connect_attempt = 0.0

    def log_command(self, description: str, ok: bool, error: str | None) -> None:
        self.command_log.appendleft({
            "time": round(time.time(), 3),
            "command": description,
            "ok": ok,
            "error": error,
        })

    def run_write(self, description: str, fn: Callable[[], None]) -> dict:
        """Runs a single CU write command (from one of the /api/cu/*
        endpoints below), logging the attempt and its outcome either way.
        Never raises -- the HTTP layer always gets a clean {ok, error}."""
        if not self.connected:
            self.log_command(description, False, "not connected")
            return {"ok": False, "error": "not connected"}
        try:
            fn()
        except UnsupportedCommand as exc:
            self.log_command(description, False, str(exc))
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            self.log_command(description, False, str(exc))
            logger.warning("CU write command failed: %s: %s", description, exc)
            return {"ok": False, "error": str(exc)}
        self.log_command(description, True, None)
        return {"ok": True, "error": None}

    def try_connect(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_connect_attempt) < RECONNECT_RETRY_SECONDS:
            return
        self._last_connect_attempt = now
        self.connect_attempts += 1
        try:
            self.cu.connect()
            self.connected = True
            self.last_error = None
            logger.warning("CU connected: %s", self.cu.describe())
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            logger.warning("CU connect failed (attempt %d): %s", self.connect_attempts, exc)

    def poll_once(self) -> None:
        if not self.connected:
            self.try_connect()
            return
        try:
            for event in self.cu.poll_timer():
                self.timer_log.appendleft({
                    "time": round(time.time(), 3),
                    "address": event.address,
                    "timestamp": event.timestamp,
                    "sector": event.sector,
                    "sector_label": "start/finish" if event.sector == 0 else f"check lane {event.sector}",
                })
        except Exception as exc:
            self._mark_disconnected(exc)
            return

        try:
            status = self.cu.read_status()
        except RuntimeError:
            return  # CarreralibCUClient.read_status() before any Status seen yet -- not an error
        except Exception as exc:
            self._mark_disconnected(exc)
            return
        self.last_status = {
            "fuel": list(status.fuel),
            "pit": list(status.pit),
            "start": status.start,
            "start_label": describe_start(status.start),
            "mode": status.mode,
            "mode_flags": _decode_mode(status.mode),
            "display": status.display,
        }

    def _mark_disconnected(self, exc: Exception) -> None:
        self.connected = False
        self.last_error = str(exc)
        logger.warning("CU poll failed, marking disconnected: %s", exc)

    def snapshot(self) -> dict:
        return {
            "backend": self.cu.describe(),
            "requested_device": self.requested_device,
            "connected": self.connected,
            "last_error": self.last_error,
            "connect_attempts": self.connect_attempts,
            # MockCUClient has no such attribute -- it never rejects a
            # controller-address write, so True accurately reflects it.
            "controller_writes_allowed": getattr(self.cu, "allow_unconfirmed_controller_writes", True),
            "status": self.last_status,
            "timer_log": list(self.timer_log),
            "command_log": list(self.command_log),
            "raw_log": list(raw_log_handler.entries),
        }


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict) -> None:
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def poll_loop(app: FastAPI) -> None:
    state: MonitorState = app.state.monitor
    while True:
        try:
            state.poll_once()
            await manager.broadcast(state.snapshot())
        except Exception:
            logger.exception("poll loop error")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _install_raw_logging()
    app.state.monitor = MonitorState()
    app.state.monitor.try_connect(force=True)

    banner = f"  CU BACKEND: {app.state.monitor.cu.describe()}  "
    rule = "=" * len(banner)
    print(rule, flush=True)
    print(banner, flush=True)
    print(rule, flush=True)

    task = asyncio.create_task(poll_loop(app))
    yield
    task.cancel()
    if app.state.monitor.connected:
        app.state.monitor.cu.disconnect()


app = FastAPI(title="Carrera CU Monitor", lifespan=lifespan)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/state")
async def api_state(request: Request) -> dict:
    return request.app.state.monitor.snapshot()


@app.post("/api/reconnect")
async def api_reconnect(request: Request) -> dict:
    state: MonitorState = request.app.state.monitor
    state.try_connect(force=True)
    return {"ok": True, "connected": state.connected, "last_error": state.last_error}


# -- Manual CU write commands -----------------------------------------------
# Every one of these fires exactly once, exactly when clicked -- there is
# no automated loop calling any of them. Each logs its outcome into
# state.command_log (part of the WebSocket snapshot) so a rejected/failed
# write is as visible as a successful one.

@app.post("/api/cu/speed")
async def api_cu_speed(body: schemas.SpeedRequest, request: Request) -> dict:
    state: MonitorState = request.app.state.monitor
    return state.run_write(f"set_speed(address={body.address}, value={body.value})",
                             lambda: state.cu.set_speed(body.address, body.value))


@app.post("/api/cu/brake")
async def api_cu_brake(body: schemas.BrakeRequest, request: Request) -> dict:
    state: MonitorState = request.app.state.monitor
    return state.run_write(f"set_brake(address={body.address}, value={body.value})",
                             lambda: state.cu.set_brake(body.address, body.value))


@app.post("/api/cu/fuel")
async def api_cu_fuel(body: schemas.FuelRequest, request: Request) -> dict:
    state: MonitorState = request.app.state.monitor
    return state.run_write(f"set_fuel_display(address={body.address}, value={body.value})",
                             lambda: state.cu.set_fuel_display(body.address, body.value))


@app.post("/api/cu/press")
async def api_cu_press(body: schemas.PressRequest, request: Request) -> dict:
    state: MonitorState = request.app.state.monitor
    return state.run_write(f"press(button_id={body.button_id})",
                             lambda: state.cu.press(body.button_id))


@app.post("/api/cu/ignore")
async def api_cu_ignore(body: schemas.IgnoreRequest, request: Request) -> dict:
    state: MonitorState = request.app.state.monitor
    return state.run_write(f"ignore(mask={body.mask:#04x})",
                             lambda: state.cu.ignore(body.mask))


@app.post("/api/cu/reset")
async def api_cu_reset(request: Request) -> dict:
    state: MonitorState = request.app.state.monitor
    return state.run_write("reset()", state.cu.reset)


@app.post("/api/cu/position")
async def api_cu_position(body: schemas.PositionRequest, request: Request) -> dict:
    state: MonitorState = request.app.state.monitor
    return state.run_write(f"set_position(address={body.address}, position={body.position})",
                             lambda: state.cu.set_position(body.address, body.position))


@app.post("/api/cu/lap")
async def api_cu_lap(body: schemas.LapRequest, request: Request) -> dict:
    state: MonitorState = request.app.state.monitor
    return state.run_write(f"set_lap(value={body.value})", lambda: state.cu.set_lap(body.value))


@app.post("/api/cu/clear_position")
async def api_cu_clear_position(request: Request) -> dict:
    state: MonitorState = request.app.state.monitor
    return state.run_write("clear_position()", state.cu.clear_position)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        await ws.send_json(ws.app.state.monitor.snapshot())
        while True:
            await ws.receive_text()  # no client input expected; just detect disconnect
    except WebSocketDisconnect:
        manager.disconnect(ws)
