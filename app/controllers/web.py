"""A "controller" whose input comes from a connected browser client (touch
buttons or captured keyboard, sent over the WebSocket) rather than a local
gamepad. This is what makes "others can access their own [screen and
controls] over the local network" work for players without a physical
controller attached to the Pi -- and it's also the easiest way to exercise
the whole app without any hardware at all.
"""
from __future__ import annotations

from app.controllers.base import ControllerInput, InputController
from app.controllers.mapping import SensitivityCurve


class WebController(InputController):
    def __init__(self, controller_id: str, curve: SensitivityCurve | None = None):
        self.controller_id = controller_id
        self.curve = curve or SensitivityCurve()
        self._raw = ControllerInput()

    def push(self, raw: ControllerInput) -> None:
        """Called by the network layer whenever a WebSocket message with
        fresh input arrives from this controller's browser client."""
        self._raw = raw

    def poll(self) -> ControllerInput:
        return ControllerInput(
            throttle=self.curve.apply_throttle(self._raw.throttle),
            brake=self.curve.apply_brake(self._raw.brake),
            lane_change=self._raw.lane_change,
            stop_pressed=self._raw.stop_pressed,
            overtake_pressed=self._raw.overtake_pressed,
        )
