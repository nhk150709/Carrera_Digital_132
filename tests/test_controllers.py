import pytest

from app.controllers.base import ControllerInput
from app.controllers.mapping import SensitivityCurve
from app.controllers.web import WebController


def test_curve_exponent_reduces_low_end_sensitivity():
    curve = SensitivityCurve(throttle_exponent=2.0)
    assert curve.apply_throttle(0.5) == pytest.approx(0.25)
    assert curve.apply_throttle(1.0) == pytest.approx(1.0)


def test_curve_gain_caps_max_output():
    curve = SensitivityCurve(brake_gain=0.5)
    assert curve.apply_brake(1.0) == pytest.approx(0.5)


def test_curve_clamps_to_unit_range():
    curve = SensitivityCurve(throttle_gain=2.0)
    assert curve.apply_throttle(1.0) == 1.0


def test_web_controller_applies_curve_on_poll():
    controller = WebController("p1", curve=SensitivityCurve(throttle_exponent=2.0))
    controller.push(ControllerInput(throttle=0.5, brake=0.0, lane_change=True, stop_pressed=False))
    result = controller.poll()
    assert result.throttle == pytest.approx(0.25)
    assert result.lane_change is True


def test_web_controller_defaults_to_zero_before_any_push():
    controller = WebController("p1")
    result = controller.poll()
    assert result.throttle == 0.0
    assert result.stop_pressed is False
