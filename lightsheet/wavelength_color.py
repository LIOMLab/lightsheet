"""Shared wavelength-to-color mapping for the lightsheet display and metadata paths.

This module is the single source of truth for the per-channel hex color
derived from a laser wavelength (nm). It is consumed by:

* the Zarr metadata path (``frame_saver_controller._build_omero_channels``
  writes the color into the OME-NGFF omero.channels[].color attribute), and
* the display path (``controller._on_channel_radio_clicked`` passes the color
  as the ``tint`` argument to ``ImageView.setImage`` so the operator can
  visually distinguish L1 from L2 in demo mode where the frames are
  otherwise identical).

The mapping covers the wavelengths configured on this rig: 488 nm -> cyan,
555 nm -> green, 640/647 nm -> red. Any other wavelength falls back to white
so an unrecognised channel is still visible in viewers that honour the omero
channel color. The operator may override the recorded color at UAT.
"""

from __future__ import annotations


def wavelength_to_hex(wavelength: int) -> str:
    """Map a laser wavelength (nm) to a 6-char hex color string (no ``#``).

    Parameters
    ----------
    wavelength:
        The laser wavelength in nanometers.

    Returns
    -------
    A 6-character upper-hex color string with no ``#`` prefix
    (e.g. ``"00FF00"`` for 555 nm). Unrecognised wavelengths return
    ``"FFFFFF"`` (white) so the channel is still visible.
    """
    if wavelength == 488:
        return "00FFFF"  # cyan
    if wavelength == 555:
        return "00FF00"  # green
    if wavelength in (640, 647):
        return "FF0000"  # red
    return "FFFFFF"  # white fallback
