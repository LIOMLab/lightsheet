'''
Regression tests for src.gaussian.fwhm flat/empty-input crash fix.

Previously fwhm() raised ValueError on flat input, all-below-half-max
input, and empty input because max() was called on an empty sequence.
After the fix these return 0; normal Gaussian input is unchanged.
'''

from lightsheet.gaussian import fwhm


def test_fwhm_flat_input():
    '''Flat input has no half-max crossing — width is undefined, return 0.'''
    assert fwhm([5, 5, 5, 5, 5]) == 0


def test_fwhm_all_below_half_max():
    '''All-zero input: max_y/2.0 == 0, no x satisfies y[x] > 0, return 0.'''
    assert fwhm([0, 0, 0, 0, 0]) == 0


def test_fwhm_empty():
    '''Empty input must not raise; return 0.'''
    assert fwhm([]) == 0


def test_fwhm_normal_gaussian():
    '''Regression guard: real Gaussian data must return the same positive
    integer width as the pre-fix implementation.'''
    assert fwhm([0, 1, 5, 10, 5, 1, 0]) > 0
    # Pre-fix value: xs = [2,3,4] (values 5,10,5 > 10/2.0=5.0? No — 5 is
    # not > 5.0). Recompute: max_y=10, threshold=5.0, y[x]>5.0 -> x=3 only
    # (value 10). xs=[3], fwhm_val = 3-3+1 = 1.
    assert fwhm([0, 1, 5, 10, 5, 1, 0]) == 1
