"""Standalone mock SigGen HAL for demo mode.

Implements ``ISigGen`` with no NI-DAQmx dependency, reusing
``lightsheet.waveforms`` to produce scan ramps bit-identical to a real run.
"""

import logging

import numpy as np

from lightsheet.channel_map import ChannelMap
from lightsheet.hal.interfaces import ICameraCore, ISigGen
from lightsheet.waveforms import sawtooth, squarewave, staircase

logger = logging.getLogger(__name__)


class MockSigGen(ISigGen):
    """Mock signal generator for demo mode — implements ISigGen with no DAQ."""

    # Class-level defaults shadow the abstract @property slots before __init__.
    galvo_left_amplitude: float = 0.0
    galvo_right_amplitude: float = 0.0
    galvo_left_offset: float = 0.0
    galvo_right_offset: float = 0.0
    etl_left_amplitude: float = 0.0
    etl_right_amplitude: float = 0.0
    etl_left_offset: float = 0.0
    etl_right_offset: float = 0.0
    waveform_cycles: int | None = None
    waveform_metadata: dict | None = None

    def __init__(self, camera: ICameraCore) -> None:
        self.camera = camera

        self.error = 0
        self.error_message = ""

        # L2 DAQ gate parity — the mock has no DAQ hardware, but the
        # controller-reachable set_laser2_gate contract and the normalized
        # L2 window must exist so the demo path and conformance tests do not
        # AttributeError.
        self._laser2_daq = None
        self._laser2_gate_enabled = False
        self.waveform_laser2_window = None

        # Hardcoded synthetic defaults mirroring real SigGen config.ini.
        self.sample_rate = 40000
        self.galvo_pre_time = 0.001
        self.galvo_scan_time = 0.100
        self.galvo_reset_time = 0.025
        self.galvo_post_time = 0.001
        self.galvo_activated = True
        self.galvo_inverted = False
        self.galvo_left_amplitude = 1.0
        self.galvo_left_offset = 0.5
        self.galvo_right_amplitude = 1.0
        self.galvo_right_offset = 0.5
        self.etl_activated = False
        self.etl_steps = 5
        self.etl_left_amplitude = 1.0
        self.etl_left_offset = 0.5
        self.etl_right_amplitude = 1.0
        self.etl_right_offset = 0.5

        self.waveform_camera = None
        self.waveform_galvo_left = None
        self.waveform_galvo_right = None
        self.waveform_etl_left = None
        self.waveform_etl_right = None
        self.waveform_metadata = None
        self.waveform_cycles = None

        self.task_galvo_etl = None
        self.task_camera = None

        self.galvo_left_right_swap = False
        self.channel_map = ChannelMap()

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    def set_laser2_gate(self, enabled: bool) -> None:
        """Parity with real SigGen.set_laser2_gate — stores the enabled flag.
        The mock has no DAQ hardware so no task is configured."""
        self._laser2_gate_enabled = bool(enabled)

    def create_scanner(self) -> None:
        return None

    def start_scanner(self) -> None:
        return None

    def monitor_scanner(self) -> None:
        return None

    def stop_scanner(self) -> None:
        return None

    def delete_scanner(self) -> None:
        return None

    def compute_scan_waveforms(self) -> None:
        """Compute Galvo + ETL scan ramps and Camera Exposure waveforms."""
        if self.camera.shutter_mode == "Lightsheet":
            self.galvo_scan_time = self.camera.line_time * self.camera.ysize
            camera_active_time = (
                self.camera.line_time * self.camera.lightsheet_exposed_lines
            )
            camera_delay_time = 3 * self.camera.line_time
            camera_delay_samples = int(np.ceil(camera_delay_time * self.sample_rate))
        elif self.camera.shutter_mode == "Rolling":
            self.galvo_scan_time = self.camera.exposure_time + (
                self.camera.line_time * 0.5 * self.camera.ysize
            )
            camera_active_time = self.galvo_scan_time - (
                self.camera.line_time * 0.5 * self.camera.ysize
            )
            camera_delay_time = 3 * self.camera.line_time + (
                self.camera.line_time * 0.5 * self.camera.ysize
            )
            camera_delay_samples = int(np.ceil(camera_delay_time * self.sample_rate))
        elif self.camera.shutter_mode == "Global":
            self.galvo_scan_time = self.camera.exposure_time
            camera_active_time = self.galvo_scan_time
            camera_delay_time = (0.5 * self.camera.ysize + 1) * self.camera.line_time
            camera_delay_samples = int(np.ceil(camera_delay_time * self.sample_rate))
        else:
            raise Exception("camera shutter mode not supported")

        self.waveform_metadata = {
            "Camera Shutter Mode": str(self.camera.shutter_mode),
            "Camera Exposure Time": str(self.camera.exposure_time),
            "Galvo Activated": str(self.galvo_activated),
            "Galvo Inverted": str(self.galvo_inverted),
            "Galvo Left Amplitude": str(self.galvo_left_amplitude),
            "Galvo Left Offset": str(self.galvo_left_offset),
            "Galvo Right Amplitude": str(self.galvo_right_amplitude),
            "Galvo Right Offset": str(self.galvo_right_offset),
            "ETL Activated": str(self.etl_activated),
            "ETL Steps": str(self.etl_steps),
            "ETL Left Amplitude": str(self.etl_left_amplitude),
            "ETL Left Offset": str(self.etl_left_offset),
            "ETL Right Amplitude": str(self.etl_right_amplitude),
            "ETL Right Offset": str(self.etl_right_offset),
        }

        self.waveform_cycles = self.etl_steps

        galvo_pre_samples = int(np.ceil(self.galvo_pre_time * self.sample_rate))
        galvo_scan_samples = int(np.ceil(self.galvo_scan_time * self.sample_rate))
        galvo_reset_samples = int(np.ceil(self.galvo_reset_time * self.sample_rate))
        galvo_post_samples = int(np.ceil(self.galvo_post_time * self.sample_rate))
        galvo_period_samples = (
            galvo_pre_samples
            + galvo_scan_samples
            + galvo_reset_samples
            + galvo_post_samples
        )
        galvo_shift = camera_delay_samples
        galvo_repeat = self.waveform_cycles
        galvo_inverted = self.galvo_inverted

        etl_step_samples = galvo_period_samples
        etl_steps = self.waveform_cycles
        etl_shift = (
            camera_delay_samples
            - int(np.ceil(galvo_reset_samples / 2))
            - galvo_post_samples
        )

        camera_pre_samples = galvo_pre_samples
        camera_active_samples = int(np.ceil(camera_active_time * self.sample_rate))
        camera_post_samples = (
            galvo_period_samples - camera_pre_samples - camera_active_samples
        )
        camera_repeat = self.waveform_cycles

        # Store derived counts so conformance tests can recompute expected waveforms.
        self._galvo_pre_samples = galvo_pre_samples
        self._galvo_scan_samples = galvo_scan_samples
        self._galvo_reset_samples = galvo_reset_samples
        self._galvo_post_samples = galvo_post_samples
        self._galvo_shift = galvo_shift
        self._etl_step_samples = etl_step_samples
        self._etl_shift = etl_shift
        self._camera_pre_samples = camera_pre_samples
        self._camera_active_samples = camera_active_samples
        self._camera_post_samples = camera_post_samples

        self.total_samples = galvo_period_samples * self.waveform_cycles
        self.total_time = self.total_samples / self.sample_rate

        self.waveform_camera = squarewave(
            pre_samples=camera_pre_samples,
            active_samples=camera_active_samples,
            post_samples=camera_post_samples,
            shift=0,
            repeat=camera_repeat,
            inverted=False,
        )

        # Normalized L2 exposure window — parity with real SigGen.
        self.waveform_laser2_window = self.waveform_camera.astype(float)

        self.waveform_galvo_left = sawtooth(
            activated=self.galvo_activated,
            pre_samples=galvo_pre_samples,
            trace_samples=galvo_scan_samples,
            retrace_samples=galvo_reset_samples,
            post_samples=galvo_post_samples,
            shift=galvo_shift,
            repeat=galvo_repeat,
            amplitude=self.galvo_left_amplitude,
            offset=self.galvo_left_offset,
            inverted=galvo_inverted,
            filtered=True,
        )
        self.waveform_galvo_right = sawtooth(
            activated=self.galvo_activated,
            pre_samples=galvo_pre_samples,
            trace_samples=galvo_scan_samples,
            retrace_samples=galvo_reset_samples,
            post_samples=galvo_post_samples,
            shift=galvo_shift,
            repeat=galvo_repeat,
            amplitude=self.galvo_right_amplitude,
            offset=self.galvo_right_offset,
            inverted=galvo_inverted,
            filtered=True,
        )

        self.waveform_etl_left = staircase(
            activated=self.etl_activated,
            step_samples=etl_step_samples,
            nbr_steps=etl_steps,
            shift=etl_shift,
            amplitude=self.etl_left_amplitude,
            offset=self.etl_left_offset,
            direction="down",
            filtered=True,
        )
        self.waveform_etl_right = staircase(
            activated=self.etl_activated,
            step_samples=etl_step_samples,
            nbr_steps=etl_steps,
            shift=etl_shift,
            amplitude=self.etl_right_amplitude,
            offset=self.etl_right_offset,
            direction="up",
            filtered=True,
        )
        return None

    def update_all(
        self,
        left_galvo: float,
        right_galvo: float,
        left_etl: float,
        right_etl: float,
    ) -> None:
        return None

    def update_galvos(self, left_galvo: float, right_galvo: float) -> None:
        return None

    def update_etls(self, left_etl: float, right_etl: float) -> None:
        return None

    def cfg_load_ini(self) -> None:
        return None

    def cfg_save_ini(self) -> None:
        return None
