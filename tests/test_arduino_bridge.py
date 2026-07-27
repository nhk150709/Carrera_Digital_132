from app.controllers.web import WebController
from app.controllers.base import ControllerInput
from app.cu.mock_client import MockCUClient
from app.network.arduino_api import ArduinoBridge
from app.race.session import RaceSession, SessionConfig


class FakeSerial:
    def __init__(self):
        self.written: list[str] = []
        self._inbound: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data.decode("ascii"))

    def readline(self) -> bytes:
        if self._inbound:
            return self._inbound.pop(0)
        return b""

    def close(self) -> None:
        pass


def make_bridge() -> tuple[ArduinoBridge, FakeSerial]:
    bridge = ArduinoBridge(port="/dev/fake")
    fake = FakeSerial()
    bridge._serial = fake  # bypass open(); no real hardware in tests
    return bridge, fake


def test_sync_writes_state_fuel_pit_rank_lines():
    bridge, fake = make_bridge()
    cu = MockCUClient(addresses=[0, 1])
    cu.connect()
    session = RaceSession(cu, SessionConfig(addresses=[0, 1]))
    session.engine.assign(0, name="Red")
    session.engine.assign(1, name="Blue")

    bridge.sync(session)

    joined = "".join(fake.written)
    assert "STATE idle\n" in joined
    assert "FUEL 0:100,1:100\n" in joined
    assert "PIT 0:0,1:0\n" in joined
    assert "RANK 0:Red:1,1:Blue:2\n" in joined


def test_jump_flag_sent_once_on_rising_edge():
    bridge, fake = make_bridge()
    cu = MockCUClient(addresses=[0])
    cu.connect()
    session = RaceSession(cu, SessionConfig(addresses=[0]))
    session.engine.begin_countdown(session.clock())
    session.engine.report_early_movement(0, session.clock())

    bridge.sync(session)
    assert any(line == "JUMP 0\n" for line in fake.written)

    fake.written.clear()
    bridge.sync(session)
    assert not any(line.startswith("JUMP") for line in fake.written)


def test_inbound_stop_button_triggers_session_stop():
    bridge, fake = make_bridge()
    cu = MockCUClient(addresses=[0])
    cu.connect()
    session = RaceSession(cu, SessionConfig(addresses=[0]))
    session.go()
    bridge._inbound.put("BTN STOP 0")  # bypasses the reader thread for a deterministic test

    bridge._apply_inbound(session)

    from app.race.models import RaceState
    assert session.engine.state == RaceState.PAUSED


def test_inbound_early_movement_flags_jump_start():
    bridge, fake = make_bridge()
    cu = MockCUClient(addresses=[0])
    cu.connect()
    session = RaceSession(cu, SessionConfig(addresses=[0]))
    session.begin_countdown()
    bridge._inbound.put("EARLY 0")

    bridge._apply_inbound(session)

    assert session.engine.cars[0].jump_start is True


def test_malformed_inbound_line_ignored_without_crashing():
    bridge, fake = make_bridge()
    cu = MockCUClient(addresses=[0])
    cu.connect()
    session = RaceSession(cu, SessionConfig(addresses=[0]))
    bridge._inbound.put("GARBAGE not a real line")
    bridge._apply_inbound(session)  # must not raise
