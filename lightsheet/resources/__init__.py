"""Package marker for ``lightsheet.resources`` package data.

The directory holds packaged assets (icons, images, calibration JSON)
referenced via ``package-data`` in ``pyproject.toml``. It must be a real
package so ``importlib.resources`` and non-editable wheel installs carry
the data files reliably.
"""
