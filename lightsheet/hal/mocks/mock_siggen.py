"""Standalone mock SigGen HAL for demo mode (D-08, D-09).

``MockSigGen`` implements ``ISigGen`` from scratch — fully decoupled from the
real ``SigGen`` class internals so real-class refactors cannot break the
mock and the mock's behavior is explicit and auditable (D-08). It constructs
with no NI-DAQmx dependency and reuses ``lightsheet.waveforms`` (the pure-
numpy generators) to produce scan ramps **bit-identical** to a real run
(D-09 — the TST-03 golden-master fidelity property). The DAQ task lifecycle
verbs (``create_scanner`` / ``start_scanner`` / ``stop_scanner`` /
``delete_scanner``) are no-ops returning ``None`` (AGENTS.md §10) so the
controller's call sites are unchanged between real and demo runs.

The controller-read attributes (``galvo_left_amplitude`` /
``galvo_right_amplitude`` / ``galvo_left_offset`` / ``galvo_right_offset`` /
``etl_left_amplitude`` / ``etl_right_amplitude`` / ``etl_left_offset`` /
``etl_right_offset`` / ``waveform_cycles`` / ``waveform_metadata``) are
declared as plain class-level defaults so they override the abstract
``@property`` slots on ``ISigGenCore`` (Python's ABC check runs at
instantiation, before ``__init__`` sets instance attributes, so the
abstract property descriptors must be shadowed at the class level — same
fix as MockCamera in Plan 01). ``__init__`` then sets the real synthetic
values as instance attributes, which is the surface the controller reads
(D-04).

The waveform-parameter derivation mirrors the real ``SigGen.compute_scan_waveforms``
for the ``Lightsheet`` and ``Rolling`` shutter modes (the modes the
controller exercises). The derived sample counts are stored on the instance
(``_galvo_pre_samples`` etc.) so the conformance test can recompute the
expected waveforms directly from ``lightsheet.waveforms`` and assert
bit-identical arrays (D-09).
"""

import logging

import numpy as np

from lightsheet.channel_map import ChannelMap
from lightsheet.hal.interfaces import ICameraCore, ISigGen
from lightsheet.waveforms import sawtooth, squarewave, staircase

logger = logging.getLogger(__name__)


class MockSigGen(ISigGen):
    """Mock signal generator for demo mode — implements ISigGen with no DAQ.

    Constructed with a camera reference (mirroring the real ``SigGen(camera)``
    dependency — waveform timing derives from camera line time / exposure /
    shutter mode). ``compute_scan_waveforms()`` reuses the pure-numpy
    ``lightsheet.waveforms`` generators so the produced arrays are
    bit-identical to a real run (D-09). The DAQ task lifecycle verbs are
    no-ops ending with ``return None`` (AGENTS.md §10).
    """

    # Class-level defaults provide pre-__init__ synthetic values (the ABC
    # now declares these as annotations, so the override is no longer
    # required for ABC satisfaction, but the defaults are kept so the mock
    # has sensible values before __init__ runs). __init__ sets the real
    # synthetic values as instance attributes.
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

        # HAL error surface (AGENTS.md §10) — cleared on construct.
        self.error = 0
        self.error_message = ""

        # Synthetic defaults mirroring the real SigGen config.ini defaults
        # (lightsheet/hal/real/siggen.py _cfg_defaults). Hardcoded so the
        # mock constructs with no config.ini read (D-09 — deterministic).
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

        # Waveform storage — populated by compute_scan_waveforms().
        self.waveform_camera = None
        self.waveform_galvo_left = None
        self.waveform_galvo_right = None
        self.waveform_etl_left = None
        self.waveform_etl_right = None
        self.waveform_metadata = None
        self.waveform_cycles = None

        # DAQ task handles — always None under the mock (no DAQ).
        self.task_galvo_etl = None
        self.task_camera = None

        # Channel-reversal + per-channel clamp policy (RFR-04 mechanism).
        # The mock ships a default-constructed ChannelMap
        # (galvo_left_right_swap=False) so any future collaborator reading
        # self.siggen.channel_map behaves identically on --demo and on the
        # rig. The mock stays a standalone, software-only class (D-08) — no
        # config.ini read; the attribute is a plain default ChannelMap().
        self.galvo_left_right_swap = False
        self.channel_map = ChannelMap()

    # ------------------------------------------------------------------ #
    # Lifecycle verbs — no-ops ending with ``return None`` (AGENTS.md §10).
    # ------------------------------------------------------------------ #

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    def create_scanner(self) -> None:
        """No-op (no DAQ task under the mock)."""
        return None

    def start_scanner(self) -> None:
        return None

    def monitor_scanner(self) -> None:
        return None

    def stop_scanner(self) -> None:
        return None

    def delete_scanner(self) -> None:
        return None

    # ------------------------------------------------------------------ #
    # Waveform computation — reuses lightsheet.waveforms (D-09 bit-identical).
    # ------------------------------------------------------------------ #

    def compute_scan_waveforms(self) -> None:
        """Compute Galvo + ETL scan ramps and Camera Exposure waveforms.

        Mirrors the real ``SigGen.compute_scan_waveforms`` parameter
        derivation for the camera's shutter mode, then delegates to the
        pure-numpy ``lightsheet.waveforms`` generators. The produced arrays
        are bit-identical to a real run for the same parameters (D-09).
        """
        # Derive galvo_scan_time and camera timing from the camera shutter
        # mode, mirroring the real SigGen. MockCamera defaults to "Rolling".
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
            camera_delay_samples = int(
                np.ceil(camera_delay_time * self.sample_rate)
            )
        elif self.camera.shutter_mode == "Global":
            self.galvo_scan_time = self.camera.exposure_time
            camera_active_time = self.galvo_scan_time
            camera_delay_time = (
                0.5 * self.camera.ysize + 1
            ) * self.camera.line_time
            camera_delay_samples = int(np.ceil(camera_delay_time * self.sample_rate))
        else:
            raise Exception("camera shutter mode not supported")

        # Save current settings to waveform metadata (mirrors real SigGen).
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

        # Number of period cycles over the complete waveform (mirrors real).
        self.waveform_cycles = self.etl_steps

        # Galvo waveform generator inputs.
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

        # ETL waveform generator inputs.
        etl_step_samples = galvo_period_samples
        etl_steps = self.waveform_cycles
        etl_shift = (
            camera_delay_samples
            - int(np.ceil(galvo_reset_samples / 2))
            - galvo_post_samples
        )

        # Camera waveform generator inputs.
        camera_pre_samples = galvo_pre_samples
        camera_active_samples = int(np.ceil(camera_active_time * self.sample_rate))
        camera_post_samples = (
            galvo_period_samples - camera_pre_samples - camera_active_samples
        )
        camera_repeat = self.waveform_cycles

        # Store the derived counts so the conformance test can recompute the
        # expected waveforms directly from lightsheet.waveforms and assert
        # bit-identical arrays (D-09 fidelity check).
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

        # Total samples / time (mirrors real SigGen attributes the controller
        # may read).
        self.total_samples = galvo_period_samples * self.waveform_cycles
        self.total_time = self.total_samples / self.sample_rate

        # Compute camera waveform (squarewave).
        self.waveform_camera = squarewave(
            pre_samples=camera_pre_samples,
            active_samples=camera_active_samples,
            post_samples=camera_post_samples,
            shift=0,
            repeat=camera_repeat,
            inverted=False,
        )

        # Compute galvo waveforms (sawtooth).
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

        # Compute ETL waveforms (staircase).
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

    # ------------------------------------------------------------------ #
    # Extended surface (ISigGen) — setters / getters / compounded methods.
    # ------------------------------------------------------------------ #

    def update_all(
        self,
        left_galvo: float,
        right_galvo: float,
        left_etl: float,
        right_etl: float,
    ) -> None:
        """No-op (no DAQ task under the mock)."""
        return None

    def update_galvos(self, left_galvo: float, right_galvo: float) -> None:
        return None

    def update_etls(self, left_etl: float, right_etl: float) -> None:
        return None

    # ------------------------------------------------------------------ #
    # Extended config surface (ISigGen) — no-op stubs. The mock has no
    # config.ini to read or persist; the synthetic defaults are already
    # set in __init__.
    # ------------------------------------------------------------------ #

    def cfg_load_ini(self) -> None:
        return None

    def cfg_save_ini(self) -> None:
        return None
