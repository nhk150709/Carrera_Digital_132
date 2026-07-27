from __future__ import annotations

from pydantic import BaseModel


class AssignRequest(BaseModel):
    controller_id: str
    name: str = ""


class ModeRequest(BaseModel):
    mode: str  # "race" | "time_attack"


class WeatherRequest(BaseModel):
    level: str  # "dry" | "damp" | "wet"


class StopRequest(BaseModel):
    triggered_by: int | None = None
    penalize_trigger: bool = False


class PenaltyRequest(BaseModel):
    address: int
    seconds: float
    reason: str = "manual"


class SensitivityRequest(BaseModel):
    throttle_exponent: float = 1.0
    throttle_gain: float = 1.0
    brake_exponent: float = 1.0
    brake_gain: float = 1.0


class WebInputMessage(BaseModel):
    type: str = "input"
    controller_id: str
    throttle: float = 0.0
    brake: float = 0.0
    lane_change: bool = False
    stop_pressed: bool = False


class RecordingStartRequest(BaseModel):
    address: int
    name: str


class PaceCarPlayRequest(BaseModel):
    recording_name: str
    address: int = 7
    speed_scale: float = 1.0
    loop: bool = False
