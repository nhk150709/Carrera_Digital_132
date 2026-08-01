"""Read-only Carrera Digital Control Unit monitor.

Connects to the real CU (serial or the AppConnect BLE adapter, via
carreralib) or the built-in mock simulator, and streams every piece of
data the protocol exposes to a live-updating browser page:

- decoded Status (fuel[]/pit[]/start/mode/display, mode bitmask decoded)
- decoded Timer events (lap/sector crossings) as they arrive
- the raw wire-level message log (carreralib's own DEBUG logging of
  send/receive bytes over serial, or BLE notification payloads) -- this
  is the actual "raw data stream from Bluetooth", not just parsed fields
- whether the CU is currently connected, and the backend identity
  (MOCK vs REAL + device), impossible to miss

No race management of any kind (no lap timing/ranking, no controller
assignment, no fuel/tyre simulation, no strategy/weather/safety-car/
overtake/reliability/ghost/qualifying logic) -- see CLAUDE.md's "Race
manager (removed, logic preserved for reintegration)" section for that
layer's design. The code itself is still recoverable from git history
(the commit before this rewrite) if/when it's reintegrated.
"""
from __future__ import annotations

import asyncio
import collections
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.cu.base import CUClient
from app.cu.mock_client import MockCUClient
from app.cu.protocol import FUEL_MODE, LAP_COUNTER_MODE, PIT_LANE_MODE, REAL_MODE

logger = logging.getLogger("carrera_monitor")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

POLL_INTERVAL_SECONDS = 0.05  # ~20Hz; the CU's write rate-limit (~75ms) doesn't apply to reads
RECONNECT_RETRY_SECONDS = 5.0
RAW_LOG_MAXLEN = 500
TIMER_LOG_MAXLEN = 200


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
    doesn't prevent the monitor UI itself from coming up."""
    device = os.environ.get("CARRERA_RMS_CU_DEVICE")
    if device:
        from app.cu.carreralib_client import CarreralibCUClient
        return CarreralibCUClient(device), device
    return MockCUClient(addresses=list(range(6))), "mock"


class MonitorState:
    def __init__(self) -> None:
        self.cu, self.requested_device = build_cu_client()
        self.connected = False
        self.last_error: str | None = None
        self.last_status: dict | None = None
        self.timer_log: collections.deque[dict] = collections.deque(maxlen=TIMER_LOG_MAXLEN)
        self.connect_attempts = 0
        self._last_connect_attempt = 0.0

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
            "status": self.last_status,
            "timer_log": list(self.timer_log),
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


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        await ws.send_json(ws.app.state.monitor.snapshot())
        while True:
            await ws.receive_text()  # no client input expected; just detect disconnect
    except WebSocketDisconnect:
        manager.disconnect(ws)
