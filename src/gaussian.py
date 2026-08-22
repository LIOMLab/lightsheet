"""
Created on April 1st, 2022
"""

import numpy as np


# Math functions
def gaussian(x: np.ndarray, a: float, x0: float, sigma: float) -> np.ndarray:
    """1D Gaussian Function"""
    return a * np.exp(-((x - x0) ** 2) / (2 * sigma**2))


def func(x: np.ndarray, w0: float, x0: float, xR: float, offset: float) -> np.ndarray:
    """Gaussian Beam Width Function"""
    return w0 * (1 + ((x - x0) / xR) ** 2) ** 0.5 + offset


def fwhm(y: list[float]) -> int:
    """Full width at half maximum"""
    if len(y) == 0:
        return 0
    max_y = max(y)  # Find the maximum y value
    if max_y == min(y):
        # Flat input (all values equal): there is no peak, so the half-max
        # width is undefined. Return 0 rather than reporting the full span.
        return 0
    xs = [x for x in range(len(y)) if y[x] > max_y / 2.0]
    if len(xs) == 0:
        # All values at or below half-max: no x satisfies y[x] > max_y/2.0,
        # so the half-max width is undefined. Return 0 rather than crashing
        # on max() of an empty sequence.
        return 0
    fwhm_val = max(xs) - min(xs) + 1
    return fwhm_val
