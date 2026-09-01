"""Standalone mock Camera HAL for demo mode.

Implements ``ICamera`` with no ``pco`` SDK dependency, returning synthetic
``uint16`` frames. Attribute names match the real ``Camera`` exactly.
"""

import logging
import time
from typing import Any

import numpy as np

from lightsheet.hal.interfaces import ICamera

logger = logging.getLogger(__name__)


class MockCamera(ICamera):
    """Mock PCO camera for demo mode — implements ICamera with no hardware."""

    # Class-level defaults shadow the abstract @property slots before __init__.
    xsize: int | None = None
    ysize: int | None = None
    binning_x: int = 1
    binning_y: int = 1
    exposure_time: float = 0.0
    shutter_mode: str = "Rolling"
    line_time: float | None = None
    lightsheet_exposed_lines: int = 0
    lightsheet_delay_lines: int = 0
    recorder_timeout_status: bool = False
    # When True, monitor_recorder sleeps for exposure_time before marking data
    # ready, making per-plane sequencing observable in the demo GUI. Never used
    # on the real rig; set only by _build_demo_bundle in __main__.py.
    simulate_timing: bool = False
    # Scripted-intensity hook: when set to callable(index, exposure_s) -> int,
    # copy_recorder_images fills each frame with that uint16 value so intensity
    # tracks a synthetic profile. Default None preserves zero-fill behavior.
    scripted_intensity_fn: Any = None
    scripted_frame_index: int = 0

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

        self.error = 0
        self.error_message = ""

        self.is_recording = False
        self.new_data_ready = False

        self.camera = None
        self.bytes_per_image: int | None = None

        # Synthetic defaults (no config.ini read required).
        self.shutter_mode = "Rolling"
        self.exposure_time = 100.0 * 1e-3  # 100 ms, stored in seconds
        self.lightsheet_line_time = 48.80 * 1e-6  # 48.8 us, stored in seconds
        self.lightsheet_exposed_lines = 16
        self.lightsheet_delay_lines = 0
        self.recorder_timeout_interval = 5
        self.recorder_timeout_floor = 5
        self.recorder_timeout_safety_factor = 3.0
        self.default_line_time = self.lightsheet_line_time

        # Automatically open, mirroring real Camera.__init__ → open() flow.
        self.open()

    def open(self) -> None:
        """Populate the controller-read attributes with synthetic defaults."""
        if self.verbose:
            print("Opening mock camera...")
        if self.camera is None:
            self.xsize = 2048
            self.ysize = 2048
            self.binning_x = 1
            self.binning_y = 1
            self.bytes_per_image = self.xsize * self.ysize * 2  # 16-bit
            self.line_time = self.default_line_time
            # Non-None sentinel makes open() idempotent.
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
        # Unconditional reset so a worker that died mid-timeout doesn't
        # poison the next scan.
        self.recorder_timeout_status = False
        return None

    def disarm(self) -> None:
        return None

    def start_recorder(self, number_of_images: int) -> None:
        self.is_recording = True
        self.recorder_timeout_status = False
        return None

    def monitor_recorder(self, number_of_images: int) -> None:
        # When simulate_timing is True (demo GUI only), sleep for exposure_time
        # so the per-plane cycle is observable at a realistic pace.
        if self.simulate_timing:
            time.sleep(self.exposure_time)
        self.new_data_ready = True
        return None

    def stop_recorder(self) -> None:
        self.is_recording = False
        return None

    def delete_recorder(self) -> None:
        # Does NOT reset recorder_timeout_status — the flag must survive for
        # the acquisition worker's post-acquire check.
        self.new_data_ready = False
        return None

    def grab_image(self, exposure_time_ms: int = 100) -> Any:
        """Return a synthetic uint16 frame of the current xsize-by-ysize shape."""
        if self.verbose:
            print("Grabbing a synthetic image...")
        assert self.xsize is not None and self.ysize is not None
        img = np.zeros((self.ysize, self.xsize), dtype=np.uint16)
        return img

    def copy_recorder_images(self, number_of_images: int) -> Any:
        """Return ``number_of_images`` synthetic uint16 frames.

        When ``scripted_intensity_fn`` is set, each frame is filled with the
        uint16 value returned by the hook; otherwise frames are zero-filled.
        """
        assert self.xsize is not None and self.ysize is not None
        if self.new_data_ready:
            if self.scripted_intensity_fn is not None:
                fill = int(
                    self.scripted_intensity_fn(
                        self.scripted_frame_index, self.exposure_time
                    )
                )
                fill = max(0, min(fill, 65535))
                images = np.full(
                    (number_of_images, self.ysize, self.xsize),
                    fill,
                    dtype=np.uint16,
                )
                self.scripted_frame_index += 1
            else:
                images = np.zeros(
                    (number_of_images, self.ysize, self.xsize), dtype=np.uint16
                )
            self.new_data_ready = False
        else:
            # Silent-data-loss fallback mirrors real Camera contract;
            # acquire path guards against it.
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

    def set_scripted_intensity_fn(self, fn: Any) -> None:
        """Set the scripted-intensity callback and reset the frame index."""
        self.scripted_intensity_fn = fn
        self.scripted_frame_index = 0
        return None

    def set_trigger_mode(self, trigger_mode: str) -> None:
        return None

    def set_lightsheet_mode(self) -> None:
        return None

    def get_name(self) -> str | None:
        """Return the synthetic camera name used by the Properties dialog."""
        return "MockCamera"

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

    def get_pixel_rates(self) -> dict[str, object] | list:  # ty: ignore[missing-type-argument]
        return {}

    def get_pixel_rate(self) -> str | None:
        return None

    def get_readout_format(self) -> str | None:
        return None

    def cfg_load_ini(self) -> None:
        return None

    def cfg_save_ini(self) -> None:
        return None

    def get_properties(self) -> dict[str, object]:
        """Return synthetic camera properties for the Properties dialog."""
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
