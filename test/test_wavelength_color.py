"""Pure-logic tests for the shared wavelength-to-color mapping.

The mapping is consumed by both the Zarr metadata path
(``frame_saver_controller._build_omero_channels``) and the display path
(``controller._on_channel_radio_clicked`` -> ``ImageView.setImage(tint=...)``).
It must return a 6-char hex string (no ``#`` prefix) for every rig wavelength,
with a white fallback for unrecognised wavelengths so an unknown channel is
still visible in viewers that honour the omero channel color.
"""

from __future__ import annotations

from lightsheet.wavelength_color import wavelength_to_hex


def test_wavelength_555_returns_green() -> None:
    assert wavelength_to_hex(555) == "00FF00"


def test_wavelength_647_returns_red() -> None:
    assert wavelength_to_hex(647) == "FF0000"


def test_wavelength_640_returns_red() -> None:
    """640 nm is the alternate red-line wavelength; it maps to red too."""
    assert wavelength_to_hex(640) == "FF0000"


def test_wavelength_488_returns_cyan() -> None:
    assert wavelength_to_hex(488) == "00FFFF"


def test_unknown_wavelength_returns_white_fallback() -> None:
    assert wavelength_to_hex(999) == "FFFFFF"


def test_returns_six_char_hex_no_prefix() -> None:
    """Every return value is a 6-character upper-hex string with no ``#``."""
    for wl in (488, 555, 640, 647, 999):
        v = wavelength_to_hex(wl)
        assert len(v) == 6, f"{wl} -> {v!r} is not 6 chars"
        assert not v.startswith("#"), f"{wl} -> {v!r} has a # prefix"
        # Must be valid uppercase hex.
        int(v, 16)
