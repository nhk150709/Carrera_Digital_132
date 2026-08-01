"""Serializes a RaceSession into plain JSON-able dicts for the WebSocket
broadcast and REST snapshot endpoint."""
from __future__ import annotations

from dataclasses import asdict

from app.race.session import RaceSession


def serialize(session: RaceSession) -> dict:
    engine = session.engine
    now = session.clock()
    strategies = session.strategy_book.all()

    return {
        "cu_backend": session.cu_backend,
        "state": engine.state.value,
        "start_phase": session.start_phase,
        "mode": engine.mode.value,
        "weather": session.weather.level.value,
        "weather_forecast": session.forecast.visible_forecast() if session.forecast else [],
        "last_stop_triggered_by": engine.last_stop_triggered_by,
        "safety_car": {
            "active": session.safety_car.active,
            "physically_present": session.safety_car.physically_present,
            "field_speed_cap": session.safety_car.config.field_speed_cap,
        },
        "rankings": [asdict(r) for r in engine.rankings()],
        "grid_order": engine.grid_order(),
        "cars": {
            str(addr): {
                "address": car.address,
                "name": car.name,
                "controller_id": car.controller_id,
                "fuel": round(car.fuel, 1),
                "tyre_wear": round(car.tyre_wear, 1),
                "compound": session.fuel.compound(addr).value,
                "in_pit": car.in_pit,
                "jump_start": car.jump_start,
                "connected": car.controller_id is not None,
                "lap_count": car.lap_count,
                "best_lap": car.best_lap,
                "penalty_seconds": car.total_penalty_seconds,
                "recording": session.recorder.is_recording(addr),
                "throttle": session.last_input.get(addr, (0.0, 0.0))[0],
                "brake": session.last_input.get(addr, (0.0, 0.0))[1],
                "overtake_active": session.overtake.is_active(addr, now),
                "overtake_cooldown_remaining": round(session.overtake.cooldown_remaining(addr, now), 1),
                "broken_down": session.reliability.is_broken_down(addr),
                "repair_progress": round(session.reliability.repair_progress(addr), 2),
                "ghost_delta": session.ghost_delta(addr),
                "strategy": {
                    "fuel_load": strategies[addr].fuel_load,
                    "compound": strategies[addr].compound.value,
                    "planned_pit_laps": strategies[addr].planned_pit_laps,
                } if addr in strategies else None,
            }
            for addr, car in engine.cars.items()
        },
        "pace_car": {
            "active": session.pace_playback is not None,
            "address": session.pace_playback.address if session.pace_playback else None,
            "speed_scale": session.pace_playback.speed_scale if session.pace_playback else None,
        },
        "events": list(session.events),
        "cu_status": session.raw_cu_status(),
        "debug_log": session.debug_log[-50:],
    }
