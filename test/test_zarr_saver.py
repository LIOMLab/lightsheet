"""Wave 0 RED scaffolds for the ZarrSaver (SAV-01 / SAV-02 / D-04).

These tests define the expected behavior of the native OME-Zarr streaming
saver that lands in a later wave. They are marked ``xfail`` (strict=False)
during Wave 0 so the suite stays GREEN: the production ``ZarrSaver`` class
does not exist yet, so each test fails at construction/import and xfail
records the expected failure. When the implementation lands, the xfail
markers are removed and the tests turn into the real GREEN gate.

The test names match the per-task verification map exactly so the
VALIDATION.md automated commands resolve by node id.

Behavior covered (per the plan's <behavior> block):
- SAV-01: N planes stream into L0 + a pyramid is built on finalize; the
  ``save_format`` branch selects the Zarr path; ``sig_finished`` fires
  only after finalize completes (close ordering).
- SAV-02: omero channels carry wavelength/color/label/active; the channel
  metadata is built from the live ``list[ILaser]``; NGFF v0.5 ome.version
  + multiscales metadata is written.
- D-04: an ``/acquisition`` group records the motor 1D datasets and the
  scan-parameter root attrs.
"""

from __future__ import annotations

import numpy as np
import pytest

# Module-level import guard: ZarrSaver does not exist yet (Wave 0). The
# xfail markers below absorb the resulting AssertionError/TypeError; we do
# NOT pytest.skip() so the test is collected and reported as xfail (the
# Nyquist "every test file exists" contract), not silently skipped.
try:  # pragma: no cover - import guard for not-yet-implemented class
    from lightsheet.gui.coordinators.frame_saver_controller import ZarrSaver
except ImportError:  # pragma: no cover - Wave 0
    ZarrSaver = None  # type: ignore[assignment,misc]

from _helpers.controller_fixture import make_controller

_WAVE0 = "Wave 0 RED scaffold — ZarrSaver implemented in a later wave"


@pytest.mark.xfail(reason=_WAVE0, strict=False)
def test_zarr_saver_streams_and_finalizes(qtbot, request, tmp_path) -> None:
    """SAV-01: N planes stream into the L0 dataset and finalize builds the
    pyramid. Read back via ``zarr.open`` and assert the L0 shape matches
    N planes and an ``acquisition`` group exists."""
    import zarr

    ctrl, _ = make_controller(qtbot, request)
    assert ZarrSaver is not None, "ZarrSaver not yet implemented"

    store_path = tmp_path / "stack.ome.zarr"
    saver = ZarrSaver(ctrl, store_path=str(store_path))
    saver.start_stack()
    n_planes = 4
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    for _ in range(n_planes):
        saver.write_frame(frame)
    saver.finalize()

    root = zarr.open(str(store_path), mode="r")
    assert "0" in root  # L0 dataset / group
    assert "acquisition" in root  # D-04 acquisition group
    l0 = root["0"]
    assert l0.shape[0] == n_planes


@pytest.mark.xfail(reason=_WAVE0, strict=False)
def test_format_branch(qtbot, request, tmp_path) -> None:
    """SAV-01: the ``save_format`` branch selects the Zarr saver path. When
    ``save_format == 'zarr'`` the saver writes an OME-Zarr store; the HDF5
    path is not taken."""
    ctrl, _ = make_controller(qtbot, request)
    assert ZarrSaver is not None, "ZarrSaver not yet implemented"
    # The controller's save_format drives the branch; 'zarr' selects ZarrSaver.
    ctrl.save_format = "zarr"
    store_path = tmp_path / "stack.ome.zarr"
    saver = ZarrSaver(ctrl, store_path=str(store_path))
    saver.start_stack()
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    saver.write_frame(frame)
    saver.finalize()
    assert store_path.exists()


@pytest.mark.xfail(reason=_WAVE0, strict=False)
def test_close_ordering(qtbot, request, tmp_path) -> None:
    """SAV-01: ``sig_finished`` fires only AFTER finalize completes (close
    ordering). A finalized saver emits the finished signal exactly once."""
    ctrl, _ = make_controller(qtbot, request)
    assert ZarrSaver is not None, "ZarrSaver not yet implemented"
    store_path = tmp_path / "stack.ome.zarr"
    saver = ZarrSaver(ctrl, store_path=str(store_path))
    saver.start_stack()
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    saver.write_frame(frame)
    finished_emissions: list[int] = []
    saver.sig_finished.connect(lambda: finished_emissions.append(1))
    saver.finalize()
    assert len(finished_emissions) == 1


@pytest.mark.xfail(reason=_WAVE0, strict=False)
def test_omero_channels(qtbot, request, tmp_path) -> None:
    """SAV-02: the omero channels carry wavelength / color / label / active
    per configured laser."""
    import zarr

    ctrl, _ = make_controller(qtbot, request)
    assert ZarrSaver is not None, "ZarrSaver not yet implemented"
    store_path = tmp_path / "stack.ome.zarr"
    saver = ZarrSaver(ctrl, store_path=str(store_path))
    saver.start_stack()
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    saver.write_frame(frame)
    saver.finalize()

    root = zarr.open(str(store_path), mode="r")
    omero = root.attrs["omero"]
    channels = omero["channels"]
    assert len(channels) == len(ctrl.lasers)
    for ch, laser in zip(channels, ctrl.lasers):
        assert ch["wavelength"] == laser.wavelength
        assert "color" in ch
        assert ch["label"] == laser.label
        assert ch["active"] == laser.active


@pytest.mark.xfail(reason=_WAVE0, strict=False)
def test_omero_from_live_lasers(qtbot, request, tmp_path) -> None:
    """SAV-02: the omero channel metadata is built from the live
    ``list[ILaser]`` the controller holds, not from a config re-parse. A
    laser whose wavelength/label was mutated at runtime is reflected in
    the saved channels."""
    import zarr

    ctrl, _ = make_controller(qtbot, request)
    assert ZarrSaver is not None, "ZarrSaver not yet implemented"
    # Mutate live laser state after construction — the saved metadata must
    # reflect the live value, not a config default.
    original_label = ctrl.lasers[0].label
    try:
        ctrl.lasers[0].label = "Mutated (555 nm)"
        store_path = tmp_path / "stack.ome.zarr"
        saver = ZarrSaver(ctrl, store_path=str(store_path))
        saver.start_stack()
        frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
        saver.write_frame(frame)
        saver.finalize()

        root = zarr.open(str(store_path), mode="r")
        channels = root.attrs["omero"]["channels"]
        assert channels[0]["label"] == "Mutated (555 nm)"
    finally:
        ctrl.lasers[0].label = original_label


@pytest.mark.xfail(reason=_WAVE0, strict=False)
def test_ngff_metadata(qtbot, request, tmp_path) -> None:
    """SAV-02: NGFF v0.5 metadata is written — ``ome.version`` and the
    ``multiscales`` structure with at least one dataset pointing at L0."""
    import zarr

    ctrl, _ = make_controller(qtbot, request)
    assert ZarrSaver is not None, "ZarrSaver not yet implemented"
    store_path = tmp_path / "stack.ome.zarr"
    saver = ZarrSaver(ctrl, store_path=str(store_path))
    saver.start_stack()
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    saver.write_frame(frame)
    saver.finalize()

    root = zarr.open(str(store_path), mode="r")
    ome = root.attrs["ome"]
    assert ome["version"] == "0.5"
    multiscales = ome["multiscales"]
    assert len(multiscales) >= 1
    datasets = multiscales[0]["datasets"]
    assert len(datasets) >= 1
    assert datasets[0]["path"] == "0"


@pytest.mark.xfail(reason=_WAVE0, strict=False)
def test_acquisition_group(qtbot, request, tmp_path) -> None:
    """D-04: the ``/acquisition`` group records the motor 1D datasets
    (vertical/horizontal/camera positions) and the scan-parameter root
    attrs (step size, scan parameters) matching the live controller."""
    import zarr

    ctrl, _ = make_controller(qtbot, request)
    assert ZarrSaver is not None, "ZarrSaver not yet implemented"
    store_path = tmp_path / "stack.ome.zarr"
    saver = ZarrSaver(ctrl, store_path=str(store_path))
    saver.start_stack()
    frame = np.zeros((ctrl.camera.ysize, ctrl.camera.xsize), dtype=np.uint16)
    saver.write_frame(frame)
    saver.finalize()

    root = zarr.open(str(store_path), mode="r")
    acq = root["acquisition"]
    # Motor 1D datasets for each axis.
    assert "motor_position_vertical" in acq
    assert "motor_position_horizontal" in acq
    assert "motor_position_camera" in acq
    # Scan-parameter root attrs.
    assert "step_size" in root.attrs
