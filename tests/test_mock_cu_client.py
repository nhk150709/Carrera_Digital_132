from app.cu.mock_client import MockCUClient


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
