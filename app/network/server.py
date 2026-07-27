"""FastAPI application: REST control API + WebSocket state broadcast + the
browser UI. This one server is what makes "runs on the Pi" and "others on
the local network can open their own screen" the same mechanism -- every
browser (the Pi's own touchscreen included) is just another WebSocket
client of the same shared RaceSession.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import HTTPConnection

from app.controllers.web import WebController
from app.cu.mock_client import MockCUClient
from app.network import schemas
from app.network.arduino_api import ArduinoBridge
from app.network.state_view import serialize
from app.race.models import RaceMode, RaceState, WeatherLevel
from app.race.pace_car import PaceCarPlayback
from app.race.session import RaceSession, SessionConfig

logger = logging.getLogger("carrera_rms")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
TICK_HZ = 20


def build_default_session() -> RaceSession:
    addresses = list(range(6))
    cu = MockCUClient(addresses=addresses, base_lap_time=6.0)
    cu.connect()
    return RaceSession(cu, SessionConfig(addresses=addresses))


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


async def tick_loop(app: FastAPI) -> None:
    session: RaceSession = app.state.session
    interval = 1.0 / TICK_HZ
    while True:
        try:
            session.tick()
            bridge: ArduinoBridge | None = app.state.arduino_bridge
            if bridge is not None:
                bridge.sync(session)
            await manager.broadcast(serialize(session))
        except Exception:
            logger.exception("tick loop error")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.session = build_default_session()
    app.state.web_controllers = {}
    serial_port = os.environ.get("CARRERA_RMS_ARDUINO_PORT")
    app.state.arduino_bridge = ArduinoBridge(serial_port) if serial_port else None
    if app.state.arduino_bridge is not None:
        app.state.arduino_bridge.open()
        app.state.arduino_bridge.start_reader(app.state.session)
    task = asyncio.create_task(tick_loop(app))
    yield
    task.cancel()
    if app.state.arduino_bridge is not None:
        app.state.arduino_bridge.close()


app = FastAPI(title="Carrera Digital RMS", lifespan=lifespan)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def get_session(request: Request) -> RaceSession:
    return request.app.state.session


def get_or_create_web_controller(conn: HTTPConnection, controller_id: str) -> WebController:
    registry: dict[str, WebController] = conn.app.state.web_controllers
    if controller_id not in registry:
        registry[controller_id] = WebController(controller_id)
    return registry[controller_id]


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/state")
async def api_state(request: Request) -> dict:
    return serialize(get_session(request))


LIGHT_INTERVAL_SECONDS = 1.0


async def _run_start_sequence(app: FastAPI) -> None:
    """Drives the 5-light countdown (F1-style: lights on one at a time,
    then all extinguish together = go), with a randomized hold before the
    green to discourage anticipation-based jump starts. Publishes each
    phase to the Arduino bridge (if configured) so external LEDs can be
    kept in sync, and only calls session.go() once the final GO phase is
    actually sent.
    """
    session: RaceSession = app.state.session
    bridge: ArduinoBridge | None = app.state.arduino_bridge

    def publish(phase: str) -> None:
        if bridge is not None:
            bridge.publish_start_phase(phase)

    publish("ARMED")
    for i in range(1, 6):
        await asyncio.sleep(LIGHT_INTERVAL_SECONDS)
        if session.engine.state != RaceState.COUNTDOWN:
            return  # countdown was aborted (e.g. a manual stop)
        publish(f"L{i}")

    await asyncio.sleep(LIGHT_INTERVAL_SECONDS + random.uniform(0.2, 1.5))
    if session.engine.state != RaceState.COUNTDOWN:
        return
    publish("GO")
    session.go()


@app.post("/api/race/countdown")
async def api_countdown(request: Request) -> dict:
    get_session(request).begin_countdown()
    asyncio.create_task(_run_start_sequence(request.app))
    return {"ok": True}


@app.post("/api/race/go")
async def api_go(request: Request) -> dict:
    get_session(request).go()
    return {"ok": True}


@app.post("/api/race/stop")
async def api_stop(body: schemas.StopRequest, request: Request) -> dict:
    get_session(request).stop(triggered_by=body.triggered_by, penalize_trigger=body.penalize_trigger)
    return {"ok": True}


@app.post("/api/race/resume")
async def api_resume(request: Request) -> dict:
    get_session(request).resume()
    return {"ok": True}


@app.post("/api/race/reset")
async def api_reset(request: Request) -> dict:
    session = get_session(request)
    session.engine.reset(session.clock())
    return {"ok": True}


@app.post("/api/race/mode")
async def api_mode(body: schemas.ModeRequest, request: Request) -> dict:
    session = get_session(request)
    try:
        session.engine.mode = RaceMode(body.mode)
    except ValueError:
        raise HTTPException(422, f"unknown mode {body.mode!r}")
    return {"ok": True}


@app.post("/api/race/weather")
async def api_weather(body: schemas.WeatherRequest, request: Request) -> dict:
    session = get_session(request)
    try:
        session.weather.set_level(WeatherLevel(body.level))
    except ValueError:
        raise HTTPException(422, f"unknown weather level {body.level!r}")
    return {"ok": True}


@app.post("/api/cars/{address}/assign")
async def api_assign(address: int, body: schemas.AssignRequest, request: Request) -> dict:
    session = get_session(request)
    if address not in session.engine.cars:
        raise HTTPException(404, f"no car at address {address}")
    controller = get_or_create_web_controller(request, body.controller_id)
    session.assign_controller(address, controller)
    if body.name:
        session.engine.assign(address, name=body.name)
    return {"ok": True}


@app.post("/api/cars/{address}/unassign")
async def api_unassign(address: int, request: Request) -> dict:
    get_session(request).unassign_controller(address)
    return {"ok": True}


@app.post("/api/cars/{address}/sensitivity")
async def api_sensitivity(address: int, body: schemas.SensitivityRequest, request: Request) -> dict:
    session = get_session(request)
    controller = session.controllers.get(address)
    if controller is None or not hasattr(controller, "curve"):
        raise HTTPException(404, "no controller assigned to this car")
    controller.curve.throttle_exponent = body.throttle_exponent
    controller.curve.throttle_gain = body.throttle_gain
    controller.curve.brake_exponent = body.brake_exponent
    controller.curve.brake_gain = body.brake_gain
    return {"ok": True}


@app.post("/api/cars/{address}/penalty")
async def api_penalty(address: int, body: schemas.PenaltyRequest, request: Request) -> dict:
    session = get_session(request)
    session.engine.add_penalty(address, body.seconds, body.reason, session.clock())
    return {"ok": True}


@app.get("/api/debug/log")
async def api_debug_log(request: Request) -> dict:
    return {"log": get_session(request).debug_log[-200:]}


@app.post("/api/recording/start")
async def api_recording_start(body: schemas.RecordingStartRequest, request: Request) -> dict:
    session = get_session(request)
    session.recorder.start(body.address, body.name, session.clock())
    return {"ok": True}


@app.post("/api/recording/stop/{address}")
async def api_recording_stop(address: int, request: Request) -> dict:
    session = get_session(request)
    recording = session.recorder.stop(address)
    if recording is None:
        raise HTTPException(404, "no active recording for this address")
    path = session.recorder.save(recording)
    return {"ok": True, "path": str(path)}


@app.get("/api/recording/list")
async def api_recording_list(request: Request) -> dict:
    return {"recordings": get_session(request).recorder.list_recordings()}


@app.post("/api/pace_car/play")
async def api_pace_car_play(body: schemas.PaceCarPlayRequest, request: Request) -> dict:
    session = get_session(request)
    try:
        recording = session.recorder.load(body.recording_name)
    except FileNotFoundError:
        raise HTTPException(404, f"no recording named {body.recording_name!r}")
    playback = PaceCarPlayback(recording=recording, address=body.address,
                                 speed_scale=body.speed_scale, loop=body.loop)
    session.start_pace_car(playback)
    return {"ok": True}


@app.post("/api/pace_car/stop")
async def api_pace_car_stop(request: Request) -> dict:
    get_session(request).stop_pace_car()
    return {"ok": True}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "input":
                try:
                    msg = schemas.WebInputMessage(**data)
                except Exception:
                    continue
                controller = get_or_create_web_controller(ws, msg.controller_id)
                from app.controllers.base import ControllerInput

                controller.push(ControllerInput(
                    throttle=msg.throttle, brake=msg.brake,
                    lane_change=msg.lane_change, stop_pressed=msg.stop_pressed,
                ))
    except WebSocketDisconnect:
        manager.disconnect(ws)
