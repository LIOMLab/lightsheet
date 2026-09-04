"""
TST-02 pure-logic characterization tests for lightsheet.waveforms.

These tests capture today's behavior of the pure-numpy scan-waveform
generators (squarewave / sawtooth / staircase) so the Phase 5 god-object
split and Phase 7 Qt6 migration cannot silently change the waveform
contract. They execute the real functions and assert on runtime output
(shape, dtype, values) — no static-source grep (AGENTS.md §5).

Mirrors the established test/test_gaussian.py style: direct import, no
fixtures, no mocks, single-assert tests with docstrings.
"""

import numpy as np

from lightsheet.waveforms import sawtooth, squarewave, staircase

# --------------------------------------------------------------------------- #
# squarewave — camera exposure trigger generator
# --------------------------------------------------------------------------- #


def test_squarewave_shape() -> None:
    """Period = pre + active + post; output = period tiled `repeat` times."""
    out = squarewave(
        pre_samples=5,
        active_samples=10,
        post_samples=5,
        shift=0,
        repeat=2,
        inverted=False,
    )
    assert out.shape == (40,)


def test_squarewave_dtype() -> None:
    """squarewave builds on np.full(..., False) → bool dtype."""
    out = squarewave(
        pre_samples=5,
        active_samples=10,
        post_samples=5,
        shift=0,
        repeat=1,
        inverted=False,
    )
    assert out.dtype == np.bool_


def test_squarewave_values() -> None:
    """Active region is True, pre/post are False; repeat tiles the period."""
    out = squarewave(
        pre_samples=5,
        active_samples=10,
        post_samples=5,
        shift=0,
        repeat=1,
        inverted=False,
    )
    # pre=False, active=True, post=False
    assert not out[0] and not out[4]
    assert out[5] and out[14]
    assert not out[15] and not out[19]


def test_squarewave_inverted() -> None:
    """inverted=True flips every element of the period."""
    out = squarewave(
        pre_samples=5,
        active_samples=10,
        post_samples=5,
        shift=0,
        repeat=1,
        inverted=False,
    )
    inv = squarewave(
        pre_samples=5,
        active_samples=10,
        post_samples=5,
        shift=0,
        repeat=1,
        inverted=True,
    )
    assert np.array_equal(inv, ~out)


def test_squarewave_shift_rotates_period() -> None:
    """shift>0 rotates the period vector right by `shift` before tiling.

    period = [F]*5 + [T]*10 + [F]*5 (20 elements). shift=2 wraps the last 2
    (both False) to the front, so the active region starts at index 7
    (shift 2 + pre 5) instead of index 5."""
    out = squarewave(
        pre_samples=5,
        active_samples=10,
        post_samples=5,
        shift=2,
        repeat=1,
        inverted=False,
    )
    # The last 2 elements of the period (both False) wrap to the front.
    assert not out[0] and not out[1]
    # The pre region (5 False) follows, then the active region at index 7.
    assert not out[2] and not out[6]
    assert out[7] and out[16]
    assert not out[17] and not out[19]


# --------------------------------------------------------------------------- #
# sawtooth — galvo scan ramp generator
# --------------------------------------------------------------------------- #


def test_sawtooth_shape() -> None:
    """Period = pre + trace + retrace + post; output tiled `repeat` times."""
    out = sawtooth(
        activated=True,
        pre_samples=5,
        trace_samples=10,
        retrace_samples=5,
        post_samples=5,
        shift=0,
        repeat=2,
        amplitude=1.0,
        offset=0.0,
        inverted=False,
        filtered=False,
    )
    assert out.shape == (50,)


def test_sawtooth_dtype() -> None:
    """sawtooth returns a float array (linspace + amplitude scaling)."""
    out = sawtooth(
        activated=True,
        pre_samples=5,
        trace_samples=10,
        retrace_samples=5,
        post_samples=5,
        shift=0,
        repeat=1,
        amplitude=1.0,
        offset=0.0,
        inverted=False,
        filtered=False,
    )
    assert np.issubdtype(out.dtype, np.floating)


def test_sawtooth_values_unfiltered() -> None:
    """Unfiltered ramp: pre=0, trace rises 0→1, retrace falls 1→0, post=0."""
    out = sawtooth(
        activated=True,
        pre_samples=5,
        trace_samples=10,
        retrace_samples=5,
        post_samples=5,
        shift=0,
        repeat=1,
        amplitude=1.0,
        offset=0.0,
        inverted=False,
        filtered=False,
    )
    assert out[0] == 0.0  # pre region
    assert out[5] == 0.0  # trace starts at 0 (linspace(0,1,10)[0])
    assert out[14] == 1.0  # trace ends at 1 (linspace(0,1,10)[-1])
    assert out[15] == 1.0  # retrace starts at 1 (linspace(1,0,5)[0])
    assert out[19] == 0.0  # retrace ends at 0
    assert out[20] == 0.0  # post region


def test_sawtooth_deactivated_is_offset() -> None:
    """activated=False returns a flat array at `offset`."""
    out = sawtooth(
        activated=False,
        pre_samples=5,
        trace_samples=10,
        retrace_samples=5,
        post_samples=5,
        shift=0,
        repeat=1,
        amplitude=1.0,
        offset=0.5,
        inverted=False,
        filtered=False,
    )
    assert out.shape == (25,)
    assert np.all(out == 0.5)


def test_sawtooth_amplitude_offset_scaling() -> None:
    """amplitude * ramp + offset scales and shifts the unfiltered ramp."""
    out = sawtooth(
        activated=True,
        pre_samples=5,
        trace_samples=10,
        retrace_samples=5,
        post_samples=5,
        shift=0,
        repeat=1,
        amplitude=2.0,
        offset=1.0,
        inverted=False,
        filtered=False,
    )
    # trace peak = amplitude * 1 + offset = 3.0
    assert out[14] == 3.0
    # pre region = amplitude * 0 + offset = 1.0
    assert out[0] == 1.0


# --------------------------------------------------------------------------- #
# staircase — ETL focus-step generator
# --------------------------------------------------------------------------- #


def test_staircase_shape() -> None:
    """total = step_samples * nbr_steps; output is that length."""
    out = staircase(
        activated=True,
        step_samples=10,
        nbr_steps=3,
        shift=0,
        amplitude=2.0,
        offset=1.0,
        direction="up",
        filtered=False,
    )
    assert out.shape == (30,)


def test_staircase_dtype() -> None:
    """staircase returns a float array."""
    out = staircase(
        activated=True,
        step_samples=10,
        nbr_steps=3,
        shift=0,
        amplitude=2.0,
        offset=1.0,
        direction="up",
        filtered=False,
    )
    assert np.issubdtype(out.dtype, np.floating)


def test_staircase_up_step_values() -> None:
    """Up staircase: step_rise = amplitude/(nbr_steps-1); levels offset+i*rise."""
    out = staircase(
        activated=True,
        step_samples=10,
        nbr_steps=3,
        shift=0,
        amplitude=2.0,
        offset=1.0,
        direction="up",
        filtered=False,
    )
    # step_rise = 2/(3-1) = 1.0; levels = 1, 2, 3
    assert out[0] == 1.0
    assert out[10] == 2.0
    assert out[20] == 3.0


def test_staircase_down_step_values() -> None:
    """Down staircase: levels descend from offset+amplitude by step_rise."""
    out = staircase(
        activated=True,
        step_samples=10,
        nbr_steps=3,
        shift=0,
        amplitude=2.0,
        offset=1.0,
        direction="down",
        filtered=False,
    )
    # starts at offset+amplitude = 3, descends by 1.0 each step → 3, 2, 1
    assert out[0] == 3.0
    assert out[10] == 2.0
    assert out[20] == 1.0


def test_staircase_single_step_is_midlevel() -> None:
    """nbr_steps=1 special case: flat at offset + amplitude/2."""
    out = staircase(
        activated=True,
        step_samples=10,
        nbr_steps=1,
        shift=0,
        amplitude=2.0,
        offset=1.0,
        direction="up",
        filtered=False,
    )
    assert out.shape == (10,)
    assert np.all(out == 2.0)  # 1 + 2/2 = 2.0


def test_staircase_deactivated_is_offset() -> None:
    """activated=False returns a flat array at `offset`."""
    out = staircase(
        activated=False,
        step_samples=10,
        nbr_steps=3,
        shift=0,
        amplitude=2.0,
        offset=1.0,
        direction="up",
        filtered=False,
    )
    assert out.shape == (30,)
    assert np.all(out == 1.0)


# --------------------------------------------------------------------------- #
# EDGE cases (empty / single-element inputs — flagged-unverified assumptions)
# --------------------------------------------------------------------------- #


def test_squarewave_empty_period() -> None:
    """EDGE: pre=active=post=0 → empty period, tiled empty → empty array.
    Today's behavior: returns an empty bool array (no crash). Captured so a
    refactor cannot silently start raising on empty input."""
    out = squarewave(
        pre_samples=0,
        active_samples=0,
        post_samples=0,
        shift=0,
        repeat=2,
        inverted=False,
    )
    assert out.shape == (0,)
    assert out.dtype == np.bool_


def test_sawtooth_single_trace_sample() -> None:
    """EDGE: trace_samples=1 → linspace(0,1,1) = [0.0]. Today's behavior:
    the trace is a single 0.0 sample (linspace endpoint semantics). Captured
    so a refactor cannot silently change single-sample trace behavior."""
    out = sawtooth(
        activated=True,
        pre_samples=0,
        trace_samples=1,
        retrace_samples=1,
        post_samples=0,
        shift=0,
        repeat=1,
        amplitude=1.0,
        offset=0.0,
        inverted=False,
        filtered=False,
    )
    assert out.shape == (2,)
    # trace[0] = linspace(0,1,1)[0] = 0.0; retrace[0] = linspace(1,0,1)[0] = 1.0
    assert out[0] == 0.0
    assert out[1] == 1.0
