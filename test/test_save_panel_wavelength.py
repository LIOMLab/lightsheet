"""Behavior tests for the single-channel wavelength-suffix save path
(G-09-10 gap closure).

The save panel must always pass a non-None ``wavelengths`` list to
``set_files`` — single-channel callers pass a 1-element list
``[active_laser_wavelength]``, multi-channel callers pass ``[wl1, wl2]``
as before. The active single-channel laser wavelength is read from the
live ``ILaser`` instance selected by the ``_auto_laser1`` /
``_auto_laser2`` flags cached on the shell at acquisition start.

These tests construct a real ``Controller_MainWindow`` via
``make_controller`` (real ``SavePanelWidget`` / ``FrameSaverController``
wired) and exercise the real save-panel helper + the real StackWorker
single-channel wavelength pre-sampling.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

pytest.importorskip("PySide6")


def test_active_single_channel_wavelength_laser1(qtbot, request) -> None:
    """When _auto_laser1 is True (and _auto_laser2 is False), the
    active single-channel wavelength is lasers[0].wavelength."""
    from _helpers.controller_fixture import make_controller

    ctrl, _ = make_controller(qtbot, request)
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False

    wl = ctrl.save_panel._active_single_channel_wavelength()
    assert wl == int(ctrl.lasers[0].wavelength)


def test_active_single_channel_wavelength_laser2_only(qtbot, request) -> None:
    """When only _auto_laser2 is True, the active single-channel
    wavelength is lasers[1].wavelength."""
    from _helpers.controller_fixture import make_controller

    ctrl, _ = make_controller(qtbot, request)
    ctrl._auto_laser1 = False
    ctrl._auto_laser2 = True

    wl = ctrl.save_panel._active_single_channel_wavelength()
    assert wl == int(ctrl.lasers[1].wavelength)


def test_active_single_channel_wavelength_neither_fallback(qtbot, request) -> None:
    """When neither _auto_laser1 nor _auto_laser2 is True (manual mode
    or edge case), the active wavelength falls back to lasers[0].wavelength
    — not None, not an error."""
    from _helpers.controller_fixture import make_controller

    ctrl, _ = make_controller(qtbot, request)
    ctrl._auto_laser1 = False
    ctrl._auto_laser2 = False

    wl = ctrl.save_panel._active_single_channel_wavelength()
    assert wl == int(ctrl.lasers[0].wavelength)


def test_save_panel_single_channel_passes_wavelength_suffix(
    qtbot, request, tmp_path
) -> None:
    """The single-channel save path (saveStitch radio, one auto-laser
    checked) calls set_files with wavelengths=[active_wavelength] — the
    saved filename carries the _{wavelength}nm suffix. This is the
    G-09-10 gap: the suffix must ALWAYS be present, including
    single-channel."""
    from _helpers.controller_fixture import make_controller

    ctrl, _ = make_controller(qtbot, request)
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False
    ctrl.saving_allowed = True
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "test")
    ctrl.save_filename = "test"
    ctrl.save_description = "single-channel suffix test"
    ctrl.save_format = "hdf5"
    # Position text attrs read by add_motor_parameters.
    ctrl.image_hor_pos_text = "0.0"
    ctrl.image_ver_pos_text = "0.0"
    ctrl.image_cam_pos_text = "0.0"
    # A reconstructed frame for the stitch path to enqueue.
    ctrl.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)

    # Stitch (reconstructed_frame) save mode — the default radio.
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)

    # Stub start_saving/stop_saving so the QThread does not actually
    # run — we only need to assert set_files was called with the
    # wavelength and the filename carries the suffix.
    saver = ctrl._fs.frame_saver
    saver.filenames_list = []
    saver.filenames_lists = []

    wl = int(ctrl.lasers[0].wavelength)

    with patch.object(saver, "start_saving"), patch.object(
        saver, "stop_saving"
    ):
        ctrl.save_panel.updateUi_save_single_image()

    # set_files was called with wavelengths=[wl] — filenames_lists has
    # one channel list and filenames_list mirrors it.
    assert len(saver.filenames_lists) == 1, (
        f"single-channel save must populate filenames_lists with one "
        f"channel list; got {len(saver.filenames_lists)}"
    )
    assert len(saver.filenames_list) >= 1, (
        "single-channel save must populate filenames_list"
    )
    for fn in saver.filenames_list:
        assert f"_{wl}nm" in fn, (
            f"single-channel filename must carry _{wl}nm suffix; got {fn}"
        )


def test_stack_worker_single_channel_presamples_wavelength(
    qtbot, request, tmp_path
) -> None:
    """StackWorker with multi_channel=False and _auto_laser1=True has
    self._wavelengths = [lasers[0].wavelength] (not None). The set_files
    call in run() passes wavelengths=[wl] so the saved filenames carry
    the suffix."""
    from _helpers.controller_fixture import make_controller
    from lightsheet.gui.workers import StackWorker

    ctrl, _ = make_controller(qtbot, request)
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False

    ctrl.saving_allowed = True
    ctrl.number_of_planes = 2
    ctrl.stack_mode_started = True
    ctrl.stack_starting_plane = 0.0
    ctrl.stack_step = 10.0
    ctrl.save_format = "hdf5"
    ctrl.save_directory = str(tmp_path)
    ctrl.save_filepath = str(tmp_path / "test")
    ctrl.save_description = "single-channel stack test"
    ctrl.current_horizontal_position_text = "0.0"
    ctrl.current_vertical_position_text = "0.0"
    ctrl.current_camera_position_text = "0.0"

    # Crop save path: one HDF5 file per plane.
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(True)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)

    worker = StackWorker(
        ctrl._bundle, ctrl._hw, ctrl,
        save_description="single-channel stack test",
        save_stitch_blend=False,
        save_all_crop=True,
        save_all_full=False,
        multi_channel=False,
    )

    # Single-channel worker pre-samples the active laser wavelength.
    assert worker._wavelengths is not None, (
        "StackWorker single-channel must pre-sample the active laser "
        "wavelength (not None)"
    )
    assert worker._wavelengths == [int(ctrl.lasers[0].wavelength)], (
        f"StackWorker single-channel _wavelengths must be "
        f"[lasers[0].wavelength]; got {worker._wavelengths}"
    )

    # Stub acquire_scan + motor move so the run completes without
    # touching hardware.
    def _fake_acquire_scan():
        ctrl.reconstructed_frame = np.zeros((4, 4), dtype=np.uint16)
    worker.acquire_scan = _fake_acquire_scan  # type: ignore[method-assign]
    worker.camera.recorder_timeout_status = False
    worker.siggen.error = 0

    with patch.object(
        worker.motors.horizontal, "move_absolute_position"
    ):
        finished_emits: list[None] = []
        worker.finished.connect(lambda: finished_emits.append(None))
        worker.run()

    assert len(finished_emits) == 1, (
        f"StackWorker.run must emit finished exactly once; "
        f"got {len(finished_emits)}"
    )

    fs = ctrl._fs.frame_saver
    # Single-channel set_files was called with wavelengths=[wl] —
    # filenames_lists has one channel list.
    assert len(fs.filenames_lists) == 1, (
        f"single-channel stack save must populate filenames_lists with "
        f"one channel list; got {len(fs.filenames_lists)}"
    )
    wl = int(ctrl.lasers[0].wavelength)
    for fn in fs.filenames_lists[0]:
        assert f"_{wl}nm" in fn, (
            f"single-channel stack filename must carry _{wl}nm suffix; "
            f"got {fn}"
        )
    # The HDF5 files were written to disk.
    for plane in range(2):
        fname = fs.filenames_lists[0][plane]
        assert Path(fname).exists(), (
            f"single-channel stack plane {plane} HDF5 file must exist: "
            f"{fname}"
        )


def test_stack_worker_single_channel_neither_auto_laser_fallback(
    qtbot, request
) -> None:
    """When neither _auto_laser1 nor _auto_laser2 is True, StackWorker
    single-channel pre-samples lasers[0].wavelength as the fallback
    (not None, not an error)."""
    from _helpers.controller_fixture import make_controller
    from lightsheet.gui.workers import StackWorker

    ctrl, _ = make_controller(qtbot, request)
    ctrl._auto_laser1 = False
    ctrl._auto_laser2 = False

    worker = StackWorker(
        ctrl._bundle, ctrl._hw, ctrl,
        save_description="fallback test",
        save_stitch_blend=False,
        save_all_crop=True,
        save_all_full=False,
        multi_channel=False,
    )

    assert worker._wavelengths is not None, (
        "StackWorker single-channel must pre-sample a wavelength even "
        "when neither auto-laser is checked (fallback to lasers[0])"
    )
    assert worker._wavelengths == [int(ctrl.lasers[0].wavelength)], (
        f"StackWorker fallback wavelength must be lasers[0].wavelength; "
        f"got {worker._wavelengths}"
    )
