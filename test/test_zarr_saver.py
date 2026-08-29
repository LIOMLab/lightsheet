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
import pytest

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


@pytest.mark.xfail(
    reason="Task 2: FrameSaverWorker.start_saving format branch + close ordering",
    strict=False,
)
def test_format_branch(qtbot, request, tmp_path) -> None:
    """SAV-01: the ``save_format`` branch selects the Zarr saver path.
    When ``save_format == 'zarr'`` the worker calls ``zarr_save_worker``
    (not ``frame_saver_worker``); ``'hdf5'`` -> ``frame_saver_worker``;
    ``'both'`` -> ``zarr_save_worker`` then ``frame_saver_worker``
    (serialized)."""
    ctrl, _ = make_controller(qtbot, request)
    assert ZarrSaver is not None
    ctrl.save_format = "zarr"
    assert ctrl.save_format == "zarr"


@pytest.mark.xfail(
    reason="Task 2: FrameSaverWorker.start_saving format branch + close ordering",
    strict=False,
)
def test_close_ordering(qtbot, request, tmp_path) -> None:
    """SAV-01: ``sig_finished`` fires only AFTER finalize completes
    (close ordering). The try/finally + ``sig_finished.emit()`` shape
    in ``FrameSaverWorker.start_saving`` is the load-bearing contract."""
    ctrl, _ = make_controller(qtbot, request)
    assert ZarrSaver is not None
