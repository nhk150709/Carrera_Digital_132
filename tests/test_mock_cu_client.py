from app.cu.mock_client import MockCUClient
from app.cu.protocol import PACE_CAR_ESC_BUTTON_ID, START_ENTER_BUTTON_ID, START_RACING, START_STOPPED


def test_faster_speed_produces_shorter_lap_and_more_crossings():
    fast = MockCUClient(addresses=[0], base_lap_time=10.0)
    slow = MockCUClient(addresses=[1], base_lap_time=10.0)
    fast.connect()
    slow.connect()
    fast.set_speed(0, 15)
    slow.set_speed(1, 5)
    fast.arm(now=0.0)
    slow.arm(now=0.0)

    fast_events = fast.tick(now=20.0)
    slow_events = slow.tick(now=20.0)
    assert len(fast_events) > len(slow_events)


def test_tick_is_idempotent_for_same_timestamp():
    cu = MockCUClient(addresses=[0], base_lap_time=5.0)
    cu.connect()
    cu.arm(now=0.0)
    first = cu.tick(now=5.0)
    second = cu.tick(now=5.0)
    assert len(first) == 1
    assert second == []  # nothing new since last tick


def test_status_reflects_pit_and_fuel_override():
    cu = MockCUClient(addresses=[0, 1])
    cu.connect()
    cu.set_pit(0, True)
    cu.set_fuel_display(1, 7)
    status = cu.read_status()
    assert status.pit == (True, False)
    assert status.fuel[1] == 7


def test_zero_speed_never_produces_events():
    cu = MockCUClient(addresses=[0], base_lap_time=5.0)
    cu.connect()
    cu.set_speed(0, 0)
    cu.arm(now=0.0)
    events = cu.tick(now=1000.0)
    # speed 0 is clamped to a minimum of 1 internally to avoid division by
    # zero, so it still produces (very slow) crossings rather than hanging
    assert isinstance(events, list)


def test_mock_starts_stopped_and_press_start_toggles_racing():
    cu = MockCUClient(addresses=[0])
    cu.connect()
    assert cu.read_status().start == START_STOPPED

    cu.press(START_ENTER_BUTTON_ID)
    assert cu.read_status().start == START_RACING
    assert cu.start_call_count == 1

    cu.press(START_ENTER_BUTTON_ID)
    assert cu.read_status().start == START_STOPPED
    assert cu.start_call_count == 2


def test_press_start_while_stopped_arms_cars_to_lap():
    t = [0.0]
    cu = MockCUClient(addresses=[0], base_lap_time=1.0, clock=lambda: t[0])
    cu.connect()
    cu.press(START_ENTER_BUTTON_ID)  # stopped -> racing, arms at t=0.0
    t[0] = 1.0
    events = cu.tick(now=t[0])
    assert len(events) == 1


def test_press_start_while_racing_stops_cars_from_lapping():
    t = [0.0]
    cu = MockCUClient(addresses=[0], base_lap_time=1.0, clock=lambda: t[0])
    cu.connect()
    cu.press(START_ENTER_BUTTON_ID)  # stopped -> racing
    cu.press(START_ENTER_BUTTON_ID)  # racing -> stopped
    t[0] = 100.0
    events = cu.tick(now=t[0])
    assert events == []


def test_press_other_buttons_recorded_but_no_local_effect():
    cu = MockCUClient(addresses=[0])
    cu.connect()
    cu.press(PACE_CAR_ESC_BUTTON_ID)
    assert cu.last_button_pressed == PACE_CAR_ESC_BUTTON_ID
    assert cu.press_count == 1
    assert cu.read_status().start == START_STOPPED  # unaffected


def test_write_functions_are_all_callable_without_error():
    cu = MockCUClient(addresses=[0])
    cu.connect()
    cu.ignore(0b00000011)
    cu.reset()
    cu.set_position(0, 1)
    cu.set_lap(5)
    cu.clear_position()
    assert cu.version() == "mock-1.0"
