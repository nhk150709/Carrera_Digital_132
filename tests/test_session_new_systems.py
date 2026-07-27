import random

from app.controllers.base import ControllerInput
from app.controllers.web import WebController
from app.cu.mock_client import MockCUClient
from app.race.fuel import TyreCompound
from app.race.reliability import ReliabilityConfig
from app.race.safety_car import SafetyCarConfig
from app.race.strategy import RaceStrategy
from app.race.session import RaceSession, SessionConfig


class _FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def make_session(addresses=(0,), **kwargs):
    clock = _FakeClock()
    cu = MockCUClient(addresses=list(addresses), base_lap_time=1.0, clock=clock)
    cu.connect()
    session = RaceSession(cu, SessionConfig(addresses=list(addresses), **kwargs), clock=clock)
    # Deterministic by default; the dedicated breakdown test overrides this.
    session.reliability.config.breakdown_chance_per_second = 0.0
    return session, cu, clock


def test_strategy_sets_starting_fuel_and_compound():
    session, cu, clock = make_session()
    session.apply_strategy(RaceStrategy(address=0, fuel_load=40.0, compound=TyreCompound.SOFT))
    assert session.fuel.fuel(0) == 40.0
    assert session.fuel.compound(0) == TyreCompound.SOFT


def test_pit_entry_triggers_tyre_change_event_and_reset():
    session, cu, clock = make_session()
    for _ in range(50):
        session.fuel.update(0, throttle=1.0, brake=1.0, dt=0.1)
    assert session.fuel.tyre_wear(0) > 0

    session.set_in_pit(0, True)
    assert session.fuel.tyre_wear(0) == 0.0
    assert any(e["type"] == "tyre_change" for e in session.events)


def test_fuel_never_refills_even_while_in_pit_across_ticks():
    session, cu, clock = make_session()
    p0 = WebController("p0")
    session.assign_controller(0, p0)
    session.go()
    p0.push(ControllerInput(throttle=1.0))
    for _ in range(20):
        clock.advance(0.2)
        session.tick()
    fuel_before_pit = session.engine.cars[0].fuel
    session.set_in_pit(0, True)
    for _ in range(20):
        clock.advance(0.2)
        session.tick()
    assert session.engine.cars[0].fuel <= fuel_before_pit


def test_overtake_button_activates_boost_and_logs_event():
    session, cu, clock = make_session()
    p0 = WebController("p0")
    session.assign_controller(0, p0)
    session.go()
    p0.push(ControllerInput(throttle=1.0, overtake_pressed=True))
    session.tick()
    assert session.overtake.is_active(0, clock())
    assert any(e["type"] == "overtake_activated" for e in session.events)


def test_overtake_costs_extra_fuel_versus_normal_driving():
    boosted, cu1, clock1 = make_session(addresses=(0,))
    normal, cu2, clock2 = make_session(addresses=(0,))
    for s, c in ((boosted, clock1), (normal, clock2)):
        p = WebController("p0")
        s.assign_controller(0, p)
        s.go()
        p.push(ControllerInput(throttle=1.0, overtake_pressed=(s is boosted)))
    for _ in range(10):
        clock1.advance(0.2)
        boosted.tick()
        clock2.advance(0.2)
        normal.tick()
    assert boosted.engine.cars[0].fuel < normal.engine.cars[0].fuel


def test_safety_car_caps_speed_field_wide():
    session, cu, clock = make_session(
        addresses=(0,), safety_car_physically_present=False,
    )
    session.safety_car.config = SafetyCarConfig(field_speed_cap=3)
    p0 = WebController("p0")
    session.assign_controller(0, p0)
    session.go()
    p0.push(ControllerInput(throttle=1.0))
    session.tick()
    normal_speed = cu._speed[0]

    session.safety_car.trigger()
    p0.push(ControllerInput(throttle=1.0))
    session.tick()
    assert cu._speed[0] <= 3
    assert cu._speed[0] < normal_speed


def test_breakdown_forces_zero_speed_until_repaired_in_pit():
    session, cu, clock = make_session(addresses=(0,))
    session.reliability = session.reliability.__class__(ReliabilityConfig(
        breakdown_chance_per_second=1000.0, repair_seconds=5.0,
    ))
    p0 = WebController("p0")
    session.assign_controller(0, p0)
    session.go()
    p0.push(ControllerInput(throttle=1.0))

    session.tick()  # dt==0 on the first tick by design, no breakdown chance yet
    clock.advance(0.1)
    session.tick()  # certain to break down this tick (chance_per_second=1.0)
    assert session.reliability.is_broken_down(0)
    assert any(e["type"] == "breakdown" for e in session.events)
    assert cu._speed[0] == 0

    # Prevent the absurdly high test probability from immediately causing
    # another breakdown once this one is repaired -- tick_repair()'s own
    # mechanics are already covered directly in test_reliability.py; this
    # test is only exercising the session wiring.
    session.reliability.config.breakdown_chance_per_second = 0.0

    session.set_in_pit(0, True)
    seen_events = []
    for _ in range(30):
        clock.advance(0.2)
        session.tick()
        seen_events.extend(session.events)  # events is cleared each tick
    assert not session.reliability.is_broken_down(0)
    assert any(e["type"] == "repair_complete" for e in seen_events)


def test_final_lap_event_fires_once():
    from app.race.engine import RaceEngineConfig

    session, cu, clock = make_session(addresses=(0,), engine_config=RaceEngineConfig(target_laps=3))
    p0 = WebController("p0")
    session.assign_controller(0, p0)
    session.go()
    p0.push(ControllerInput(throttle=1.0))
    seen = 0
    for _ in range(400):
        clock.advance(0.05)
        session.tick()
        if any(e["type"] == "final_lap" for e in session.events):
            seen += 1
        if session.engine.state.value == "finished":
            break
    assert seen == 1


def test_stop_attribution_visible_on_engine_and_cleared_on_new_countdown():
    session, cu, clock = make_session()
    p0 = WebController("p0")
    session.assign_controller(0, p0)
    session.go()
    p0.push(ControllerInput(throttle=1.0, stop_pressed=True))
    session.tick()
    assert session.engine.last_stop_triggered_by == 0

    session.resume()
    session.begin_countdown()
    assert session.engine.last_stop_triggered_by is None


def test_forecast_changes_weather_based_on_leader_lap_not_wall_clock():
    from app.race.forecast import ForecastEntry, WeatherForecast
    from app.race.models import WeatherLevel

    session, cu, clock = make_session(addresses=(0,))
    session.set_forecast(WeatherForecast([
        ForecastEntry(lap=2, predicted_level=WeatherLevel.WET, confidence=0.6, actual_level=WeatherLevel.WET),
    ]))
    p0 = WebController("p0")
    session.assign_controller(0, p0)
    session.go()
    p0.push(ControllerInput(throttle=1.0))

    assert session.weather.level == WeatherLevel.DRY
    seen_events = []
    for _ in range(60):
        clock.advance(0.2)
        session.tick()
        seen_events.extend(session.events)
        if session.engine.cars[0].lap_count >= 2:
            break
    assert session.weather.level == WeatherLevel.WET
    assert any(e["type"] == "weather_change" for e in seen_events)


def test_ghost_delta_available_after_lap_and_ghost_set(tmp_path):
    session, cu, clock = make_session(addresses=(0,))
    session.recorder.storage_dir = tmp_path
    session.recorder.start(0, "ghost1", now=0.0)
    from app.race.recorder import EventType
    session.recorder.record(0, EventType.LAP, 1.0, now=5.0)
    recording = session.recorder.stop(0)
    session.recorder.save(recording)

    session.set_ghost(0, "ghost1")
    session.engine.go(0.0)
    session.engine.handle_timer_event(0, timestamp=6.0, sector=0)  # lap 1 in 6s, ghost did it in 5s
    delta = session.ghost_delta(0)
    assert delta == 1.0
