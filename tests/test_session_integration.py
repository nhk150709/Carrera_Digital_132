from app.controllers.base import ControllerInput
from app.controllers.web import WebController
from app.cu.mock_client import MockCUClient
from app.race.models import RaceState
from app.race.session import RaceSession, SessionConfig


class _FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def make_session(addresses=(0, 1)):
    clock = _FakeClock()
    cu = MockCUClient(addresses=list(addresses), base_lap_time=1.0, clock=clock)
    cu.connect()
    session = RaceSession(cu, SessionConfig(addresses=list(addresses)), clock=clock)
    # These tests predate the random-breakdown feature and aren't testing
    # it; keep them deterministic rather than depending on RNG luck.
    session.reliability.config.breakdown_chance_per_second = 0.0
    return session, cu


def test_full_race_flow_produces_laps_and_ranking():
    session, cu = make_session()
    clock: _FakeClock = session.clock

    p0 = WebController("p0")
    p1 = WebController("p1")
    session.assign_controller(0, p0)
    session.assign_controller(1, p1)

    session.begin_countdown()
    session.go()
    p0.push(ControllerInput(throttle=1.0))
    p1.push(ControllerInput(throttle=0.3))

    for _ in range(50):
        clock.advance(0.2)
        session.tick()

    ranking = session.engine.rankings()
    assert ranking[0].address == 0  # faster car leads
    assert ranking[0].lap_count > 0
    assert session.engine.cars[0].fuel < 100.0  # fuel drained while driving


def test_last_input_reflects_current_throttle_and_brake():
    session, cu = make_session(addresses=(0,))
    p0 = WebController("p0")
    session.assign_controller(0, p0)
    session.go()
    p0.push(ControllerInput(throttle=0.6, brake=0.2))
    session.tick()
    assert session.last_input[0] == (0.6, 0.2)


def test_stop_button_pauses_race_and_can_penalize_trigger():
    session, cu = make_session(addresses=(0,))
    clock: _FakeClock = session.clock
    p0 = WebController("p0")
    session.assign_controller(0, p0)
    session.begin_countdown()
    session.go()

    p0.push(ControllerInput(throttle=0.5, stop_pressed=True))
    session.tick()
    assert session.engine.state == RaceState.PAUSED


def test_early_movement_during_countdown_flags_jump_start():
    session, cu = make_session(addresses=(0,))
    clock: _FakeClock = session.clock
    p0 = WebController("p0")
    session.assign_controller(0, p0)
    session.begin_countdown()
    p0.push(ControllerInput(throttle=0.8))
    session.tick()
    assert session.engine.cars[0].jump_start is True


def test_controller_addressed_cars_use_unsupported_write_guard_gracefully_with_mock():
    # MockCUClient is permissive (allows all addresses) so the full pipeline
    # is testable without hardware; the real CarreralibCUClient would raise
    # UnsupportedCommand for addresses 0-5 and session.tick() logs it rather
    # than crashing (see test below with a stub raising client).
    session, cu = make_session(addresses=(0,))
    p0 = WebController("p0")
    session.assign_controller(0, p0)
    session.begin_countdown()
    session.go()
    p0.push(ControllerInput(throttle=1.0))
    session.tick()
    assert session.debug_log == []  # no rejection logged against the mock


def test_unsupported_command_is_logged_not_raised():
    from app.cu.base import CUClient, UnsupportedCommand
    from app.cu.protocol import Status

    class RejectingCU(CUClient):
        def connect(self): pass
        def disconnect(self): pass
        def read_status(self): return Status(fuel=(0,), pit=(False,), start=0, mode=0, display=1)
        def poll_timer(self): return []
        def set_speed(self, address, value): raise UnsupportedCommand("nope")
        def set_brake(self, address, value): raise UnsupportedCommand("nope")
        def set_fuel_display(self, address, value): raise UnsupportedCommand("nope")
        def start(self): pass

    session = RaceSession(RejectingCU(), SessionConfig(addresses=[0]), clock=_FakeClock())
    p0 = WebController("p0")
    session.assign_controller(0, p0)
    session.begin_countdown()
    session.go()
    p0.push(ControllerInput(throttle=1.0))
    session.tick()  # must not raise
    assert any("rejected" in line for line in session.debug_log)
