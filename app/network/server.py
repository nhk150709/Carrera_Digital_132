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

from app.controllers.base import ControllerInput
from app.controllers.web import WebController
from app.cu.mock_client import MockCUClient
from app.network import schemas
from app.network.arduino_api import ArduinoBridge
from app.network.state_view import serialize
from app.race.forecast import generate_forecast
from app.race.fuel import TyreCompound
from app.race.models import RaceMode, RaceState, WeatherLevel
from app.race.pace_car import PaceCarPlayback
from app.race.safety_car import SafetyCarConfig
from app.race.session import RaceSession, SessionConfig
from app.race.strategy import RaceStrategy, recommend_strategy

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
        session.set_start_phase(phase)
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


@app.post("/api/cars/{address}/strategy")
async def api_strategy_set(address: int, body: schemas.StrategyRequest, request: Request) -> dict:
    session = get_session(request)
    if address not in session.engine.cars:
        raise HTTPException(404, f"no car at address {address}")
    try:
        compound = TyreCompound(body.compound)
    except ValueError:
        raise HTTPException(422, f"unknown compound {body.compound!r}")
    session.apply_strategy(RaceStrategy(
        address=address, fuel_load=body.fuel_load, compound=compound,
        planned_pit_laps=list(body.planned_pit_laps),
    ))
    return {"ok": True}


@app.get("/api/cars/{address}/strategy/recommend")
async def api_strategy_recommend(address: int, total_laps: int, avg_lap_seconds: float = 6.0) -> dict:
    plan = recommend_strategy(address, total_laps, avg_lap_seconds)
    return {
        "fuel_load": plan.fuel_load,
        "compound": plan.compound.value,
        "planned_pit_laps": plan.planned_pit_laps,
    }


@app.get("/api/cars/{address}/strategy/graph")
async def api_strategy_graph(address: int, total_laps: int, request: Request,
                                avg_lap_seconds: float = 6.0) -> dict:
    session = get_session(request)
    strategy = session.strategy_book.get(address) or recommend_strategy(address, total_laps, avg_lap_seconds)
    from app.race.strategy import project_plan

    projected = project_plan(strategy, total_laps, avg_lap_seconds)
    actual = [
        {"lap": lap.lap_number, "fuel": lap.fuel_at_lap, "tyre_wear": lap.tyre_wear_at_lap}
        for lap in session.engine.cars[address].laps
    ] if address in session.engine.cars else []
    return {
        "planned": [{"lap": p.lap, "fuel": p.fuel, "tyre_wear": p.tyre_wear} for p in projected],
        "actual": actual,
        "weather_forecast": session.forecast.visible_forecast() if session.forecast else [],
    }


@app.post("/api/cars/{address}/pit")
async def api_pit(address: int, body: schemas.PitRequest, request: Request) -> dict:
    get_session(request).set_in_pit(address, body.in_pit)
    return {"ok": True}


@app.post("/api/race/safety_car")
async def api_safety_car(body: schemas.SafetyCarRequest, request: Request) -> dict:
    session = get_session(request)
    if body.action == "trigger":
        session.safety_car.trigger()
    elif body.action == "end":
        session.safety_car.end()
    else:
        raise HTTPException(422, f"unknown action {body.action!r}")
    return {"ok": True}


@app.post("/api/race/safety_car/config")
async def api_safety_car_config(body: schemas.SafetyCarConfigRequest, request: Request) -> dict:
    session = get_session(request)
    session.safety_car.physically_present = body.physically_present
    session.safety_car.config = SafetyCarConfig(
        field_speed_cap=body.field_speed_cap,
        random_trigger_chance_per_lap=body.random_trigger_chance_per_lap,
    )
    return {"ok": True}


@app.post("/api/race/forecast")
async def api_forecast_generate(body: schemas.ForecastRequest, request: Request) -> dict:
    session = get_session(request)
    session.set_forecast(generate_forecast(body.total_laps, body.num_changes, rng=session._rng))
    return {"ok": True, "forecast": session.forecast.visible_forecast()}


@app.post("/api/race/forecast/clear")
async def api_forecast_clear(request: Request) -> dict:
    get_session(request).set_forecast(None)
    return {"ok": True}


@app.post("/api/cars/{address}/ghost")
async def api_ghost_set(address: int, body: schemas.GhostRequest, request: Request) -> dict:
    session = get_session(request)
    try:
        session.set_ghost(address, body.recording_name)
    except FileNotFoundError:
        raise HTTPException(404, f"no recording named {body.recording_name!r}")
    return {"ok": True}


@app.post("/api/cars/{address}/ghost/clear")
async def api_ghost_clear(address: int, request: Request) -> dict:
    get_session(request).clear_ghost(address)
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
                controller.push(ControllerInput(
                    throttle=msg.throttle, brake=msg.brake,
                    lane_change=msg.lane_change, stop_pressed=msg.stop_pressed,
                    overtake_pressed=msg.overtake_pressed,
                ))
    except WebSocketDisconnect:
        manager.disconnect(ws)
