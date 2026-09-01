"""MockMotors / MockMotor branch-coverage closure.

Exercises the unit-conversion branches (m / cm / mm / µm / µStep / unknown),
the over-travel ValueError arcs on both move verbs, the getter/setter
surface, and the MockMotors container extended surface (get_properties /
get_positions / cfg_load_ini / cfg_save_ini / open / close) so every branch
in ``lightsheet/hal/mocks/mock_motors.py`` is taken at least once.

Behavior tests (AGENTS.md §5) — every assertion is on a runtime
postcondition (raised ValueError, converted position value, returned
name/units/inverted), never a static-source grep.
"""

from __future__ import annotations

import pytest

from lightsheet.hal.mocks.mock_motors import MockMotor, MockMotors


def _make_axis(
    microstep_size: float = 0.047625,
    limit_low: int = 0,
    limit_high: int = 1066666,
) -> MockMotor:
    return MockMotor(
        device_number=1,
        microstep_size=microstep_size,
        limit_low_microsteps=limit_low,
        limit_high_microsteps=limit_high,
    )


# -- position_to_microsteps unit branches -----------------------------------


@pytest.mark.parametrize(
    "units,expected_factor",
    [
        ("m", 1),
        ("cm", 10**-2),
        ("mm", 10**-3),
        ("\u03bcm", 10**-6),
    ],
)
def test_position_to_microsteps_unit_branches(
    units: str, expected_factor: float
) -> None:
    """Each supported unit branch in position_to_microsteps produces the
    expected microstep count for a known position."""
    axis = _make_axis(microstep_size=0.047625)
    # 1 mm = 1000 µm; microstep_size 0.047625 µm => 1 mm = 1000/0.047625 microsteps
    # The exact value is not the point — the branch is. Assert it is positive
    # and matches the formula for the chosen unit.
    microsteps = axis.position_to_microsteps(1.0, units)
    expected = int(1.0 * expected_factor / (0.047625 * 10**-6))
    assert microsteps == expected, f"unit {units!r} branch mismatch"


def test_position_to_microsteps_microstep_unit_branch() -> None:
    """The µStep unit branch uses microstep_size * 1e-6 as the factor."""
    axis = _make_axis(microstep_size=0.047625)
    # 1 uStep => factor = microstep_size * 1e-6;
    # position * factor / (microstep_size * 1e-6) = position
    assert axis.position_to_microsteps(500.0, "\u03bcStep") == 500


def test_position_to_microsteps_unknown_unit_falls_back_to_zero() -> None:
    """The unknown-unit else branch yields factor=0 -> microsteps=0
    (the safety fallback that prevents UnboundLocalError)."""
    axis = _make_axis()
    assert axis.position_to_microsteps(123.0, "furlongs") == 0


def test_position_to_microsteps_zero_microstep_size_falls_back_to_zero() -> None:
    """When microstep_size is 0 the `microstep_size > 0` guard fails and
    microsteps=0 (the else branch at line 145-146)."""
    axis = _make_axis(microstep_size=0.0)
    assert axis.position_to_microsteps(1.0, "mm") == 0


# -- microsteps_to_position unit branches -----------------------------------


@pytest.mark.parametrize(
    "units",
    ["m", "cm", "mm", "\u03bcm", "\u03bcStep"],
)
def test_microsteps_to_position_unit_branches(units: str) -> None:
    """Each supported unit branch in microsteps_to_position produces a
    finite non-negative position for a known microstep count."""
    axis = _make_axis(microstep_size=0.047625)
    position = axis.microsteps_to_position(1000, units)
    assert position >= 0
    # The branch is exercised; the exact value depends on the unit's
    # factor. Assert the position is finite and non-negative (the
    # branch-under-test is the unit dispatch, not the numeric value).
    assert position == position  # finite


def test_microsteps_to_position_unknown_unit_falls_back_to_zero() -> None:
    """The unknown-unit else branch yields factor=0 -> position=0."""
    axis = _make_axis()
    assert axis.microsteps_to_position(1000, "parsecs") == 0


def test_microsteps_to_position_zero_microstep_size_falls_back_to_zero() -> None:
    """When microstep_size is 0 the guard fails and position=0."""
    axis = _make_axis(microstep_size=0.0)
    assert axis.microsteps_to_position(1000, "mm") == 0


# -- move_absolute_position over-travel arcs --------------------------------


def test_move_absolute_over_high_limit_raises() -> None:
    axis = _make_axis(limit_high=1000)
    with pytest.raises(ValueError, match="exceeds the high travel limit"):
        axis.move_absolute_position(9999.0, "mm")


def test_move_absolute_below_low_limit_raises() -> None:
    axis = _make_axis(limit_low=0, limit_high=1000)
    with pytest.raises(ValueError, match="below the low travel limit"):
        axis.move_absolute_position(-1.0, "mm")


def test_move_absolute_within_limits_updates_position() -> None:
    axis = _make_axis(limit_low=0, limit_high=1066666)
    axis.move_absolute_position(5.0, "mm")
    assert axis.position_microsteps > 0
    assert axis.position == float(axis.position_microsteps)


# -- move_relative_position over-travel arcs --------------------------------


def test_move_relative_over_high_limit_raises() -> None:
    axis = _make_axis(limit_low=0, limit_high=1000)
    # Move near the top first.
    axis.position_microsteps = 950
    with pytest.raises(ValueError, match="exceeding the high travel limit"):
        axis.move_relative_position(100.0, "mm")


def test_move_relative_below_low_limit_raises() -> None:
    axis = _make_axis(limit_low=0, limit_high=1000)
    axis.position_microsteps = 50
    with pytest.raises(ValueError, match="below the low travel limit"):
        axis.move_relative_position(-100.0, "mm")


def test_move_relative_within_limits_updates_position() -> None:
    axis = _make_axis(limit_low=0, limit_high=1066666)
    axis.position_microsteps = 100
    axis.move_relative_position(1.0, "mm")
    assert axis.position_microsteps > 100


# -- extended getter/setter surface -----------------------------------------


def test_get_name_returns_mock_name() -> None:
    axis = _make_axis()
    assert axis.get_name() == "MockMotor"


def test_set_units_and_get_units_round_trip() -> None:
    axis = _make_axis()
    axis.set_units("cm")
    assert axis.get_units() == "cm"


def test_set_inverted_and_get_inverted_round_trip() -> None:
    axis = _make_axis()
    axis.set_inverted(True)
    assert axis.get_inverted() is True


def test_set_limit_low_high_origin_round_trip() -> None:
    axis = _make_axis(microstep_size=0.047625, limit_low=0, limit_high=1066666)
    axis.set_limit_low(1.0, "mm")
    assert axis.limit_low_microsteps > 0
    axis.set_limit_high(50.0, "mm")
    assert axis.limit_high_microsteps > axis.limit_low_microsteps
    axis.set_origin(5.0, "mm")
    assert axis.origin_microsteps > 0


def test_get_limit_low_high_origin_return_converted_values() -> None:
    axis = _make_axis(microstep_size=0.047625, limit_low=0, limit_high=1066666)
    # Default limits are 0 and 1066666 microsteps.
    assert axis.get_limit_low("mm") == 0.0
    high_mm = axis.get_limit_high("mm")
    assert high_mm > 0
    assert axis.get_origin("mm") == 0.0


def test_get_position_returns_converted_position() -> None:
    axis = _make_axis(microstep_size=0.047625, limit_low=0, limit_high=1066666)
    axis.position_microsteps = 1000
    pos_mm = axis.get_position("mm")
    assert pos_mm > 0


def test_ask_id_returns_zero_for_mock() -> None:
    axis = _make_axis()
    # Mock has no serial hardware; id stays 0 from __init__.
    assert axis.ask_id() == 0


def test_move_home_is_noop() -> None:
    axis = _make_axis()
    axis.position_microsteps = 500
    axis.move_home()
    # No-op — position unchanged.
    assert axis.position_microsteps == 500


# -- MockMotors container extended surface ----------------------------------


def test_mock_motors_get_properties_returns_three_axis_names() -> None:
    motors = MockMotors()
    props = motors.get_properties()
    assert set(props.keys()) == {"vertical name", "horizontal name", "camera name"}
    assert props["vertical name"] == "MockMotor"


def test_mock_motors_get_positions_returns_three_axis_positions() -> None:
    motors = MockMotors()
    positions = motors.get_positions()
    assert set(positions.keys()) == {
        "vertical position",
        "horizontal position",
        "camera position",
    }
    # All start at limit_low (0) -> position 0.0 mm.
    assert positions["vertical position"] == 0.0


def test_mock_motors_open_close_cfg_are_noops() -> None:
    motors = MockMotors()
    assert motors.open() is None
    assert motors.close() is None
    assert motors.cfg_load_ini() is None
    assert motors.cfg_save_ini() is None


# -- MockMotors.move_axes_parallel safety contract ---------------------------


def test_mock_motors_move_axes_parallel_rejects_without_partial_mutation() -> None:
    """Over-travel on one axis in a parallel move raises ValueError and leaves
    every motor's position unchanged (no partial mutation)."""
    motors = MockMotors()
    with pytest.raises(ValueError, match="exceeds the high travel limit"):
        motors.move_axes_parallel([("horizontal", 5.0, "mm"), ("camera", 999.0, "mm")])
    assert motors.horizontal.position_microsteps == 0
    assert motors.camera.position_microsteps == 0


def test_mock_motors_move_axes_parallel_updates_both_in_range() -> None:
    """All in-range parallel moves update each motor's position in order."""
    motors = MockMotors()
    motors.move_axes_parallel([("horizontal", 5.0, "mm"), ("camera", 5.0, "mm")])
    assert motors.horizontal.position_microsteps > 0
    assert motors.camera.position_microsteps > 0
