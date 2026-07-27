"""Serializes a RaceSession into plain JSON-able dicts for the WebSocket
broadcast and REST snapshot endpoint."""
from __future__ import annotations

from dataclasses import asdict

from app.race.session import RaceSession


def serialize(session: RaceSession) -> dict:
    engine = session.engine
    return {
        "state": engine.state.value,
        "mode": engine.mode.value,
        "weather": session.weather.level.value,
        "rankings": [asdict(r) for r in engine.rankings()],
        "cars": {
            str(addr): {
                "address": car.address,
                "name": car.name,
                "controller_id": car.controller_id,
                "fuel": round(car.fuel, 1),
                "tyre_wear": round(car.tyre_wear, 1),
                "in_pit": car.in_pit,
                "jump_start": car.jump_start,
                "connected": car.controller_id is not None,
                "lap_count": car.lap_count,
                "best_lap": car.best_lap,
                "penalty_seconds": car.total_penalty_seconds,
                "recording": session.recorder.is_recording(addr),
            }
            for addr, car in engine.cars.items()
        },
        "pace_car": {
            "active": session.pace_playback is not None,
            "address": session.pace_playback.address if session.pace_playback else None,
            "speed_scale": session.pace_playback.speed_scale if session.pace_playback else None,
        },
        "debug_log": session.debug_log[-50:],
    }
