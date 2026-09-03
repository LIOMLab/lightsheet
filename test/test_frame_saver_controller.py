"""FrameSaverController extraction tests (god-object split).

``FrameSaverController`` is a plain-Python collaborator that owns the
``FrameSaver`` + ``FrameViewer`` QObject instances and routes the
shell's save/enqueue calls through to them. The QObjects themselves
(``FrameSaver`` / ``FrameViewer``) are defined in
``lightsheet/gui/frame_saver_controller.py`` alongside this collaborator
(moved verbatim from ``lightsheet/gui/controller.py`` — a
behavior-preserving mechanical relocation). The shell delegates through
``self._fs``.

``Controller_MainWindow`` cannot be instantiated on this Mac (no PySide6
display), so the tests construct ``FrameSaverController`` directly with a
Mock stand-in shell and assert on the wrapped instances + the routed
calls. The ``FrameSaver`` / ``FrameViewer`` classes ARE constructible on
Mac (they only need a QObject parent + numpy for the default frame) —
PySide6 is installed in the dev venv, and ``conftest.py`` stubs the hardware
SDKs — so the real classes are used here, not Mocks.

Behavior covered (per the plan's ``<behavior>`` block):

1. constructing ``FrameSaverController(bundle, shell)`` creates a
   ``frame_saver`` (a ``FrameSaver`` parented to ``shell``) and a
   ``frame_viewer`` (a ``FrameViewer`` parented to ``shell``, sized from
   ``bundle.camera.ysize`` / ``bundle.camera.xsize``).
2. calling ``FrameSaverController.enqueue_frame(frame)`` delegates to the
   wrapped ``frame_viewer.enqueue_frame(frame)``.
3. ``FrameSaver.sig_status_message`` is connected to
   ``shell.updateUi_message_printer`` after the extraction (the same
   wiring the pre-extraction ``hardware_init`` performed).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import numpy as np
import pytest
from PySide6.QtCore import QObject
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")  # FrameSaver/FrameViewer are QObjects

from lightsheet.gui.coordinators.frame_saver_controller import (
    FrameSaver,
    FrameSaverController,
    FrameViewer,
)
from lightsheet.hal import (
    DeviceBundle,
    MockCamera,
    MockETLs,
    MockLaser,
    MockMotors,
    MockSigGen,
)


class _ShellStandin(QObject):
    """Minimal QObject stand-in for the shell.

    FrameSaver/FrameViewer are QObjects parented to the shell, so the
    shell stand-in must itself be a QObject (PySide6 rejects a Mock as a
    parent). The ``updateUi_message_printer`` slot is the
    sig_status_message receiver — track calls on it via a list.
    ``ui.imageView`` is the widget FrameViewer's __init__ seeds the
    default frame into (a Mock is fine — the call is a no-op for the
    test). ``save_format`` is read by FrameSaver.__init__.
    """

    def __init__(self) -> None:
        super().__init__()
        self.message_printer_calls: list[str] = []
        self.sig_message = Mock()
        self.ui = Mock()
        self.save_format = "hdf5"

    def updateUi_message_printer(self, message: str) -> None:
        self.message_printer_calls.append(message)


def _make_bundle() -> DeviceBundle:
    """Build a demo DeviceBundle with the camera dimensions
    FrameSaverController reads (bundle.camera.ysize / xsize)."""
    camera = MockCamera(verbose=True)
    siggen = MockSigGen(camera)
    motors = MockMotors()
    lasers = (
        MockLaser(wavelength=555, max_power_mw=300.0, label="Laser 1 (555 nm)"),
        MockLaser(wavelength=647, max_power_mw=150.0, label="Laser 2 (647 nm)"),
    )
    etls = MockETLs()
    return DeviceBundle(
        camera=camera, siggen=siggen, motors=motors, etls=etls, lasers=lasers
    )


def _make_shell() -> _ShellStandin:
    """Build a QObject shell stand-in exposing the attributes
    FrameSaverController.__init__ touches: ``updateUi_message_printer``
    (the sig_status_message slot) and a ``sig_message`` Mock so any
    incidental emit is a no-op."""
    return _ShellStandin()


def test_init_creates_frame_saver_parented_to_shell() -> None:
    """FrameSaverController(bundle, shell) constructs a FrameSaver
    parented to shell (the QObject parent)."""
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    assert isinstance(fs.frame_saver, FrameSaver), (
        "FrameSaverController must own a FrameSaver instance"
    )
    # FrameSaver.__init__ sets self.parent = parent (the shell) and calls
    # QObject.__init__(self, parent) — both reference the shell. The
    # .parent attribute is the shell (FrameSaver stores it for the save
    # worker to read self.parent.lasers).
    assert fs.frame_saver.parent is shell, (
        "FrameSaver must be parented to the shell (QObject parent)"
    )


def test_init_creates_frame_viewer_sized_from_bundle_camera() -> None:
    """FrameSaverController(bundle, shell) constructs a FrameViewer
    parented to shell, sized from bundle.camera.ysize / xsize."""
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    assert isinstance(fs.frame_viewer, FrameViewer), (
        "FrameSaverController must own a FrameViewer instance"
    )
    assert fs.frame_viewer.parent is shell, (
        "FrameViewer must be parented to the shell (QObject parent)"
    )
    assert fs.frame_viewer.rows == int(bundle.camera.ysize), (  # ty: ignore[invalid-argument-type]
        "FrameViewer rows must come from bundle.camera.ysize"
    )
    assert fs.frame_viewer.columns == int(bundle.camera.xsize), (  # ty: ignore[invalid-argument-type]
        "FrameViewer columns must come from bundle.camera.xsize"
    )


def test_enqueue_frame_delegates_to_frame_viewer() -> None:
    """FrameSaverController.enqueue_frame(frame) delegates to the wrapped
    frame_viewer.enqueue_frame(frame). Asserted by substituting a Mock
    frame_viewer on the controller instance and confirming the call
    lands on it with the same frame argument."""
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    # Substitute a Mock frame_viewer so the delegation is observable
    # without relying on the real queue.Queue internals.
    fs.frame_viewer = Mock()
    frame = np.zeros((4, 4), dtype=np.uint16)
    fs.enqueue_frame(frame)
    fs.frame_viewer.enqueue_frame.assert_called_once_with(frame)


def test_frame_saver_sig_status_message_connected_to_shell_slot() -> None:
    """FrameSaver.sig_status_message must be connected to
    shell.updateUi_message_printer after the extraction — the same
    wiring the pre-extraction hardware_init performed (FrameSaver is a
    QObject running its save worker on a thread; its status messages
    must cross to the GUI thread via the signal/slot queue, AGENTS.md
    §11).

    Asserted behaviorally: emitting the signal must call the shell slot
    (PySide6 does not expose a public receiver enumeration on Signal).
    """
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    fs.frame_saver.sig_status_message.emit("test message")
    assert shell.message_printer_calls == ["test message"], (
        "sig_status_message.emit must route to shell.updateUi_message_printer"
    )


def test_pass_through_methods_route_to_frame_saver() -> None:
    """The pass-through methods (reinit, add_sample_name,
    add_motor_parameters, set_files, start_saving, enqueue_buffer,
    stop_saving) route to the wrapped frame_saver. Asserted by
    substituting a Mock frame_saver and confirming each call lands."""
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    fs.frame_saver = Mock()

    fs.reinit(3)
    fs.frame_saver.reinit.assert_called_once_with(3)

    fs.add_sample_name("sample")
    fs.frame_saver.add_sample_name.assert_called_once_with("sample")

    fs.add_motor_parameters("h", "v", "c")
    fs.frame_saver.add_motor_parameters.assert_called_once_with("h", "v", "c")

    fs.set_files(1, "name", "singleImage", 1, "ETLscan")
    fs.frame_saver.set_files.assert_called_once_with(
        1, "name", "singleImage", 1, "ETLscan", wavelengths=None
    )

    fs.enqueue_buffer(np.zeros((1, 1), dtype=np.uint16))
    fs.frame_saver.enqueue_buffer.assert_called_once()

    fs.start_saving()
    fs.frame_saver.start_saving.assert_called_once()

    fs.stop_saving()
    fs.frame_saver.stop_saving.assert_called_once()


def test_frame_saver_worker_surfaces_h5py_error_and_stops(tmp_path: Path) -> None:
    """IN-04: a non-timeout exception (h5py write error, disk full, HDF5
    corruption) in frame_saver_worker must surface to the operator via
    sig_status_message and set saving_started=False so the worker stops,
    rather than silently retrying on a corrupt file.

    Simulates the error by pointing filenames_list at a path inside a
    read-only directory so h5py.File(..., "a") raises OSError on open.
    The worker should emit a "Save error: ..." message and flip
    saving_started to False.
    """
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    saver = fs.frame_saver

    # Read-only directory so h5py.File(path, "a") raises OSError/PermissionError.
    ro_dir = tmp_path / "readonly"
    ro_dir.mkdir()
    ro_dir.chmod(0o555)
    bad_path = str(ro_dir / "plane_00001.hdf5")

    saver.filenames_list = [bad_path]
    saver.number_of_datasets = 1
    saver.datasets_name = "dataset_"
    saver.sample_name = "test"
    saver.horizontal_positions_list = ["0"]
    saver.vertical_positions_list = ["0"]
    saver.camera_positions_list = ["0"]
    saver.saving_started = True

    # Run the worker synchronously (no thread) — the error path is
    # independent of threading; it's a try/except in the worker body.
    saver.frame_saver_worker()

    # The error must have surfaced via sig_status_message (routed to the
    # shell slot). At least one message should mention "Save error".
    error_msgs = [m for m in shell.message_printer_calls if m.startswith("Save error")]
    assert error_msgs, (
        "frame_saver_worker must emit a 'Save error: ...' message on a "
        "non-timeout exception; got: " + repr(shell.message_printer_calls)
    )
    # The worker must have stopped (saving_started flipped to False).
    assert saver.saving_started is False, (
        "frame_saver_worker must set saving_started=False on a save error "
        "so it does not keep writing to a corrupt file"
    )

    # Restore permissions so tmp_path cleanup can remove the directory.
    ro_dir.chmod(0o755)


def test_set_files_sequential_plane_numbers(tmp_path: Path) -> None:
    """In a FRESH directory, set_files(number_of_files=3,
    files_name="stack", scan_type="z", ..., wavelengths=[555]) produces
    filenames_list = ["stack_z_555nm.hdf5", "stack_z_555nm_01.hdf5",
    "stack_z_555nm_02.hdf5"] — the compact convention: NO suffix on the
    first file, then _01, _02 (2-digit, width scales with file count),
    with the _{wavelength}nm suffix (the wavelengths=None branch is
    retired). The old _plane_00001 segment is dropped.

    set_files uses os.path.isfile against the CWD-relative filename, so
    the test chdir's into tmp_path (a fresh directory) for the duration
    of the call. filenames_list is reset to [] before the call so the
    assertion is independent of any prior state.
    """
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    saver = fs.frame_saver
    saver.filenames_list = []
    saver.filenames_lists = []

    import os

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        saver.set_files(3, "stack", "z", 1, "dataset_", wavelengths=[555])
    finally:
        os.chdir(cwd)

    assert saver.filenames_list == [
        "stack_555nm.hdf5",
        "stack_555nm_01.hdf5",
        "stack_555nm_02.hdf5",
    ], (
        "set_files in a fresh directory must produce the compact "
        "sequential names (no scan_type, no suffix on first, then _01, "
        "_02) with the _{wavelength}nm suffix; got: " + repr(saver.filenames_list)
    )


def test_set_files_collision_suffix(tmp_path: Path) -> None:
    """In a directory where "stack_z_555nm.hdf5" ALREADY EXISTS,
    set_files produces "stack_z_555nm_01.hdf5" for the first slot (the
    sequential counter increments past the collision), and subsequent
    slots continue _02, _03.

    Pre-creates the colliding file in tmp_path, chdir's there for the
    set_files call (set_files uses os.path.isfile on the bare filename),
    then asserts on filenames_list.
    """
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    saver = fs.frame_saver
    saver.filenames_list = []
    saver.filenames_lists = []

    # Pre-create the colliding file in the fresh directory.
    (tmp_path / "stack_555nm.hdf5").write_bytes(b"")

    import os

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        saver.set_files(3, "stack", "z", 1, "dataset_", wavelengths=[555])
    finally:
        os.chdir(cwd)

    assert saver.filenames_list == [
        "stack_555nm_01.hdf5",
        "stack_555nm_02.hdf5",
        "stack_555nm_03.hdf5",
    ], (
        "set_files must shift the sequential counter past a colliding "
        "first file (_01, _02, _03); got: " + repr(saver.filenames_list)
    )


def test_set_files_collision_suffix_increments(tmp_path: Path) -> None:
    """When both stack_z_555nm.hdf5 and stack_z_555nm_01.hdf5 exist, the
    counter increments past both — the first slot gets _02, then _03,
    _04.

    Pre-creates both colliding files in tmp_path, chdir's there for the
    set_files call, then asserts the sequential counter bumped past both.
    """
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    saver = fs.frame_saver
    saver.filenames_list = []
    saver.filenames_lists = []

    # Pre-create both the base and the _01 collision files.
    (tmp_path / "stack_555nm.hdf5").write_bytes(b"")
    (tmp_path / "stack_555nm_01.hdf5").write_bytes(b"")

    import os

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        saver.set_files(3, "stack", "z", 1, "dataset_", wavelengths=[555])
    finally:
        os.chdir(cwd)

    assert saver.filenames_list == [
        "stack_555nm_02.hdf5",
        "stack_555nm_03.hdf5",
        "stack_555nm_04.hdf5",
    ], (
        "set_files must increment the sequential counter past existing "
        "base and _01 to _02, _03, _04; got: " + repr(saver.filenames_list)
    )


# ---------------------------------------------------------------------------
# Multi-channel per-channel HDF5 save separation (MCA-03 / D-05)
# ---------------------------------------------------------------------------


def test_set_files_multi_channel_wavelength_suffix(tmp_path: Path) -> None:
    """set_files with wavelengths=[555, 640] builds
    self.filenames_lists as a list of 2 lists (one per channel), each
    length number_of_files, with _{wavelength}nm suffix and the compact
    sequential counter (no suffix on first, then _01, _02). Wavelength
    values come from the caller (which reads them from the live ILaser
    instance).
    """
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    saver = fs.frame_saver
    saver.filenames_list = []
    saver.filenames_lists = []

    import os
    import re

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        saver.set_files(
            2,
            "scan",
            "stack",
            1,
            "reconstructed_frame",
            wavelengths=[555, 640],
        )
    finally:
        os.chdir(cwd)

    assert isinstance(saver.filenames_lists, list), (
        "filenames_lists must be a list of lists in multi-channel mode"
    )
    assert len(saver.filenames_lists) == 2, (
        "filenames_lists must have one list per channel (2 channels)"
    )
    assert len(saver.filenames_lists[0]) == 2, (
        "channel 0 list must have number_of_files entries"
    )
    assert len(saver.filenames_lists[1]) == 2, (
        "channel 1 list must have number_of_files entries"
    )
    for fn in saver.filenames_lists[0]:
        assert re.search(r"_555nm(_\d+)?\.hdf5$", fn), (
            f"channel 0 filename must carry _555nm suffix: {fn}"
        )
    for fn in saver.filenames_lists[1]:
        assert re.search(r"_640nm(_\d+)?\.hdf5$", fn), (
            f"channel 1 filename must carry _640nm suffix: {fn}"
        )
    # Compact sequential counter: no scan_type, no suffix on first, _01 on second.
    assert saver.filenames_lists[0][0] == "scan_555nm.hdf5"
    assert saver.filenames_lists[0][1] == "scan_555nm_01.hdf5"
    assert saver.filenames_lists[1][0] == "scan_640nm.hdf5"
    assert saver.filenames_lists[1][1] == "scan_640nm_01.hdf5"


def test_set_files_single_channel_has_suffix(tmp_path: Path) -> None:
    """Single-channel set_files with wavelengths=[555] builds
    self.filenames_lists with one channel list (length number_of_files)
    AND populates self.filenames_list from filenames_lists[0] so the
    single-channel frame_saver_worker (which reads filenames_list) is
    byte-identical except for the filename suffix. Each filename MUST
    carry the _{wavelength}nm suffix — the wavelengths=None back-compat
    branch is retired.
    """
    import os
    import re

    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    saver = fs.frame_saver
    saver.filenames_list = []
    saver.filenames_lists = []

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        saver.set_files(
            2,
            "scan",
            "stack",
            1,
            "reconstructed_frame",
            wavelengths=[555],
        )
    finally:
        os.chdir(cwd)

    # filenames_lists has one channel list (single-channel mode passes a
    # 1-element wavelengths list).
    assert len(saver.filenames_lists) == 1, (
        "single-channel filenames_lists must have one channel list"
    )
    assert len(saver.filenames_lists[0]) == 2, (
        "channel 0 list must have number_of_files entries"
    )
    # filenames_list is populated from filenames_lists[0] so the
    # single-channel frame_saver_worker (which reads filenames_list) is
    # unchanged.
    assert len(saver.filenames_list) == 2, (
        "single-channel filenames_list must have number_of_files entries"
    )
    assert saver.filenames_list == saver.filenames_lists[0], (
        "filenames_list must mirror filenames_lists[0] in single-channel mode"
    )
    for fn in saver.filenames_list:
        assert re.search(r"_555nm(_\d+)?\.hdf5$", fn), (
            f"single-channel filename must carry _555nm suffix "
            f"(optionally followed by a sequential _NN): {fn}"
        )


def test_set_files_rejects_wavelengths_none(tmp_path: Path) -> None:
    """The wavelengths=None back-compat branch is retired. set_files
    raises ValueError when wavelengths is None so a stale caller that
    forgets to pass wavelengths fails loudly instead of producing an
    unsuffixed file."""
    import os

    import pytest

    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    saver = fs.frame_saver
    saver.filenames_list = []
    saver.filenames_lists = []

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        with pytest.raises(ValueError):
            saver.set_files(
                2,
                "scan",
                "stack",
                1,
                "reconstructed_frame",
                wavelengths=None,
            )
    finally:
        os.chdir(cwd)


def test_set_files_collision_avoidance_per_channel(tmp_path: Path) -> None:
    """Collision avoidance runs independently per channel — pre-create
    channel 0's first file; channel 0 shifts to _01 while channel 1 (no
    collision) stays unsuffixed.
    """
    import os

    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    saver = fs.frame_saver
    saver.filenames_list = []
    saver.filenames_lists = []

    # Pre-create channel 0's first file so it collides
    (tmp_path / "scan_555nm.hdf5").write_bytes(b"")

    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        saver.set_files(
            1,
            "scan",
            "stack",
            1,
            "reconstructed_frame",
            wavelengths=[555, 640],
        )
    finally:
        os.chdir(cwd)

    assert len(saver.filenames_lists) == 2
    # Channel 0 collides → shifts to _01
    assert saver.filenames_lists[0][0] == "scan_555nm_01.hdf5", (
        f"channel 0 colliding filename must shift to _01: {saver.filenames_lists[0][0]}"
    )
    # Channel 1 does not collide → no sequential suffix
    assert saver.filenames_lists[1][0] == "scan_640nm.hdf5", (
        f"channel 1 non-colliding filename must have no sequential "
        f"suffix: {saver.filenames_lists[1][0]}"
    )


def _make_mock_h5py() -> tuple[type, dict[str, list[tuple[str, np.ndarray]]]]:
    """Build a Mock h5py.File replacement that records create_dataset calls.

    Returns (mock_file_class, written_files) where written_files is a dict
    mapping filename -> list of (dataset_name, data_array) tuples.
    """
    written_files: dict[str, list[tuple[str, np.ndarray]]] = {}

    class _MockDataset:
        def __init__(self, name: str, data: np.ndarray) -> None:
            self.name = name
            self.data = data
            self.attrs: dict = {}  # ty: ignore[missing-type-argument]

    class _MockFile:
        def __init__(self, path: str, mode: str = "a") -> None:
            self.path = path
            self.attrs: dict = {}  # ty: ignore[missing-type-argument]
            written_files.setdefault(path, [])

        def create_dataset(
            self, name: str, data: Any = None, **kwargs: Any
        ) -> _MockDataset:
            ds = _MockDataset(name, data)
            written_files[self.path].append((name, data))
            return ds

        def close(self) -> None:
            pass

    return _MockFile, written_files


def test_frame_saver_worker_branches_on_channel_tag(tmp_path: Path) -> None:
    """MCA-03: frame_saver_worker branches on the channel tag from the
    dequeued (channel_idx, frame) tuple — frameA → filenames_lists[0][0],
    frameB → filenames_lists[1][0]. The single-consumer queue contract
    is preserved (one queue, one consume loop, no split).
    """
    from unittest.mock import patch

    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    saver = fs.frame_saver

    # Set up multi-channel filenames_lists (2 channels x 2 planes each)
    saver.filenames_lists = [
        [
            str(tmp_path / "ch0_plane_00001.hdf5"),
            str(tmp_path / "ch0_plane_00002.hdf5"),
        ],
        [
            str(tmp_path / "ch1_plane_00001.hdf5"),
            str(tmp_path / "ch1_plane_00002.hdf5"),
        ],
    ]
    saver.filenames_list = []
    saver.number_of_datasets = 1
    saver.datasets_name = "dataset_"
    saver.sample_name = "test"
    saver.horizontal_positions_list = ["0", "0"]
    saver.vertical_positions_list = ["0", "0"]
    saver.camera_positions_list = ["0", "0"]
    saver.saving_started = True

    mock_file_cls, written_files = _make_mock_h5py()

    frameA = np.zeros((4, 4), dtype=np.uint16)
    frameA[0, 0] = 100
    frameB = np.zeros((4, 4), dtype=np.uint16)
    frameB[0, 0] = 200

    saver.enqueue_buffer((0, frameA))
    saver.enqueue_buffer((1, frameB))

    # Simulate stop_saving() flipping the flag after the acquisition
    # queued all frames — the worker drains the remaining frames then
    # exits on the next queue.Empty (the documented termination
    # contract, frame_saver_controller.py lines 542-550). Without this
    # the worker loops forever waiting for the 2 unwritten planes
    # (total_files=4, only 2 frames enqueued).
    saver.saving_started = False

    with patch(
        "lightsheet.gui.coordinators.frame_saver_controller.h5py.File",
        mock_file_cls,
    ):
        # Mock metadata methods (they need lasers/motors/siggen/camera
        # which the _ShellStandin does not have)
        saver._write_laser_metadata = Mock()
        saver._write_acquisition_metadata = Mock()
        saver.frame_saver_worker()

    # frameA → filenames_lists[0][0], frameB → filenames_lists[1][0]
    ch0_file = saver.filenames_lists[0][0]
    ch1_file = saver.filenames_lists[1][0]
    assert ch0_file in written_files, f"channel 0 file must be opened: {ch0_file}"
    assert ch1_file in written_files, f"channel 1 file must be opened: {ch1_file}"
    assert len(written_files[ch0_file]) == 1, (
        "channel 0 file must have exactly 1 dataset"
    )
    assert len(written_files[ch1_file]) == 1, (
        "channel 1 file must have exactly 1 dataset"
    )
    np.testing.assert_array_equal(written_files[ch0_file][0][1], frameA)
    np.testing.assert_array_equal(written_files[ch1_file][0][1], frameB)


def test_frame_saver_worker_single_channel_bare_ndarray(tmp_path: Path) -> None:
    """Back-compat: a bare ndarray (no channel tag) dequeued by
    frame_saver_worker uses the existing self.filenames_list path —
    written to filenames_list[0]. The multi-channel filenames_lists
    is empty so the worker takes the single-channel branch.
    """
    from unittest.mock import patch

    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
    saver = fs.frame_saver

    saver.filenames_list = [str(tmp_path / "plane_00001.hdf5")]
    saver.filenames_lists = []  # empty → single-channel mode
    saver.number_of_datasets = 1
    saver.datasets_name = "dataset_"
    saver.sample_name = "test"
    saver.horizontal_positions_list = ["0"]
    saver.vertical_positions_list = ["0"]
    saver.camera_positions_list = ["0"]
    saver.saving_started = True

    mock_file_cls, written_files = _make_mock_h5py()

    frame = np.zeros((4, 4), dtype=np.uint16)
    frame[0, 0] = 42

    saver.enqueue_buffer(frame)

    with patch(
        "lightsheet.gui.coordinators.frame_saver_controller.h5py.File",
        mock_file_cls,
    ):
        saver._write_laser_metadata = Mock()
        saver._write_acquisition_metadata = Mock()
        saver.frame_saver_worker()

    assert saver.filenames_list[0] in written_files, (
        f"single-channel file must be opened: {saver.filenames_list[0]}"
    )
    assert len(written_files[saver.filenames_list[0]]) == 1
    np.testing.assert_array_equal(written_files[saver.filenames_list[0]][0][1], frame)


# ---------------------------------------------------------------------------
# updateUi_save_single_image multi-channel dual-save (MCA-03 single mode)
# ---------------------------------------------------------------------------
#
# These tests construct the real Controller_MainWindow via the shared
# make_controller fixture (the same one test_controller_methods.py uses for
# the single-image save tests) because updateUi_save_single_image reads
# self._shell._auto_laser1 / _auto_laser2 / lasers / reconstructed_frames —
# attributes that only exist on the real shell, not on the _ShellStandin
# used by the FrameSaver-only tests above. The FrameSaver collaborator
# (self._fs) is mocked so the test asserts on the routed calls without
# spinning up the save worker thread.


def test_save_single_image_multi_channel_writes_two_files(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    """Multi-channel single mode: when both auto-laser checkboxes are
    checked, the Save button writes TWO wavelength-suffixed HDF5 files
    (one per channel). set_files is called with wavelengths=[wl1, wl2]
    read from the live ILaser instances, and enqueue_buffer is called
    twice with (0, frameA) and (1, frameB) tagged tuples — one per
    channel. The single-consumer queue contract is preserved (the two
    tagged frames go through the same enqueue_buffer → single queue).
    """
    from _helpers.controller_fixture import (
        make_controller,
    )

    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.saving_allowed = True
    ctrl.save_directory = "/tmp"
    ctrl.save_filename = "test"
    ctrl.save_filepath = "/tmp/test"
    ctrl.image_hor_pos_text = "0.0"
    ctrl.image_ver_pos_text = "0.0"
    ctrl.image_cam_pos_text = "0.0"

    # Wavelengths come from the live ILaser instances — never hardcoded.
    wl1 = ctrl.lasers[0].wavelength
    wl2 = ctrl.lasers[1].wavelength
    frameA = np.zeros((4, 4), dtype=np.uint16)
    frameA[0, 0] = 100
    frameB = np.zeros((4, 4), dtype=np.uint16)
    frameB[0, 0] = 200
    ctrl.reconstructed_frames = {wl1: frameA, wl2: frameB}

    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = True

    # reconstructed (default) radio path — neither crop nor full checked
    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)

    ctrl._fs.reinit = Mock()
    ctrl._fs.set_files = Mock()
    ctrl._fs.enqueue_buffer = Mock()
    ctrl._fs.start_saving = Mock()
    ctrl._fs.stop_saving = Mock()
    ctrl._fs.add_sample_name = Mock()
    ctrl._fs.add_motor_parameters = Mock()

    ctrl.save_panel.updateUi_save_single_image()

    ctrl._fs.set_files.assert_called_once_with(
        1,
        ctrl.save_filepath,
        "singleImage",
        1,
        "reconstructed_frame",
        wavelengths=[wl1, wl2],
    )
    enqueue_calls = ctrl._fs.enqueue_buffer.call_args_list
    assert len(enqueue_calls) == 2, (
        f"multi-channel must enqueue two tagged frames; got {len(enqueue_calls)}"
    )
    assert enqueue_calls[0].args == ((0, frameA),), (
        f"first enqueue must be (0, frameA); got {enqueue_calls[0].args}"
    )
    assert enqueue_calls[1].args == ((1, frameB),), (
        f"second enqueue must be (1, frameB); got {enqueue_calls[1].args}"
    )
    ctrl._fs.start_saving.assert_called_once()
    ctrl._fs.stop_saving.assert_called_once()


def test_save_single_image_single_channel_unchanged(
    qtbot: QtBot, request: pytest.FixtureRequest
) -> None:
    """Single-channel mode (one auto-laser checked): updateUi_save_single_image
    calls set_files with wavelengths=[active_wavelength] so the saved
    filename carries the _{wavelength}nm suffix. enqueue_buffer is called
    once with the bare reconstructed_frame (no channel tag) — the single-
    channel save worker reads filenames_list (populated from
    filenames_lists[0]).
    """
    from _helpers.controller_fixture import (
        make_controller,
    )

    ctrl, _bundle = make_controller(qtbot, request)
    ctrl.saving_allowed = True
    ctrl.save_directory = "/tmp"
    ctrl.save_filename = "test"
    ctrl.save_filepath = "/tmp/test"
    ctrl.image_hor_pos_text = "0.0"
    ctrl.image_ver_pos_text = "0.0"
    ctrl.image_cam_pos_text = "0.0"

    frameA = np.zeros((4, 4), dtype=np.uint16)
    frameA[0, 0] = 100
    ctrl.reconstructed_frame = frameA

    # Single-channel: only one auto-laser checked
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False

    ctrl.save_panel.ui.radioButton_saveAllCrop.setChecked(False)
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(False)

    ctrl._fs.reinit = Mock()
    ctrl._fs.set_files = Mock()
    ctrl._fs.enqueue_buffer = Mock()
    ctrl._fs.start_saving = Mock()
    ctrl._fs.stop_saving = Mock()
    ctrl._fs.add_sample_name = Mock()
    ctrl._fs.add_motor_parameters = Mock()

    ctrl.save_panel.updateUi_save_single_image()

    # set_files called with wavelengths=[active_wavelength] (single-channel
    # now passes the active laser wavelength so the suffix is always
    # present).
    active_wl = int(ctrl.lasers[0].wavelength)
    ctrl._fs.set_files.assert_called_once_with(
        1,
        ctrl.save_filepath,
        "singleImage",
        1,
        "reconstructed_frame",
        wavelengths=[active_wl],
    )
    ctrl._fs.enqueue_buffer.assert_called_once_with(frameA)
    ctrl._fs.start_saving.assert_called_once()
    ctrl._fs.stop_saving.assert_called_once()


# ---------------------------------------------------------------------------
# Per-channel Zarr merge (MCA-04 / D-06)
# ---------------------------------------------------------------------------
#
# ZarrSaver.start_stack gains an n_channels param so the L0 array shape
# becomes (n_channels, n_planes, y, x); write_plane gains a channel_idx
# param so each channel's planes write to a distinct channel-axis index.
# Single-channel stays (1, z, y, x) (n_channels=1 default — back-compat
# with Phase 8). finalize guards len(omero_channels) == n_channels. The
# zarr_save_worker / both_save_worker branch on the channel tag from the
# dequeued (channel_idx, frame) tuple. These tests use the real
# Controller_MainWindow via make_controller because ZarrSaver reads
# self.parent.camera / .lasers / ._auto_laser1 / ._auto_laser2 /
# .save_directory / .stack_step / .siggen — attributes that only exist
# on the real shell.


def test_zarr_saver_start_stack_n_channels(
    qtbot: QtBot, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """MCA-04: start_stack(store_path, n_planes=3, n_channels=2)
    constructs the writer with shape (2, 3, ysize, xsize) and
    chunk_shape (1, 1, ysize, xsize). The channel axis is the leading
    axis so each channel's planes write to a distinct channel-axis
    index (NGFF v0.5 channel dimension)."""
    from _helpers.controller_fixture import (
        make_controller,
    )

    from lightsheet.gui.coordinators.frame_saver_controller import ZarrSaver

    ctrl, _ = make_controller(qtbot, request)
    ctrl.save_directory = str(tmp_path)
    ctrl.stack_step = 1.0

    store_path = str(tmp_path / "stack.ome.zarr")
    saver = ZarrSaver(ctrl)
    saver.start_stack(store_path, n_planes=3, n_channels=2)

    assert saver._writer is not None, "start_stack must construct the writer"
    arr = saver._writer._level0_array()
    assert arr.shape == (2, 3, ctrl.camera.ysize, ctrl.camera.xsize), (
        f"n_channels=2 writer shape must be (2, 3, y, x); got {arr.shape}"
    )
    assert arr.chunks == (1, 1, ctrl.camera.ysize, ctrl.camera.xsize), (
        f"chunk_shape must be (1, 1, y, x); got {arr.chunks}"
    )
    assert saver._n_channels == 2, "start_stack must store self._n_channels"


def test_zarr_saver_start_stack_single_channel_back_compat(
    qtbot: QtBot, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """MCA-04 back-compat: start_stack with n_channels=1 (and with
    n_channels omitted — default=1) produces shape (1, n_planes, y, x) —
    byte-identical to the Phase 8 single-channel writer shape."""
    from _helpers.controller_fixture import (
        make_controller,
    )

    from lightsheet.gui.coordinators.frame_saver_controller import ZarrSaver

    ctrl, _ = make_controller(qtbot, request)
    ctrl.save_directory = str(tmp_path)
    ctrl.stack_step = 1.0

    # Explicit n_channels=1
    store_path = str(tmp_path / "stack_a.ome.zarr")
    saver = ZarrSaver(ctrl)
    saver.start_stack(store_path, n_planes=3, n_channels=1)
    arr = saver._writer._level0_array()  # ty: ignore[unresolved-attribute]
    assert arr.shape == (1, 3, ctrl.camera.ysize, ctrl.camera.xsize), (
        f"n_channels=1 writer shape must be (1, 3, y, x); got {arr.shape}"
    )

    # n_channels omitted — default=1
    store_path_b = str(tmp_path / "stack_b.ome.zarr")
    saver_b = ZarrSaver(ctrl)
    saver_b.start_stack(store_path_b, n_planes=3)
    arr_b = saver_b._writer._level0_array()  # ty: ignore[unresolved-attribute]
    assert arr_b.shape == (1, 3, ctrl.camera.ysize, ctrl.camera.xsize), (
        f"default n_channels writer shape must be (1, 3, y, x); got {arr_b.shape}"
    )
    assert saver_b._n_channels == 1


def test_zarr_saver_write_plane_channel_idx(
    qtbot: QtBot, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """MCA-04: after start_stack(n_channels=2), write_plane(channel_idx=0,
    z_idx=1, frame=A, ...) writes A to writer[0, 1, :, :] and
    write_plane(channel_idx=1, z_idx=1, frame=B, ...) writes B to
    writer[1, 1, :, :]. Each channel's planes write to a distinct
    channel-axis index — they do not merge or collide."""
    from _helpers.controller_fixture import (
        make_controller,
    )

    from lightsheet.gui.coordinators.frame_saver_controller import ZarrSaver

    ctrl, _ = make_controller(qtbot, request)
    ctrl.save_directory = str(tmp_path)
    ctrl.stack_step = 1.0

    store_path = str(tmp_path / "stack.ome.zarr")
    saver = ZarrSaver(ctrl)
    saver.start_stack(store_path, n_planes=2, n_channels=2)

    ysize = ctrl.camera.ysize
    xsize = ctrl.camera.xsize
    frameA = np.zeros((ysize, xsize), dtype=np.uint16)
    frameA[0, 0] = 100
    frameB = np.zeros((ysize, xsize), dtype=np.uint16)
    frameB[0, 0] = 200

    saver.write_plane(0, 1, frameA, 0.0, 0.0, 0.0)
    saver.write_plane(1, 1, frameB, 0.0, 0.0, 0.0)
    assert saver._writer is not None

    np.testing.assert_array_equal(
        np.asarray(saver._writer[0, 1, :, :]),
        frameA,
    )
    np.testing.assert_array_equal(
        np.asarray(saver._writer[1, 1, :, :]),
        frameB,
    )


def test_zarr_saver_write_plane_motor_positions_once_per_plane(
    qtbot: QtBot, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """MCA-04 / T-09-12: write_plane records motor positions only when
    channel_idx == 0 (once per plane, not per channel) — avoids
    duplicating position entries that would desync the Z->position
    mapping. Calling write_plane(0, z_idx=0, ...) and write_plane(1,
    z_idx=0, ...) for the same plane must leave each position list at
    length 1, not 2."""
    from _helpers.controller_fixture import (
        make_controller,
    )

    from lightsheet.gui.coordinators.frame_saver_controller import ZarrSaver

    ctrl, _ = make_controller(qtbot, request)
    ctrl.save_directory = str(tmp_path)
    ctrl.stack_step = 1.0

    store_path = str(tmp_path / "stack.ome.zarr")
    saver = ZarrSaver(ctrl)
    saver.start_stack(store_path, n_planes=1, n_channels=2)

    ysize = ctrl.camera.ysize
    xsize = ctrl.camera.xsize
    frame = np.zeros((ysize, xsize), dtype=np.uint16)

    saver.write_plane(0, 0, frame, 1.0, 2.0, 3.0)
    saver.write_plane(1, 0, frame, 1.0, 2.0, 3.0)

    assert len(saver._horizontal_positions) == 1, (
        f"horizontal positions must be recorded once per plane (channel_idx==0 "
        f"guard); got length {len(saver._horizontal_positions)}"
    )
    assert len(saver._vertical_positions) == 1, (
        f"vertical positions must be recorded once per plane; got length "
        f"{len(saver._vertical_positions)}"
    )
    assert len(saver._camera_positions) == 1, (
        f"camera positions must be recorded once per plane; got length "
        f"{len(saver._camera_positions)}"
    )
    assert saver._horizontal_positions[0] == 1.0
    assert saver._vertical_positions[0] == 2.0
    assert saver._camera_positions[0] == 3.0


def test_zarr_saver_finalize_omero_channels_length(
    qtbot: QtBot, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """MCA-04 / T-09-11: with n_channels=2 and both auto-laser flags set,
    finalize() calls finalize_with_resolutions with len(omero_channels)
    == 2; with n_channels=1 and one flag, len == 1. The ZarrSaver layer
    asserts len(omero_channels) == self._n_channels (defense-in-depth
    over the writer's non-validating API) and raises RuntimeError on
    mismatch."""
    import zarr
    from _helpers.controller_fixture import (
        make_controller,
    )

    from lightsheet.gui.coordinators.frame_saver_controller import ZarrSaver

    ctrl, _ = make_controller(qtbot, request)
    ctrl.save_directory = str(tmp_path)
    ctrl.stack_step = 1.0
    # Shrink the camera so the Dask pyramid build is fast.
    ctrl.camera.xsize = 32
    ctrl.camera.ysize = 32

    # Two channels: both auto-lasers checked.
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = True
    store_path = str(tmp_path / "stack_2ch.ome.zarr")
    saver = ZarrSaver(ctrl)
    saver.start_stack(store_path, n_planes=1, n_channels=2)
    frame = np.zeros((32, 32), dtype=np.uint16)
    saver.write_plane(0, 0, frame, 0.0, 0.0, 0.0)
    saver.write_plane(1, 0, frame, 0.0, 0.0, 0.0)
    saver.finalize()

    root = zarr.open(store_path, mode="r")
    channels = root.attrs["ome"]["omero"]["channels"]  # ty: ignore[invalid-argument-type, not-subscriptable]
    assert len(channels) == 2, (
        f"n_channels=2 with both flags must produce 2 omero channels; "
        f"got {len(channels)}"
    )

    # One channel: only laser 1 checked.
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = False
    store_path_b = str(tmp_path / "stack_1ch.ome.zarr")
    saver_b = ZarrSaver(ctrl)
    saver_b.start_stack(store_path_b, n_planes=1, n_channels=1)
    saver_b.write_plane(0, 0, frame, 0.0, 0.0, 0.0)
    saver_b.finalize()

    root_b = zarr.open(store_path_b, mode="r")
    channels_b = root_b.attrs["ome"]["omero"]["channels"]  # ty: ignore[invalid-argument-type, not-subscriptable]
    assert len(channels_b) == 1, (
        f"n_channels=1 with one flag must produce 1 omero channel; "
        f"got {len(channels_b)}"
    )


def test_zarr_saver_finalize_raises_on_channel_count_mismatch(
    qtbot: QtBot, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """MCA-04 / T-09-11: if the caller passes n_channels that differs
    from len(_build_omero_channels()), finalize raises RuntimeError —
    defense-in-depth over the writer's non-validating API. The caller
    MUST derive n_channels from the same auto-laser flags as
    _build_omero_channels."""
    from _helpers.controller_fixture import (
        make_controller,
    )

    from lightsheet.gui.coordinators.frame_saver_controller import ZarrSaver

    ctrl, _ = make_controller(qtbot, request)
    ctrl.save_directory = str(tmp_path)
    ctrl.stack_step = 1.0
    ctrl.camera.xsize = 32
    ctrl.camera.ysize = 32

    # Both auto-lasers checked → _build_omero_channels returns 2, but
    # caller passes n_channels=1 → mismatch.
    ctrl._auto_laser1 = True
    ctrl._auto_laser2 = True
    store_path = str(tmp_path / "stack_mismatch.ome.zarr")
    saver = ZarrSaver(ctrl)
    saver.start_stack(store_path, n_planes=1, n_channels=1)
    frame = np.zeros((32, 32), dtype=np.uint16)
    saver.write_plane(0, 0, frame, 0.0, 0.0, 0.0)

    with pytest.raises(RuntimeError, match="omero_channels"):
        saver.finalize()


def test_zarr_save_worker_branches_on_channel_tag(
    qtbot: QtBot, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """MCA-04: zarr_save_worker branches on the channel tag from the
    dequeued (channel_idx, frame) tuple and calls
    ZarrSaver.write_plane(channel_idx, z_idx, frame, ...). Bare-ndarray
    dequeues (single-channel back-compat) call write_plane(0, z_idx,
    frame, ...). The single-consumer queue contract is preserved."""
    from unittest.mock import MagicMock

    from _helpers.controller_fixture import (
        make_controller,
    )

    from lightsheet.gui.coordinators.frame_saver_controller import (
        FrameSaverWorker,
    )

    ctrl, _ = make_controller(qtbot, request)
    ctrl.save_directory = str(tmp_path)
    ctrl.stack_step = 1.0
    ctrl.save_format = "zarr"
    saver = ctrl._fs.frame_saver

    # Replace the ZarrSaver with a Mock so we can assert on write_plane
    # calls without touching the disk.
    saver._zarr_saver = MagicMock()
    saver._zarr_saver.start_stack = MagicMock()
    saver._zarr_saver.write_plane = MagicMock()
    saver._zarr_saver.finalize = MagicMock()

    # Multi-channel: 2 channels x 2 planes = 4 frames total.
    saver.filenames_lists = []  # not used by zarr_save_worker
    saver.number_of_files = 2
    saver.number_of_datasets = 1
    saver.files_name = "stack"
    saver.datasets_name = "ch"
    saver.horizontal_positions_list = ["0.0", "0.0", "0.0", "0.0"]
    saver.vertical_positions_list = ["0.0", "0.0", "0.0", "0.0"]
    saver.camera_positions_list = ["0.0", "0.0", "0.0", "0.0"]
    saver.saving_started = True

    # The save queue is constructed in FrameSaver.__init__ with
    # maxsize = 2 * block_size (= 2 by default). enqueue_buffer uses
    # put(block=True), so pre-loading 4 frames with no consumer running
    # would deadlock on the 3rd put. Replace with an unbounded queue so
    # the real enqueue_buffer (block=True) can pre-load all 4 frames
    # before the worker starts consuming — mirrors how the real
    # acquisition enqueues near-instantly then the worker drains.
    import queue as _queue

    saver.queue = _queue.Queue()

    frameA = np.zeros((4, 4), dtype=np.uint16)
    frameA[0, 0] = 100
    frameB = np.zeros((4, 4), dtype=np.uint16)
    frameB[0, 0] = 200

    # Enqueue 2 channel-0 frames and 2 channel-1 frames (interleaved,
    # matching the StackWorker per-plane cycle emission order).
    saver.enqueue_buffer((0, frameA))
    saver.enqueue_buffer((1, frameB))
    saver.enqueue_buffer((0, frameA))
    saver.enqueue_buffer((1, frameB))
    # Simulate stop_saving() after enqueueing so the worker exits on the
    # next queue.Empty (total_frames=4, all 4 enqueued — but n_planes=2
    # so the worker exits after 2 z_idx increments per channel... see
    # implementation: zarr_save_worker counts z_idx up to n_planes=2).
    saver.saving_started = False

    worker = FrameSaverWorker(saver)
    finished: list[int] = []
    worker.sig_finished.connect(lambda: finished.append(1))
    worker.start_saving()

    assert len(finished) == 1, "sig_finished must emit exactly once"
    # start_stack called with n_planes (and the default n_channels=1 —
    # the worker does not yet derive n_channels from the auto-laser
    # flags; that is the caller's job via set_files / a future plan).
    saver._zarr_saver.start_stack.assert_called_once()
    # write_plane called 4 times — once per enqueued frame, with the
    # correct channel_idx.
    write_calls = saver._zarr_saver.write_plane.call_args_list
    assert len(write_calls) == 4, (
        f"write_plane must be called once per enqueued frame (4); got "
        f"{len(write_calls)}"
    )
    # First two calls: (0, 0, frameA, ...) and (1, 0, frameB, ...)
    # The z_idx increments per channel — channel 0's second frame is
    # z_idx=1, channel 1's second frame is z_idx=1.
    assert write_calls[0].args[0] == 0, (
        f"first write channel_idx must be 0; got {write_calls[0].args[0]}"
    )
    assert write_calls[1].args[0] == 1, (
        f"second write channel_idx must be 1; got {write_calls[1].args[0]}"
    )
    np.testing.assert_array_equal(write_calls[0].args[2], frameA)
    np.testing.assert_array_equal(write_calls[1].args[2], frameB)


def test_zarr_save_worker_single_channel_bare_ndarray_calls_write_plane_channel0(
    qtbot: QtBot, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """MCA-04 back-compat: a bare ndarray (no channel tag) dequeued by
    zarr_save_worker calls write_plane(0, z_idx, frame, ...) — channel
    0, the single-channel back-compat path."""
    from unittest.mock import MagicMock

    from _helpers.controller_fixture import (
        make_controller,
    )

    from lightsheet.gui.coordinators.frame_saver_controller import (
        FrameSaverWorker,
    )

    ctrl, _ = make_controller(qtbot, request)
    ctrl.save_directory = str(tmp_path)
    ctrl.stack_step = 1.0
    ctrl.save_format = "zarr"
    saver = ctrl._fs.frame_saver

    saver._zarr_saver = MagicMock()
    saver._zarr_saver.start_stack = MagicMock()
    saver._zarr_saver.write_plane = MagicMock()
    saver._zarr_saver.finalize = MagicMock()

    saver.filenames_lists = []
    saver.number_of_files = 1
    saver.number_of_datasets = 1
    saver.files_name = "stack"
    saver.datasets_name = "ch"
    saver.horizontal_positions_list = ["0.0"]
    saver.vertical_positions_list = ["0.0"]
    saver.camera_positions_list = ["0.0"]
    saver.saving_started = True

    frame = np.zeros((4, 4), dtype=np.uint16)
    saver.enqueue_buffer(frame)
    saver.saving_started = False

    worker = FrameSaverWorker(saver)
    finished: list[int] = []
    worker.sig_finished.connect(lambda: finished.append(1))
    worker.start_saving()

    assert len(finished) == 1
    write_calls = saver._zarr_saver.write_plane.call_args_list
    assert len(write_calls) == 1, (
        f"bare-ndarray dequeue must call write_plane once; got {len(write_calls)}"
    )
    assert write_calls[0].args[0] == 0, (
        f"bare-ndarray must route to channel_idx=0; got {write_calls[0].args[0]}"
    )
    np.testing.assert_array_equal(write_calls[0].args[2], frame)


def test_save_path_round_trips_channel_axis(
    qtbot: QtBot, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    """MCA-04 companion contract test (assumption_delta_decision): for
    n_channels=2, every enqueued tagged (channel_idx, frame) tuple
    round-trips through the channel axis — a tagged enqueue produces a
    Zarr writer shape whose shape[0] == n_channels AND an HDF5 filename
    in filenames_lists[channel_idx]. For n_channels=1, the single-channel
    path enqueues a bare ndarray and the frame lands in
    filenames_lists[0] (mirrored to filenames_list). This test goes red
    the instant a future phase reintroduces the singular assumption (a
    save path that bypasses the channel axis)."""
    from unittest.mock import patch

    for n_channels in (1, 2):
        bundle = _make_bundle()
        shell = _make_shell()
        fs = FrameSaverController(bundle, shell)  # ty: ignore[invalid-argument-type]
        saver = fs.frame_saver

        # Build per-channel filenames_lists (set_files with wavelengths).
        wavelengths = [555] if n_channels == 1 else [555, 640]
        saver.filenames_lists = []
        saver.filenames_list = []
        import os

        cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            saver.set_files(
                2,
                "scan",
                "stack",
                1,
                "reconstructed_frame",
                wavelengths=wavelengths,
            )
        finally:
            os.chdir(cwd)

        assert len(saver.filenames_lists) == n_channels, (
            f"n_channels={n_channels}: filenames_lists must have "
            f"{n_channels} lists; got {len(saver.filenames_lists)}"
        )
        for ch_idx in range(n_channels):
            assert len(saver.filenames_lists[ch_idx]) == 2, (
                f"n_channels={n_channels} ch={ch_idx}: list must have "
                f"2 entries; got {len(saver.filenames_lists[ch_idx])}"
            )

        # Enqueue frames: tagged tuples for multi-channel, bare ndarray
        # for single-channel (the production single-channel path enqueues
        # bare ndarrays — the worker reads filenames_list).
        mock_file_cls, written_files = _make_mock_h5py()
        frames = []
        if n_channels == 1:
            f = np.zeros((4, 4), dtype=np.uint16)
            f[0, 0] = 100
            frames.append(f)
            saver.enqueue_buffer(f)
        else:
            for ch_idx in range(n_channels):
                f = np.zeros((4, 4), dtype=np.uint16)
                f[0, 0] = 100 + ch_idx
                frames.append(f)
                saver.enqueue_buffer((ch_idx, f))
        saver.number_of_datasets = 1
        saver.datasets_name = "dataset_"
        saver.sample_name = "test"
        saver.horizontal_positions_list = ["0", "0"]
        saver.vertical_positions_list = ["0", "0"]
        saver.camera_positions_list = ["0", "0"]
        saver.saving_started = False  # simulate stop_saving after enqueue

        with patch(
            "lightsheet.gui.coordinators.frame_saver_controller.h5py.File",
            mock_file_cls,
        ):
            saver._write_laser_metadata = Mock()
            saver._write_acquisition_metadata = Mock()
            saver.frame_saver_worker()

        # Each channel's frame landed in the correct file. For
        # single-channel, the file is filenames_lists[0][0] (also
        # filenames_list[0]); for multi-channel, filenames_lists[ch][0].
        if n_channels == 1:
            expected_file = saver.filenames_lists[0][0]
            assert expected_file in written_files, (
                f"n_channels=1: file must be opened: {expected_file}; "
                f"got {list(written_files.keys())}"
            )
            np.testing.assert_array_equal(written_files[expected_file][0][1], frames[0])
        else:
            for ch_idx in range(n_channels):
                expected_file = saver.filenames_lists[ch_idx][0]
                assert expected_file in written_files, (
                    f"n_channels={n_channels} ch={ch_idx}: file must be opened: "
                    f"{expected_file}; got {list(written_files.keys())}"
                )
                np.testing.assert_array_equal(
                    written_files[expected_file][0][1], frames[ch_idx]
                )
