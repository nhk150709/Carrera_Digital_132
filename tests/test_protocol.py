from app.cu.protocol import (
    START_LIGHT_SEQUENCE,
    START_RACING,
    START_STOPPED,
    describe_start,
)


def test_describe_start_confirmed_values():
    assert describe_start(START_RACING) == "RACING"
    assert describe_start(START_STOPPED) == "STOPPED"
    assert describe_start(2) == "light sequence 1/6"
    assert describe_start(7) == "light sequence 6/6 (about to go)"


def test_describe_start_unknown_value_is_labeled_not_hidden():
    # 8/9 are documented range (0..9) but not observed/confirmed -- must
    # not silently look like a known state.
    assert "unknown" in describe_start(8)
    assert "unknown" in describe_start(9)


def test_start_light_sequence_matches_confirmed_range():
    assert set(START_LIGHT_SEQUENCE) == {2, 3, 4, 5, 6, 7}
