"""Behavior tests for the ZarrSaver plain-Python collaborator
(SAV-01 / SAV-02 / D-04).

The ZarrSaver streams reconstructed frames into a pre-allocated L0
OME-Zarr array on the save worker thread (peak RAM = one frame + one
chunk), then ``finalize`` builds the 10/25/50/100 um analysis pyramid
out-of-core via Dask and writes the OME-NGFF multiscales +
omero.channels metadata. The ``/acquisition`` group (D-04) carries
per-plane motor positions + scan params as structured datasets/attrs,
read from the live HAL instances.

The test names match the per-task verification map exactly so the
VALIDATION.md automated commands resolve by node id.
"""

from __future__ import annotations

import numpy as np

from lightsheet.gui.coordinators.frame_saver_controller import ZarrSaver

from _helpers.controller_fixture import make_controller


def _save_directory(ctrl, tmp_path) -> str:
    """Point the controller's save_directory at tmp_path so the
    ZarrSaver's path-traversal guard accepts the tmp_path store."""
    import os

    ctrl.save_directory = str(tmp_path)
    return str(tmp_path)


def test_position_to_float_strips_unit_suffix() -> None:
    """The Zarr /acquisition/motor datasets need numeric values, but
    add_motor_parameters stores the shell's formatted display strings
    (e.g. "99.82 μm"). _position_to_float must coerce all the shapes the
    shell's units_fixformat produces, plus bare numerics, without raising.
    """
    from lightsheet.gui.coordinators.frame_saver_controller import (
        _position_to_float,
    )

    # Formatted display strings (the real input from add_motor_parameters).
    assert _position_to_float("99.82 μm") == 99.82
    assert _position_to_float("0.00 mm") == 0.0
    assert _position_to_float("-1.50 μm") == -1.5
    # Bare numeric string and already-numeric values pass through.
    assert _position_to_float("12.5") == 12.5
    assert _position_to_float(7) == 7.0
    assert _position_to_float(3.25) == 3.25
    # A non-numeric leading token raises (surfaced as a save error by the
    # worker's try/except — never writes a malformed store).
    import pytest

    with pytest.raises(ValueError):
        _position_to_float("not a number")


def test_zarr_saver_streams_and_finalizes(qtbot, request, tmp_path) -> None:
    """SAV-01: N planes stream into the L0 dataset and finalize builds
    the pyramid. Read back via ``zarr.open`` and assert the L0 shape
    matches (1, N, ysize, xsize) and an ``acquisition`` group exists."""
    import zarr

    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0

    store_path = str(tmp_path / "stack.ome.zarr")
    saver = ZarrSaver(ctrl)
    n_planes = 4
    saver.start_stack(store_path, n_planes)
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    for z in range(n_planes):
        saver.write_plane(0, z, frame, 0.0, 0.0, 0.0)
    saver.finalize()

    root = zarr.open(store_path, mode="r")
    assert "0" in root  # L0 dataset / group
    assert "acquisition" in root  # D-04 acquisition group
    assert root["0"].shape == (1, n_planes, ctrl.camera.ysize, ctrl.camera.xsize)


def test_omero_channels(qtbot, request, tmp_path) -> None:
    """SAV-02: the omero channels carry wavelength / color / label /
    active per laser that was actually used in the acquisition. Only
    lasers whose auto-laser flag was set at acquisition start are
    included — not all configured lasers. The color is a 6-char hex
    string with no ``#`` prefix."""
    import zarr

    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0

    # Only laser 2 (647 nm) was active for this acquisition.
    ctrl._auto_laser1 = False
    ctrl._auto_laser2 = True

    store_path = str(tmp_path / "stack.ome.zarr")
    saver = ZarrSaver(ctrl)
    saver.start_stack(store_path, 1)
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    saver.write_plane(0, 0, frame, 0.0, 0.0, 0.0)
    saver.finalize()

    root = zarr.open(store_path, mode="r")
    ome = root.attrs["ome"]
    channels = ome["omero"]["channels"]
    # Only the active laser (647 nm) should be in the channels list.
    assert len(channels) == 1, (
        f"expected 1 channel (only laser 2 was active), got {len(channels)}"
    )
    ch = channels[0]
    assert ch["wavelength"] == 647
    assert isinstance(ch["color"], str)
    assert len(ch["color"]) == 6
    assert "#" not in ch["color"]
    assert ch["label"] == ctrl.lasers[1].label
    assert ch["active"] is True


def test_omero_from_live_lasers(qtbot, request, tmp_path) -> None:
    """SAV-02: the omero channel metadata is built from the live
    ``list[ILaser]`` the controller holds, not from a config re-parse.
    A laser whose ``label`` was mutated at runtime is reflected in the
    saved channels. The channel filter uses the cached auto-laser flags
    (``_auto_laser1`` / ``_auto_laser2``) sampled at acquisition start,
    not the live ``laser.active`` state (which is False by finalize
    time because ``stop_lasers()`` runs before finalize)."""
    import zarr

    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0

    # Laser 1 was active for this acquisition.
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False

    # Mutate live laser label after constructing the ZarrSaver but
    # before finalize — the saved metadata must reflect the live value.
    original_label = ctrl.lasers[0].label
    try:
        ctrl.lasers[0].label = "Mutated (555 nm)"
        store_path = str(tmp_path / "stack.ome.zarr")
        saver = ZarrSaver(ctrl)
        saver.start_stack(store_path, 1)
        frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
        saver.write_plane(0, 0, frame, 0.0, 0.0, 0.0)
        saver.finalize()

        root = zarr.open(store_path, mode="r")
        channels = root.attrs["ome"]["omero"]["channels"]
        assert len(channels) == 1, (
            f"expected 1 channel (only laser 1 was active), got {len(channels)}"
        )
        assert channels[0]["label"] == "Mutated (555 nm)"
        assert channels[0]["active"] is True
    finally:
        ctrl.lasers[0].label = original_label


def test_ngff_metadata(qtbot, request, tmp_path) -> None:
    """SAV-02: NGFF v0.5 metadata is written — ``ome.version`` and the
    ``multiscales`` structure with at least one dataset pointing at L0."""
    import zarr

    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0

    store_path = str(tmp_path / "stack.ome.zarr")
    saver = ZarrSaver(ctrl)
    saver.start_stack(store_path, 1)
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    saver.write_plane(0, 0, frame, 0.0, 0.0, 0.0)
    saver.finalize()

    root = zarr.open(store_path, mode="r")
    ome = root.attrs["ome"]
    assert ome["version"] == "0.5"
    multiscales = ome["multiscales"]
    assert len(multiscales) >= 1
    datasets = multiscales[0]["datasets"]
    assert len(datasets) >= 1
    assert datasets[0]["path"] == "0"


def test_acquisition_group(qtbot, request, tmp_path) -> None:
    """D-04: the ``/acquisition`` group records the motor 1D datasets
    (horizontal/vertical/camera positions, length n_planes) and the
    scan-parameter group attrs (galvo/ETL amplitudes+offsets, exposure,
    sample_rate, shutter_mode) matching the live controller."""
    import zarr

    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0

    store_path = str(tmp_path / "stack.ome.zarr")
    saver = ZarrSaver(ctrl)
    n_planes = 3
    saver.start_stack(store_path, n_planes)
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    for z in range(n_planes):
        saver.write_plane(0, z, frame, float(z), float(z) * 2.0, float(z) * 3.0)
    saver.finalize()

    root = zarr.open(store_path, mode="r")
    acq = root["acquisition"]
    motor = acq["motor"]
    assert motor["horizontal"].shape == (n_planes,)
    assert motor["vertical"].shape == (n_planes,)
    assert motor["camera"].shape == (n_planes,)
    # Scan-parameter group attrs read from the live HAL instances.
    assert acq.attrs["galvo_left_amplitude"] == ctrl.siggen.galvo_left_amplitude
    assert acq.attrs["etl_left_amplitude"] == ctrl.siggen.etl_left_amplitude
    assert acq.attrs["exposure_time_s"] == ctrl.camera.exposure_time
    assert acq.attrs["shutter_mode"] == ctrl.camera.shutter_mode
    assert acq.attrs["sample_rate"] == ctrl.siggen.sample_rate


# --- Task 2 tests (format branch + close ordering) ---------------------
# These two are made GREEN in Task 2 alongside the FrameSaverWorker
# format branch. They are kept here so all 7 ZarrSaver tests live in one
# file (VALIDATION.md resolves them by node id).


def test_format_branch(qtbot, request, tmp_path) -> None:
    """SAV-01: the ``save_format`` branch selects the Zarr saver path.
    When ``save_format == 'zarr'`` the worker calls ``zarr_save_worker``
    (not ``frame_saver_worker``); ``'hdf5'`` -> ``frame_saver_worker``;
    ``'both'`` -> ``zarr_save_worker`` then ``frame_saver_worker``
    (serialized). The try/finally + ``sig_finished.emit()`` shape is
    preserved verbatim (single emit, not duplicated)."""
    from unittest.mock import MagicMock

    from lightsheet.gui.coordinators.frame_saver_controller import FrameSaverWorker

    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    saver = ctrl._fs.frame_saver

    # Replace the loop bodies with spies so we can observe which branch
    # ran without touching the disk or starting a real QThread.
    saver.frame_saver_worker = MagicMock()
    saver.zarr_save_worker = MagicMock()
    saver.both_save_worker = MagicMock()

    def _run(fmt: str) -> list[str]:
        ctrl.save_format = fmt
        worker = FrameSaverWorker(saver)
        finished: list[int] = []
        worker.sig_finished.connect(lambda: finished.append(1))
        # Call the slot directly (on the calling thread) — no QThread.
        worker.start_saving()
        return finished

    # zarr -> zarr_save_worker only.
    saver.zarr_save_worker.reset_mock()
    saver.frame_saver_worker.reset_mock()
    saver.both_save_worker.reset_mock()
    finished = _run("zarr")
    assert saver.zarr_save_worker.call_count == 1
    assert saver.frame_saver_worker.call_count == 0
    assert saver.both_save_worker.call_count == 0
    assert len(finished) == 1  # sig_finished emitted exactly once

    # hdf5 -> frame_saver_worker only.
    saver.zarr_save_worker.reset_mock()
    saver.frame_saver_worker.reset_mock()
    saver.both_save_worker.reset_mock()
    finished = _run("hdf5")
    assert saver.frame_saver_worker.call_count == 1
    assert saver.zarr_save_worker.call_count == 0
    assert saver.both_save_worker.call_count == 0
    assert len(finished) == 1

    # both -> both_save_worker (single dual-write loop, not two separate
    # calls). The previous two-call design drained the shared queue twice
    # and produced empty HDF5 files; both_save_worker fixes this.
    saver.zarr_save_worker.reset_mock()
    saver.frame_saver_worker.reset_mock()
    saver.both_save_worker.reset_mock()
    finished = _run("both")
    assert saver.both_save_worker.call_count == 1
    assert saver.zarr_save_worker.call_count == 0
    assert saver.frame_saver_worker.call_count == 0
    assert len(finished) == 1  # single sig_finished, not duplicated

    # unknown -> defaults to frame_saver_worker.
    saver.zarr_save_worker.reset_mock()
    saver.frame_saver_worker.reset_mock()
    finished = _run("tiff")
    assert saver.frame_saver_worker.call_count == 1
    assert saver.zarr_save_worker.call_count == 0
    assert len(finished) == 1


def test_close_ordering(qtbot, request, tmp_path) -> None:
    """SAV-01: ``sig_finished`` fires only AFTER finalize completes
    (close ordering). The try/finally + ``sig_finished.emit()`` shape
    in ``FrameSaverWorker.start_saving`` is the load-bearing contract —
    a Zarr finalize that takes a measurable time completes BEFORE
    ``sig_finished`` emits."""
    from lightsheet.gui.coordinators.frame_saver_controller import FrameSaverWorker

    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0
    ctrl.save_format = "zarr"
    saver = ctrl._fs.frame_saver

    # Drive a real Zarr save through the worker slot (called directly
    # on the calling thread — no QThread). The finalize builds a real
    # (tiny) pyramid so the close-ordering is exercised end-to-end.
    n_planes = 2
    saver.set_files(
        number_of_files=n_planes,
        files_name="stack",
        scan_type="z",
        number_of_datasets=1,
        datasets_name="ch",
        wavelengths=[555],
    )
    saver.horizontal_positions_list = [0.0, 1.0]
    saver.vertical_positions_list = [0.0, 2.0]
    saver.camera_positions_list = [0.0, 3.0]
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    # Pre-load the queue so zarr_save_worker drains without waiting.
    saver.queue.put(frame)
    saver.queue.put(frame)
    # The production FrameSaver.start_saving() sets saving_started=True
    # then starts the QThread; here we call the worker slot directly
    # (no QThread), so set the flag manually to mirror the production
    # entry condition.
    saver.saving_started = True

    worker = FrameSaverWorker(saver)
    finished: list[int] = []
    worker.sig_finished.connect(lambda: finished.append(1))
    # The ZarrSaver is constructed in FrameSaver.__init__; finalize runs
    # inside the worker's try block, so sig_finished (in the finally)
    # fires AFTER finalize returns.
    worker.start_saving()
    assert len(finished) == 1
    # The store was finalized (acquisition group present).
    import zarr

    root = zarr.open(str(tmp_path / "stack.ome.zarr"), mode="r")
    assert "acquisition" in root
    assert root["0"].shape == (1, n_planes, ctrl.camera.ysize, ctrl.camera.xsize)


def test_zarr_save_finalizes_after_stop_saving_on_normal_completion(
    qtbot, request, tmp_path
) -> None:
    """Regression: on normal stack completion ``stop_saving()`` flips
    ``saving_started=False`` (it is the winding-down path for BOTH abort
    and success). The zarr_save_worker must STILL finalize when all planes
    were written (``z_idx >= n_planes``), because the multiscales + omero
    metadata + /acquisition group are written at finalize — without them
    napari-ome-zarr opens the store and returns no data.

    The previous gate ``if not self.saving_started: skip finalize`` fired
    on normal completion too, leaving a partial store (L0 data only, empty
    root attrs, no pyramid, no /acquisition group). This test simulates the
    real completion sequence: the queue is pre-loaded with all frames, and
    a queue wrapper flips ``saving_started=False`` once the last frame is
    consumed (mimicking the acquisition coordinator calling stop_saving()
    after enqueuing the final plane)."""
    import zarr

    from lightsheet.gui.coordinators.frame_saver_controller import (
        FrameSaverWorker,
    )

    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0
    ctrl.save_format = "zarr"
    # Shrink the camera frame so the Dask pyramid build in finalize is
    # fast (2048x2048 x 5 planes takes minutes; 32x32 takes milliseconds).
    ctrl.camera.xsize = 32
    ctrl.camera.ysize = 32
    saver = ctrl._fs.frame_saver

    n_planes = 2
    saver.set_files(
        number_of_files=n_planes,
        files_name="stack",
        scan_type="z",
        number_of_datasets=1,
        datasets_name="ch",
        wavelengths=[555],
    )
    # Use the shell's formatted display strings (the real input shape —
    # add_motor_parameters stores units_fixformat output like "99.82 μm").
    # The Zarr worker must coerce these to floats for the numeric
    # /acquisition/motor datasets; a bare float() would raise ValueError
    # on the unit suffix and abort the save mid-stream.
    saver.horizontal_positions_list = ["0.00 μm", "1.00 μm"]
    saver.vertical_positions_list = ["0.00 μm", "2.00 μm"]
    saver.camera_positions_list = ["0.00 μm", "3.00 μm"]
    frame = np.zeros(
        (ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16
    )

    # Queue wrapper that flips saving_started=False once the last frame is
    # consumed — mimicking stop_saving() on normal completion.
    class _StopAfterLastQueue:
        def __init__(self, real, n_frames: int) -> None:
            self._real = real
            self._remaining = n_frames

        def get(self, block=True, timeout=None):
            buf = self._real.get(block=block, timeout=timeout)
            self._remaining -= 1
            if self._remaining <= 0:
                saver.saving_started = False
            return buf

        def __getattr__(self, name):
            return getattr(self._real, name)

    saver.queue = _StopAfterLastQueue(saver.queue, n_planes)
    for _ in range(n_planes):
        saver.queue.put(frame)
    saver.saving_started = True

    worker = FrameSaverWorker(saver)
    finished: list[int] = []
    worker.sig_finished.connect(lambda: finished.append(1))
    worker.start_saving()
    assert len(finished) == 1

    # The store MUST be finalized despite saving_started=False at the
    # completion gate — root attrs carry the ome metadata and the
    # /acquisition group is present.
    root = zarr.open(str(tmp_path / "stack.ome.zarr"), mode="r")
    assert "acquisition" in root, (
        "finalize was skipped on normal completion — /acquisition group "
        "missing (the napari-ome-zarr 'returned no data' regression)"
    )
    assert "ome" in root.attrs, (
        "multiscales/omero metadata missing — napari-ome-zarr cannot read "
        "the store without the ome root attrs"
    )


def test_zarr_drains_queue_after_stop_saving(qtbot, request, tmp_path) -> None:
    """Regression: all frames queued, then stop_saving() flips
    saving_started=False BEFORE the worker drains the queue.

    This is the demo-mode / fast-rig scenario: the acquisition queues all
    frames near-instantly, then stop_saving() fires. The old worker loop
    (`while self.saving_started and z_idx < n_planes`) exited on the flag
    flip after consuming only 1 frame, leaving the rest in the queue and
    producing a 1-plane store with no finalize. The fix drains remaining
    frames via get_nowait() on queue.Empty when saving_started is False.
    """
    from lightsheet.gui.coordinators.frame_saver_controller import (
        FrameSaverWorker,
    )

    import zarr

    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0
    ctrl.save_format = "zarr"
    # Shrink the camera frame so the Dask pyramid build in finalize is
    # fast (2048x2048 x 5 planes takes minutes; 32x32 takes milliseconds).
    ctrl.camera.xsize = 32
    ctrl.camera.ysize = 32
    saver = ctrl._fs.frame_saver
    # Reinit with a larger block_size so the queue (maxsize = 2 * block_size)
    # can hold all n_planes frames at once for the pre-load below.
    saver.reinit(8)

    n_planes = 5
    saver.set_files(
        number_of_files=n_planes,
        files_name="drain_test",
        scan_type="z",
        number_of_datasets=1,
        datasets_name="ch",
        wavelengths=[555],
    )
    saver.horizontal_positions_list = [f"{i}.00 μm" for i in range(n_planes)]
    saver.vertical_positions_list = [f"{i}.00 μm" for i in range(n_planes)]
    saver.camera_positions_list = [f"{i}.00 μm" for i in range(n_planes)]
    frame = np.zeros(
        (ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16
    )

    # Pre-queue ALL frames BEFORE starting the worker — mimicking the
    # demo-mode scenario where the acquisition completes instantly.
    for _ in range(n_planes):
        saver.queue.put(frame)

    # Flip saving_started=False BEFORE the worker starts, simulating
    # stop_saving() being called by the acquisition worker right after
    # queueing the last frame. The worker must still drain all 5 frames
    # and finalize the store.
    saver.saving_started = True

    # Use a wrapper that flips the flag after the first get, so the worker
    # sees saving_started=False while frames are still in the queue.
    class _FlipAfterFirstGet:
        def __init__(self, real) -> None:
            self._real = real
            self._count = 0

        def get(self, block=True, timeout=None):
            buf = self._real.get(block=block, timeout=timeout)
            self._count += 1
            if self._count >= 1:
                saver.saving_started = False
            return buf

        def get_nowait(self):
            return self._real.get_nowait()

        def __getattr__(self, name):
            return getattr(self._real, name)

    saver.queue = _FlipAfterFirstGet(saver.queue)

    worker = FrameSaverWorker(saver)
    finished: list[int] = []
    worker.sig_finished.connect(lambda: finished.append(1))
    worker.start_saving()
    assert len(finished) == 1

    # ALL 5 planes must be written + the store finalized despite
    # saving_started being flipped after the first frame.
    root = zarr.open(str(tmp_path / "drain_test.ome.zarr"), mode="r")
    assert "acquisition" in root, (
        "finalize was skipped — /acquisition group missing "
        "(the worker exited before draining the queue)"
    )
    assert "ome" in root.attrs, (
        "multiscales/omero metadata missing — napari-ome-zarr cannot read "
        "the store without the ome root attrs"
    )
    # L0 should have all 5 planes.
    arr = root["0"]
    assert arr.shape[1] == n_planes, (
        f"L0 has {arr.shape[1]} planes but expected {n_planes} — "
        f"the worker did not drain the queue after stop_saving()"
    )


def test_both_mode_writes_both_formats(qtbot, request, tmp_path) -> None:
    """CR-01 regression: ``both`` save mode must write image data to BOTH
    the OME-Zarr store AND the HDF5 files from a single queue-consume
    pass. The previous two-loop design (zarr_save_worker then
    frame_saver_worker) drained the shared single-consumer queue twice —
    the Zarr loop consumed every frame, leaving the HDF5 loop with an
    empty queue so it produced metadata-only HDF5 files (no image
    datasets). This test exercises the real shared queue end-to-end
    (no MagicMock spies on the worker methods) and asserts both formats
    carry the image data.
    """
    import h5py
    import zarr

    from lightsheet.gui.coordinators.frame_saver_controller import FrameSaverWorker

    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0
    ctrl.save_format = "both"
    # Shrink the camera frame so the Dask pyramid build in finalize is
    # fast (2048x2048 takes minutes; 32x32 takes milliseconds).
    ctrl.camera.xsize = 32
    ctrl.camera.ysize = 32
    saver = ctrl._fs.frame_saver
    # Reinit with a larger block_size so the queue (maxsize = 2 * block_size)
    # can hold all n_planes frames at once for the pre-load below.
    saver.reinit(8)

    n_planes = 3
    # files_name must include the save directory prefix (production code
    # joins save_directory + filename before calling set_files, so the
    # filenames_list entries are full paths).
    files_name = str(tmp_path / "stack")
    saver.set_files(
        number_of_files=n_planes,
        files_name=files_name,
        scan_type="z",
        number_of_datasets=1,
        datasets_name="ch",
        wavelengths=[555],
    )
    saver.horizontal_positions_list = [0.0, 1.0, 2.0]
    saver.vertical_positions_list = [0.0, 2.0, 4.0]
    saver.camera_positions_list = [0.0, 3.0, 6.0]
    # Distinct non-zero pixel values per plane so we can verify the data
    # actually landed in both formats (not just metadata headers).
    frames = []
    for z in range(n_planes):
        frame = np.full(
            (ctrl.camera.ysize, ctrl.camera.xsize), (z + 1) * 100, dtype=np.uint16
        )
        frames.append(frame)
        saver.queue.put(frame)
    saver.saving_started = True

    worker = FrameSaverWorker(saver)
    finished: list[int] = []
    worker.sig_finished.connect(lambda: finished.append(1))
    worker.start_saving()

    # sig_finished emitted exactly once (close-ordering contract).
    assert len(finished) == 1

    # --- Zarr store has the full image data + acquisition group ---
    root = zarr.open(str(tmp_path / "stack.ome.zarr"), mode="r")
    assert "acquisition" in root
    assert root["0"].shape == (1, n_planes, ctrl.camera.ysize, ctrl.camera.xsize)
    arr = root["0"]
    for z in range(n_planes):
        # The single-channel axis is 0; plane z is axis 1.
        assert np.all(arr[0, z, :, :] == (z + 1) * 100)

    # --- HDF5 files have image datasets (NOT metadata-only) ---
    # set_files builds the per-channel filenames_list; read the actual
    # paths from there instead of reconstructing the old
    # _plane_NNNNN convention (the naming is now compact: no suffix on
    # the first file, then _01, _02, ...).
    assert len(saver.filenames_list) == n_planes
    for z in range(n_planes):
        h5_path = saver.filenames_list[z]
        with h5py.File(h5_path, "r") as f:
            keys = list(f.keys())
            # The dataset name pattern is datasets_name + counter (1-based).
            assert len(keys) == 1, f"HDF5 file {h5_path} has {len(keys)} datasets, expected 1"
            ds = f[keys[0]]
            assert ds.shape == (ctrl.camera.ysize, ctrl.camera.xsize)
            assert np.all(ds[()] == (z + 1) * 100), (
                f"HDF5 plane {z} data mismatch: got max {ds[()].max()}, "
                f"expected {(z + 1) * 100}"
            )


# ---------------------------------------------------------------------------
# write_empty_chunks — all-zero frames must produce data chunks on disk
# (G-09-11 gap closure). zarr v3 defaults write_empty_chunks=False, which
# silently skips all-zero chunks — MockCamera demo frames and dark real-rig
# frames produce a metadata-only store with zero data chunk files. The
# ZarrSaver.start_stack fix forwards config={'write_empty_chunks': True} to
# the L0 array creation so all-zero chunks are persisted.
# ---------------------------------------------------------------------------


def _count_chunk_files(store_path: str) -> int:
    """Walk the zarr store tree and count files under the ``0/c/``
    directory (the L0 chunk files). A metadata-only store has zero
    chunk files (only ``zarr.json`` files); a store with data has
    chunk files like ``0/c/0/0/0/0``."""
    import os

    chunk_files = 0
    for root, _dirs, files in os.walk(store_path):
        rel = os.path.relpath(root, store_path)
        # Count files in any directory under 0/c/ (chunk storage).
        if rel.startswith("0/c/") or rel == "0/c":
            chunk_files += len(files)
    return chunk_files


def test_zarr_all_zero_frames_produce_chunks(qtbot, request, tmp_path) -> None:
    """G-09-11: a Zarr store written with all-zero uint16 frames (the
    MockCamera demo case) must contain actual data chunk files under
    ``0/c/`` — not just ``zarr.json`` metadata. zarr v3 defaults
    ``write_empty_chunks=False`` which silently skips all-zero chunks;
    ZarrSaver.start_stack forwards ``config={'write_empty_chunks': True}``
    to the L0 array creation so all-zero chunks are persisted."""
    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0
    # Shrink the camera frame so the Dask pyramid build in finalize is
    # fast (2048x2048 takes minutes; 32x32 takes milliseconds).
    ctrl.camera.xsize = 32
    ctrl.camera.ysize = 32

    store_path = str(tmp_path / "stack.ome.zarr")
    saver = ZarrSaver(ctrl)
    n_planes = 2
    saver.start_stack(store_path, n_planes)
    # All-zero frames — the MockCamera demo case.
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    for z in range(n_planes):
        saver.write_plane(0, z, frame, 0.0, 0.0, 0.0)
    saver.finalize()

    # The store must contain actual data chunk files under 0/c/, not
    # just zarr.json metadata.
    chunk_count = _count_chunk_files(store_path)
    assert chunk_count >= 1, (
        f"all-zero frames must produce at least one chunk file under "
        f"0/c/; got {chunk_count} (metadata-only store — "
        f"write_empty_chunks not forwarded)"
    )


def test_zarr_multi_channel_all_zero_produce_chunks(
    qtbot, request, tmp_path
) -> None:
    """G-09-11 multi-channel: a 2-channel Zarr store with all-zero
    frames must have chunk files for both channels (``c/0/`` and
    ``c/1/`` directories contain chunk files)."""
    import os

    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0
    ctrl.camera.xsize = 32
    ctrl.camera.ysize = 32
    # Both auto-laser flags set so the omero channels match n_channels=2
    # (finalize asserts omero_channels length == n_channels for >1 ch).
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = True

    store_path = str(tmp_path / "stack.ome.zarr")
    saver = ZarrSaver(ctrl)
    n_planes = 2
    n_channels = 2
    saver.start_stack(store_path, n_planes, n_channels=n_channels)
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    for ch in range(n_channels):
        for z in range(n_planes):
            saver.write_plane(ch, z, frame, float(z), float(z), float(z))
    saver.finalize()

    # Both channels must have chunk files.
    for ch in range(n_channels):
        ch_dir = os.path.join(store_path, "0", "c", str(ch))
        ch_chunks = 0
        if os.path.isdir(ch_dir):
            for _root, _dirs, files in os.walk(ch_dir):
                ch_chunks += len(files)
        assert ch_chunks >= 1, (
            f"channel {ch}: all-zero frames must produce at least one "
            f"chunk file under 0/c/{ch}/; got {ch_chunks}"
        )


def test_zarr_non_zero_frames_still_produce_chunks(
    qtbot, request, tmp_path
) -> None:
    """Regression: non-zero frames must still produce chunk files (the
    write_empty_chunks=True fix must not break the non-zero path)."""
    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0
    ctrl.camera.xsize = 32
    ctrl.camera.ysize = 32

    store_path = str(tmp_path / "stack.ome.zarr")
    saver = ZarrSaver(ctrl)
    n_planes = 2
    saver.start_stack(store_path, n_planes)
    # Non-zero frames with distinct values per plane.
    for z in range(n_planes):
        frame = np.full(
            (ctrl.camera.ysize, ctrl.camera.xsize),
            (z + 1) * 100,
            dtype=np.uint16,
        )
        saver.write_plane(0, z, frame, float(z), float(z), float(z))
    saver.finalize()

    chunk_count = _count_chunk_files(store_path)
    assert chunk_count >= 1, (
        f"non-zero frames must produce chunk files; got {chunk_count}"
    )

    # Verify the data round-trips correctly.
    import zarr

    root = zarr.open(store_path, mode="r")
    arr = root["0"]
    for z in range(n_planes):
        assert np.all(arr[0, z, :, :] == (z + 1) * 100), (
            f"plane {z} data mismatch after round-trip"
        )
