"""Standalone mock Camera HAL for demo mode (D-08, D-09).

``MockCamera`` implements ``ICamera`` from scratch — fully decoupled from the
real ``Camera`` class internals so real-class refactors cannot break the mock
and the mock's behavior is explicit and auditable (D-08). It constructs with
no hardware (no ``pco`` import), populates the controller-read attributes with
synthetic defaults (D-09 — deterministic + shape-correct; pixel content is
out of scope), and returns synthetic ``uint16`` frames from ``grab_image``.

The attribute names EXACTLY match the real ``Camera`` (the controller reads
them as direct attributes, D-04/Pitfall 1): ``xsize``, ``ysize``,
``exposure_time``, ``shutter_mode``, ``line_time``, ``lightsheet_exposed_lines``,
``lightsheet_delay_lines``, ``recorder_timeout_status``, ``error``,
``error_message``, ``is_recording``, ``new_data_ready``, ``camera``.
"""

import logging
from typing import Any

import numpy as np

from lightsheet.hal.interfaces import ICamera

logger = logging.getLogger(__name__)


class MockCamera(ICamera):
    """Mock PCO camera for demo mode — implements ICamera with no hardware.

    Constructed with no ``pco`` SDK dependency. ``open()`` populates the
    controller-read attributes with synthetic defaults (2048x2048, 100 ms
    exposure, Rolling shutter) so the controller's image-viewer sizing and
    FrameViewer construction receive real shapes. ``grab_image()`` returns
    synthetic ``uint16`` frames of the right shape (D-09).

    All lifecycle verbs are no-ops ending with ``return None`` (AGENTS.md §10)
    so the controller's call sites are unchanged between real and demo runs.

    The controller-read attributes (``xsize`` / ``ysize`` / ``exposure_time``
    / ...) are declared here as plain class-level defaults so they override
    the abstract ``@property`` slots on ``ICameraCore`` (Python's ABC check
    runs at instantiation, before ``__init__`` sets instance attributes, so
    the abstract property descriptors must be shadowed at the class level).
    ``__init__`` / ``open()`` then set the real synthetic values as instance
    attributes, which is the surface the controller reads (D-04).
    """

    # Class-level defaults provide pre-__init__ synthetic values (the ABC
    # now declares these as annotations, so the override is no longer
    # required for ABC satisfaction, but the defaults are kept so the mock
    # has sensible values before open() runs). __init__/open() set the real
    # synthetic values as instance attributes.
    xsize: int | None = None
    ysize: int | None = None
    # Binning readback (D-02) — defaults to 1x1 (no binning), matching the
    # rig's current state per the rig probe. The real Camera reads
    # sdk.get_binning() in open()/arm(); the mock uses the class-level
    # default so the controller's read path is unchanged between real and
    # demo runs.
    binning_x: int = 1
    binning_y: int = 1
    exposure_time: float = 0.0
    shutter_mode: str = "Rolling"
    line_time: float | None = None
    lightsheet_exposed_lines: int = 0
    lightsheet_delay_lines: int = 0
    recorder_timeout_status: bool = False

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

        # HAL error surface (AGENTS.md §10) — cleared on construct.
        self.error = 0
        self.error_message = ""

        # Flags (bool) — mirror the real Camera's instance surface.
        self.is_recording = False
        self.new_data_ready = False

        # Other variables — populated by open() with synthetic defaults.
        # xsize / ysize / line_time / recorder_timeout_status keep their
        # class-level defaults (set above) so the ABC's abstract @property
        # slots are shadowed before __init__ runs; open() overwrites them
        # with the real synthetic values.
        self.camera = None
        self.bytes_per_image: int | None = None

        # Configurable settings — synthetic defaults (no config.ini read
        # required; D-09 — deterministic). MockCamera with empty/missing
        # config.ini still constructs with these synthetic defaults rather
        # than crashing.
        self.shutter_mode = "Rolling"
        self.exposure_time = 100.0 * 1e-3  # 100 ms, stored in seconds
        self.lightsheet_line_time = 48.80 * 1e-6  # 48.8 us, stored in seconds
        self.lightsheet_exposed_lines = 16
        self.lightsheet_delay_lines = 0
        self.recorder_timeout_interval = 5
        self.recorder_timeout_floor = 5
        self.recorder_timeout_safety_factor = 3.0
        self.default_line_time = self.lightsheet_line_time

        # Automatically open (sets xsize/ysize/line_time) on instance creation,
        # mirroring the real Camera.__init__ → open() flow.
        self.open()

    # ------------------------------------------------------------------ #
    # Lifecycle verbs — no-ops ending with ``return None`` (AGENTS.md §10).
    # ------------------------------------------------------------------ #

    def open(self) -> None:
        """Populate the controller-read attributes with synthetic defaults."""
        if self.verbose:
            print("Opening mock camera...")
        if self.camera is None:
            # Synthetic PCO edge dimensions (D-09 — shape-correct, pixel
            # content out of scope).
            self.xsize = 2048
            self.ysize = 2048
            # Binning readback (D-02) — synthetic 1x1 default mirrors the
            # real Camera.open() sdk.get_binning() readback.
            self.binning_x = 1
            self.binning_y = 1
            self.bytes_per_image = self.xsize * self.ysize * 2  # 16-bit
            self.line_time = self.default_line_time
            # Mark the mock as "opened" with a non-None sentinel so open()
            # is idempotent (mirrors the real Camera's `if self.camera is
            # None` guard).
            self.camera = "mock"
            if self.verbose:
                print(" Mock camera opened.")
        else:
            if self.verbose:
                print(" Mock camera already opened.")
        return None

    def close(self) -> None:
        if self.camera is not None:
            self.camera = None
            if self.verbose:
                print(" Mock camera closed.")
        return None

    def arm(self) -> None:
        return None

    def arm_scan(self) -> None:
        # Mirror the real Camera's unconditional recorder_timeout_status
        # reset (a worker that died mid-timeout must not poison the next
        # scan). The hardware branch is a no-op for the mock.
        self.recorder_timeout_status = False
        return None

    def disarm(self) -> None:
        return None

    def start_recorder(self, number_of_images: int) -> None:
        self.is_recording = True
        self.recorder_timeout_status = False
        return None

    def monitor_recorder(self, number_of_images: int) -> None:
        # The mock "completes" instantly — all images are ready.
        self.new_data_ready = True
        return None

    def stop_recorder(self) -> None:
        self.is_recording = False
        return None

    def delete_recorder(self) -> None:
        # Does NOT reset recorder_timeout_status — mirrors the real Camera
        # contract: the flag must survive long enough for the acquisition
        # worker's post-acquire check (see camera.py delete_recorder).
        self.new_data_ready = False
        return None

    # ------------------------------------------------------------------ #
    # Setters / getters / compounded methods (ICamera extended surface).
    # ------------------------------------------------------------------ #

    def grab_image(self, exposure_time_ms: int = 100) -> Any:
        """Return a synthetic uint16 frame of the current xsize-by-ysize shape."""
        if self.verbose:
            print("Grabbing a synthetic image...")
        assert self.xsize is not None and self.ysize is not None
        img = np.zeros((self.ysize, self.xsize), dtype=np.uint16)
        return img

    def copy_recorder_images(self, number_of_images: int) -> Any:
        """Return ``number_of_images`` synthetic uint16 frames."""
        assert self.xsize is not None and self.ysize is not None
        if self.new_data_ready:
            images = np.zeros(
                (number_of_images, self.ysize, self.xsize), dtype=np.uint16
            )
            self.new_data_ready = False
        else:
            # Mirror the real Camera's silent-data-loss fallback (the
            # known anti-pattern in AGENTS.md §13). The mock keeps it so
            # the controller's call sites are unchanged; the acquire path
            # guards against reaching it on timeout.
            images = np.zeros(
                (number_of_images, self.ysize, self.xsize), dtype=np.uint16
            )
        return images

    def get_camera_temperature(self) -> float | None:
        return 20.0

    def get_sensor_temperature(self) -> float | None:
        return 20.0

    def get_power_temperature(self) -> float | None:
        return 20.0

    def get_xsize(self) -> int | None:
        return self.xsize

    def get_ysize(self) -> int | None:
        return self.ysize

    def set_exposure_time(self, exposure_time_ms: int) -> None:
        self.exposure_time = float(exposure_time_ms) * 1e-3
        return None

    def set_trigger_mode(self, trigger_mode: str) -> None:
        """No-op — the mock camera has no hardware trigger to configure."""
        return None

    def set_lightsheet_mode(self) -> None:
        """No-op — the mock camera has no hardware timing registers to set."""
        return None

    def get_name(self) -> str | None:
        """Return the synthetic camera name used by the Properties dialog."""
        return "MockCamera"

    # Stubs for the extended ICamera getters — return synthetic defaults
    # mirroring real Camera's not-open path (the mock has no PCO SDK to query).
    def get_trigger_mode(self) -> str | None:
        return None

    def get_acquire_mode(self) -> str | None:
        return None

    def get_storage_mode(self) -> str | None:
        return None

    def get_recorder_submode(self) -> str | None:
        return None

    def get_exposure_time(self) -> int | None:
        return None

    def get_exposure_timebase(self) -> str | None:
        return None

    def get_delay_time(self) -> int | None:
        return None

    def get_delay_timebase(self) -> str | None:
        return None

    def get_pixel_rates(self) -> dict[str, object] | list:
        return {}

    def get_pixel_rate(self) -> str | None:
        return None

    def get_readout_format(self) -> str | None:
        return None

    def cfg_load_ini(self) -> None:
        # No-op — mock has no config.ini to read; the synthetic defaults
        # are already set in __init__.
        return None

    def cfg_save_ini(self) -> None:
        # No-op — mock does not persist config.
        return None

    def get_properties(self) -> dict[str, object]:
        """Return synthetic camera properties matching the keys the
        controller's ``Properties_Dialog.get_properties`` reads
        (camera name, x/y sizes, camera/sensor/power temperatures,
        trigger/acquire/storage modes, recorder submode). The values are
        deterministic synthetic defaults (D-09) so the dialog renders
        without raising under demo mode."""
        return {
            "camera name": "MockCamera",
            "x": self.xsize,
            "y": self.ysize,
            "camera temperature": 20.0,
            "sensor temperature": 20.0,
            "power temperature": 20.0,
            "trigger mode": "auto trigger",
            "acquire mode": "auto",
            "storage mode": "Recorder",
            "recorder submode": "sequence non blocking",
        }
