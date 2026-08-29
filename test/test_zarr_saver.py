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
        saver.write_plane(z, frame, 0.0, 0.0, 0.0)
    saver.finalize()

    root = zarr.open(store_path, mode="r")
    assert "0" in root  # L0 dataset / group
    assert "acquisition" in root  # D-04 acquisition group
    assert root["0"].shape == (1, n_planes, ctrl.camera.ysize, ctrl.camera.xsize)


def test_omero_channels(qtbot, request, tmp_path) -> None:
    """SAV-02: the omero channels carry wavelength / color / label /
    active per configured laser. The color is a 6-char hex string with
    no ``#`` prefix."""
    import zarr

    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0

    store_path = str(tmp_path / "stack.ome.zarr")
    saver = ZarrSaver(ctrl)
    saver.start_stack(store_path, 1)
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    saver.write_plane(0, frame, 0.0, 0.0, 0.0)
    saver.finalize()

    root = zarr.open(store_path, mode="r")
    ome = root.attrs["ome"]
    channels = ome["omero"]["channels"]
    assert len(channels) == len(ctrl.lasers)
    for ch, laser in zip(channels, ctrl.lasers):
        assert ch["wavelength"] == laser.wavelength
        assert isinstance(ch["color"], str)
        assert len(ch["color"]) == 6
        assert "#" not in ch["color"]
        assert ch["label"] == laser.label
        assert ch["active"] == bool(laser.active)


def test_omero_from_live_lasers(qtbot, request, tmp_path) -> None:
    """SAV-02: the omero channel metadata is built from the live
    ``list[ILaser]`` the controller holds, not from a config re-parse.
    A laser whose ``active`` flag was mutated at runtime is reflected
    in the saved channels."""
    import zarr

    ctrl, _ = make_controller(qtbot, request)
    _save_directory(ctrl, tmp_path)
    ctrl.stack_step = 1.0

    # Mutate live laser state after constructing the ZarrSaver but
    # before finalize — the saved metadata must reflect the live value.
    original_active = ctrl.lasers[0].active
    original_label = ctrl.lasers[0].label
    try:
        ctrl.lasers[0].active = not original_active
        ctrl.lasers[0].label = "Mutated (555 nm)"
        store_path = str(tmp_path / "stack.ome.zarr")
        saver = ZarrSaver(ctrl)
        saver.start_stack(store_path, 1)
        frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
        saver.write_plane(0, frame, 0.0, 0.0, 0.0)
        saver.finalize()

        root = zarr.open(store_path, mode="r")
        channels = root.attrs["ome"]["omero"]["channels"]
        assert channels[0]["label"] == "Mutated (555 nm)"
        assert channels[0]["active"] == (not original_active)
    finally:
        ctrl.lasers[0].active = original_active
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
    saver.write_plane(0, frame, 0.0, 0.0, 0.0)
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
        saver.write_plane(z, frame, float(z), float(z) * 2.0, float(z) * 3.0)
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
    # set_files creates one .hdf5 file per plane (full path = files_name
    # + _z_plane_NNNNN.hdf5).
    for z in range(n_planes):
        h5_path = str(tmp_path / f"stack_z_plane_{z + 1:05d}.hdf5")
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
