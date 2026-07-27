"""Local physical gamepad support (Xbox controllers etc.) via pygame's
joystick module -- works over Bluetooth or USB, whatever the OS already
sees as a joystick device once paired.

Axis/button indices for triggers and buttons vary by OS/driver/controller
firmware, so they're configurable rather than hardcoded; the defaults
match a typical Xbox controller on Linux (verify with a quick
`python -m app.controllers.gamepad --probe` style check against your
actual hardware before trusting the defaults).

pygame is imported lazily so the rest of the app runs fine on a machine
that doesn't have it installed / has no controllers attached.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.controllers.base import ControllerInput, InputController
from app.controllers.mapping import SensitivityCurve


@dataclass
class GamepadAxisMap:
    throttle_axis: int = 5  # right trigger on most Linux SDL mappings
    brake_axis: int = 4  # left trigger
    # Triggers commonly report -1 (released) .. 1 (fully pressed); set to
    # False if your controller/driver reports 0..1 already.
    trigger_is_bipolar: bool = True
    lane_change_button: int = 0  # "A" button
    stop_button: int = 1  # "B" button


class GamepadController(InputController):
    def __init__(self, controller_id: str, joystick_index: int,
                 curve: SensitivityCurve | None = None,
                 axis_map: GamepadAxisMap | None = None):
        self.controller_id = controller_id
        self.joystick_index = joystick_index
        self.curve = curve or SensitivityCurve()
        self.axis_map = axis_map or GamepadAxisMap()
        self._joystick = None

    def open(self) -> None:
        import pygame

        pygame.joystick.init()
        self._joystick = pygame.joystick.Joystick(self.joystick_index)
        self._joystick.init()

    def _axis_to_unit(self, raw_value: float) -> float:
        if self.axis_map.trigger_is_bipolar:
            return max(0.0, min(1.0, (raw_value + 1.0) / 2.0))
        return max(0.0, min(1.0, raw_value))

    def poll(self) -> ControllerInput:
        import pygame

        if self._joystick is None:
            self.open()
        pygame.event.pump()
        j = self._joystick
        raw_throttle = self._axis_to_unit(j.get_axis(self.axis_map.throttle_axis))
        raw_brake = self._axis_to_unit(j.get_axis(self.axis_map.brake_axis))
        return ControllerInput(
            throttle=self.curve.apply_throttle(raw_throttle),
            brake=self.curve.apply_brake(raw_brake),
            lane_change=bool(j.get_button(self.axis_map.lane_change_button)),
            stop_pressed=bool(j.get_button(self.axis_map.stop_button)),
        )


def list_available_joysticks() -> list[str]:
    """Best-effort probe of currently connected joysticks/gamepads --
    useful when wiring up axis_map for real hardware."""
    import pygame

    pygame.joystick.init()
    names = []
    for i in range(pygame.joystick.get_count()):
        j = pygame.joystick.Joystick(i)
        j.init()
        names.append(f"{i}: {j.get_name()} ({j.get_numaxes()} axes, {j.get_numbuttons()} buttons)")
    return names
