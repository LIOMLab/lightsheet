"""
Regression tests for src.gaussian.fwhm flat/empty-input crash fix.

Previously fwhm() raised ValueError on flat input, all-below-half-max
input, and empty input because max() was called on an empty sequence.
After the fix these return 0; normal Gaussian input is unchanged.

Extended (TST-02) with characterization tests for fwhm on a known
Gaussian and for the gaussian()/func() point values, so the Phase 5
god-object split and Phase 7 Qt6 migration cannot silently change the
beam-width model. Tests execute the real functions (AGENTS.md §5).
"""

import numpy as np

from lightsheet.gaussian import func, fwhm, gaussian


def test_fwhm_flat_input() -> None:
    """Flat input has no half-max crossing — width is undefined, return 0."""
    assert fwhm([5, 5, 5, 5, 5]) == 0


def test_fwhm_all_below_half_max() -> None:
    """All-zero input: max_y/2.0 == 0, no x satisfies y[x] > 0, return 0."""
    assert fwhm([0, 0, 0, 0, 0]) == 0


def test_fwhm_empty() -> None:
    """Empty input must not raise; return 0."""
    assert fwhm([]) == 0


def test_fwhm_normal_gaussian() -> None:
    """Regression guard: real Gaussian data must return the same positive
    integer width as the pre-fix implementation."""
    assert fwhm([0, 1, 5, 10, 5, 1, 0]) > 0
    # Pre-fix value: xs = [2,3,4] (values 5,10,5 > 10/2.0=5.0? No — 5 is
    # not > 5.0). Recompute: max_y=10, threshold=5.0, y[x]>5.0 -> x=3 only
    # (value 10). xs=[3], fwhm_val = 3-3+1 = 1.
    assert fwhm([0, 1, 5, 10, 5, 1, 0]) == 1


# --------------------------------------------------------------------------- #
# TST-02 characterization: known-Gaussian width + gaussian()/func() values.
# --------------------------------------------------------------------------- #


def test_fwhm_known_gaussian() -> None:
    """A sampled Gaussian with a known half-max width returns that width.

    Construct a Gaussian with sigma=2, peak=10, centered at x=10 on a 21-
    sample grid. Half-max = 5.0; the samples strictly above 5.0 span the
    central region. fwhm counts those samples (max-min+1)."""
    x = np.arange(21)
    y = gaussian(x, a=10.0, x0=10.0, sigma=2.0)
    # The continuous FWHM is 2*sqrt(2*ln(2))*sigma ≈ 4.71 → 5 samples above
    # half-max on this grid. Lock the integer count the function returns.
    assert fwhm(list(y)) == 5


def test_gaussian_func_values() -> None:
    """gaussian() returns a*exp(-(x-x0)^2/(2*sigma^2)) at each point."""
    x = np.array([0.0, 1.0, 2.0])
    out = gaussian(x, a=3.0, x0=1.0, sigma=1.0)
    # x=0: 3*exp(-1/2); x=1: 3*exp(0)=3; x=2: 3*exp(-1/2)
    assert out[1] == 3.0
    assert np.isclose(out[0], 3.0 * np.exp(-0.5))
    assert np.isclose(out[2], 3.0 * np.exp(-0.5))


def test_func_beam_width_values() -> None:
    """func() is the Gaussian beam-width model w0*sqrt(1+((x-x0)/xR)^2)+offset."""
    x = np.array([0.0, 5.0, 10.0])
    out = func(x, w0=2.0, x0=5.0, xR=5.0, offset=0.0)
    # x=5 (beam waist): 2*sqrt(1+0)+0 = 2.0
    assert np.isclose(out[1], 2.0)
    # x=0 and x=10 are symmetric: 2*sqrt(1+1)+0 = 2*sqrt(2)
    expected = 2.0 * np.sqrt(2.0)
    assert np.isclose(out[0], expected)
    assert np.isclose(out[2], expected)
