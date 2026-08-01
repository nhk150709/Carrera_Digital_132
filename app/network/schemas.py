"""Request bodies for the monitor's manual CU-write endpoints. Every field
maps 1:1 onto a real carreralib.cu.ControlUnit write command -- see
app/cu/base.py for what each one does and app/network/server.py for the
endpoints that call them."""
from __future__ import annotations

from pydantic import BaseModel


class SpeedRequest(BaseModel):
    address: int
    value: int


class BrakeRequest(BaseModel):
    address: int
    value: int


class FuelRequest(BaseModel):
    address: int
    value: int


class PressRequest(BaseModel):
    button_id: int


class IgnoreRequest(BaseModel):
    mask: int


class PositionRequest(BaseModel):
    address: int
    position: int


class LapRequest(BaseModel):
    value: int
