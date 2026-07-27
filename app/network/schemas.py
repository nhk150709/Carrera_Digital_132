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
    overtake_pressed: bool = False


class RecordingStartRequest(BaseModel):
    address: int
    name: str


class PaceCarPlayRequest(BaseModel):
    recording_name: str
    address: int = 7
    speed_scale: float = 1.0
    loop: bool = False


class StrategyRequest(BaseModel):
    fuel_load: float = 100.0
    compound: str = "medium"  # "soft" | "medium" | "hard"
    planned_pit_laps: list[int] = []


class StrategyRecommendRequest(BaseModel):
    total_laps: int
    avg_lap_seconds: float = 6.0


class PitRequest(BaseModel):
    in_pit: bool


class SafetyCarRequest(BaseModel):
    action: str  # "trigger" | "end"


class SafetyCarConfigRequest(BaseModel):
    physically_present: bool = False
    field_speed_cap: int = 5
    random_trigger_chance_per_lap: float = 0.0


class ForecastRequest(BaseModel):
    total_laps: int
    num_changes: int = 2


class GhostRequest(BaseModel):
    recording_name: str
