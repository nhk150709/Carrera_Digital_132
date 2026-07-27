from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ControllerInput:
    throttle: float = 0.0  # 0..1
    brake: float = 0.0  # 0..1
    lane_change: bool = False
    stop_pressed: bool = False
    overtake_pressed: bool = False  # push-to-pass


class InputController(ABC):
    controller_id: str

    @abstractmethod
    def poll(self) -> ControllerInput: ...
