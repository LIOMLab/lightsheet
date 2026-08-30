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

from unittest.mock import Mock

import numpy as np
import pytest
from PySide6.QtCore import QObject

pytest.importorskip("PySide6")  # FrameSaver/FrameViewer are QObjects

from lightsheet.gui.coordinators.frame_saver_controller import FrameSaver, FrameViewer, FrameSaverController
from lightsheet.hal import DeviceBundle, MockCamera, MockETLs, MockLaser, MockMotors, MockSigGen


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
    return DeviceBundle(camera=camera, siggen=siggen, motors=motors, etls=etls, lasers=lasers)


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
    fs = FrameSaverController(bundle, shell)
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
    fs = FrameSaverController(bundle, shell)
    assert isinstance(fs.frame_viewer, FrameViewer), (
        "FrameSaverController must own a FrameViewer instance"
    )
    assert fs.frame_viewer.parent is shell, (
        "FrameViewer must be parented to the shell (QObject parent)"
    )
    assert fs.frame_viewer.rows == int(bundle.camera.ysize), (
        "FrameViewer rows must come from bundle.camera.ysize"
    )
    assert fs.frame_viewer.columns == int(bundle.camera.xsize), (
        "FrameViewer columns must come from bundle.camera.xsize"
    )


def test_enqueue_frame_delegates_to_frame_viewer() -> None:
    """FrameSaverController.enqueue_frame(frame) delegates to the wrapped
    frame_viewer.enqueue_frame(frame). Asserted by substituting a Mock
    frame_viewer on the controller instance and confirming the call
    lands on it with the same frame argument."""
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)
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
    fs = FrameSaverController(bundle, shell)
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
    fs = FrameSaverController(bundle, shell)
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


def test_frame_saver_worker_surfaces_h5py_error_and_stops(tmp_path) -> None:
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
    fs = FrameSaverController(bundle, shell)
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


def test_set_files_sequential_plane_numbers(tmp_path) -> None:
    """IN-05: in a FRESH directory, set_files(number_of_files=3,
    files_name="stack", scan_type="z", ...) produces filenames_list =
    ["stack_z_plane_00001.hdf5", "stack_z_plane_00002.hdf5",
    "stack_z_plane_00003.hdf5"] — per-file 1-based sequential plane
    index, 5-digit zero-padded.

    set_files uses os.path.isfile against the CWD-relative filename, so
    the test chdir's into tmp_path (a fresh directory) for the duration
    of the call. filenames_list is reset to [] before the call so the
    assertion is independent of any prior state.
    """
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)
    saver = fs.frame_saver
    saver.filenames_list = []

    import os

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        saver.set_files(3, "stack", "z", 1, "dataset_")
    finally:
        os.chdir(cwd)

    assert saver.filenames_list == [
        "stack_z_plane_00001.hdf5",
        "stack_z_plane_00002.hdf5",
        "stack_z_plane_00003.hdf5",
    ], (
        "set_files in a fresh directory must produce per-file 1-based "
        "sequential 5-digit zero-padded plane numbers; got: "
        + repr(saver.filenames_list)
    )


def test_set_files_collision_suffix(tmp_path) -> None:
    """IN-05: in a directory where "stack_z_plane_00001.hdf5" ALREADY
    EXISTS, set_files produces "stack_z_plane_00001_v02.hdf5" for that
    plane (the _vNN collision suffix, starting at v2), while
    non-colliding planes stay sequential.

    Pre-creates the colliding file in tmp_path, chdir's there for the
    set_files call (set_files uses os.path.isfile on the bare filename),
    then asserts on filenames_list.
    """
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)
    saver = fs.frame_saver
    saver.filenames_list = []

    # Pre-create the colliding file in the fresh directory.
    (tmp_path / "stack_z_plane_00001.hdf5").write_bytes(b"")

    import os

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        saver.set_files(3, "stack", "z", 1, "dataset_")
    finally:
        os.chdir(cwd)

    assert saver.filenames_list == [
        "stack_z_plane_00001_v02.hdf5",
        "stack_z_plane_00002.hdf5",
        "stack_z_plane_00003.hdf5",
    ], (
        "set_files must append _v02 to a colliding plane while leaving "
        "non-colliding planes sequential; got: "
        + repr(saver.filenames_list)
    )


def test_set_files_collision_suffix_increments(tmp_path) -> None:
    """IN-05: when both plane_00001.hdf5 and plane_00001_v02.hdf5 exist,
    the suffix increments to _v03 for that plane.

    Pre-creates both colliding files in tmp_path, chdir's there for the
    set_files call, then asserts the third plane gets _v03.
    """
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)
    saver = fs.frame_saver
    saver.filenames_list = []

    # Pre-create both the base and the _v02 collision files.
    (tmp_path / "stack_z_plane_00001.hdf5").write_bytes(b"")
    (tmp_path / "stack_z_plane_00001_v02.hdf5").write_bytes(b"")

    import os

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        saver.set_files(3, "stack", "z", 1, "dataset_")
    finally:
        os.chdir(cwd)

    assert saver.filenames_list == [
        "stack_z_plane_00001_v03.hdf5",
        "stack_z_plane_00002.hdf5",
        "stack_z_plane_00003.hdf5",
    ], (
        "set_files must increment the collision suffix past existing "
        "_v02 to _v03 when both base and _v02 exist; got: "
        + repr(saver.filenames_list)
    )


# ---------------------------------------------------------------------------
# Multi-channel per-channel HDF5 save separation (MCA-03 / D-05)
# ---------------------------------------------------------------------------


def test_set_files_multi_channel_wavelength_suffix(tmp_path) -> None:
    """MCA-03: set_files with wavelengths=[555, 640] builds
    self.filenames_lists as a list of 2 lists (one per channel), each
    length number_of_files, with _{wavelength}nm suffix and 5-digit
    zero-padded plane index. Wavelength values come from the caller
    (which reads them from the live ILaser instance).
    """
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)
    saver = fs.frame_saver
    saver.filenames_list = []
    saver.filenames_lists = []

    import os

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        saver.set_files(
            2, "scan", "stack", 1, "reconstructed_frame",
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
        assert fn.endswith("_555nm.hdf5"), (
            f"channel 0 filename must end with _555nm.hdf5: {fn}"
        )
    for fn in saver.filenames_lists[1]:
        assert fn.endswith("_640nm.hdf5"), (
            f"channel 1 filename must end with _640nm.hdf5: {fn}"
        )
    # Plane index is 1-based, 5-digit zero-padded
    assert "plane_00001" in saver.filenames_lists[0][0]
    assert "plane_00002" in saver.filenames_lists[0][1]


def test_set_files_single_channel_no_suffix(tmp_path) -> None:
    """MCA-03 back-compat: set_files with wavelengths=None keeps today's
    single self.filenames_list behavior — no _{wavelength}nm suffix.
    Byte-identical to the pre-multi-channel path.
    """
    import os
    import re

    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)
    saver = fs.frame_saver
    saver.filenames_list = []
    saver.filenames_lists = []

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        saver.set_files(
            2, "scan", "stack", 1, "reconstructed_frame",
            wavelengths=None,
        )
    finally:
        os.chdir(cwd)

    assert len(saver.filenames_list) == 2, (
        "single-channel filenames_list must have number_of_files entries"
    )
    for fn in saver.filenames_list:
        assert not re.search(r"_\d+nm\.hdf5$", fn), (
            f"single-channel filename must NOT have wavelength suffix: {fn}"
        )


def test_set_files_collision_avoidance_per_channel(tmp_path) -> None:
    """MCA-03: _vNN collision avoidance runs independently per channel —
    pre-create a file in channel 0's first plane; channel 0 gets _v02
    while channel 1 (no collision) stays unsuffixed.
    """
    import os

    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)
    saver = fs.frame_saver
    saver.filenames_list = []
    saver.filenames_lists = []

    # Pre-create channel 0's first file so it collides
    (tmp_path / "scan_stack_plane_00001_555nm.hdf5").write_bytes(b"")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        saver.set_files(
            1, "scan", "stack", 1, "reconstructed_frame",
            wavelengths=[555, 640],
        )
    finally:
        os.chdir(cwd)

    assert len(saver.filenames_lists) == 2
    # Channel 0 collides → gets _v02
    assert "_v02" in saver.filenames_lists[0][0], (
        f"channel 0 colliding filename must get _v02: {saver.filenames_lists[0][0]}"
    )
    # Channel 1 does not collide → no _vNN
    assert "_v" not in saver.filenames_lists[1][0], (
        f"channel 1 non-colliding filename must NOT get _vNN: {saver.filenames_lists[1][0]}"
    )


def _make_mock_h5py():
    """Build a Mock h5py.File replacement that records create_dataset calls.

    Returns (mock_file_class, written_files) where written_files is a dict
    mapping filename -> list of (dataset_name, data_array) tuples.
    """
    written_files: dict[str, list[tuple[str, np.ndarray]]] = {}

    class _MockDataset:
        def __init__(self, name: str, data: np.ndarray) -> None:
            self.name = name
            self.data = data
            self.attrs: dict = {}

    class _MockFile:
        def __init__(self, path: str, mode: str = "a") -> None:
            self.path = path
            self.attrs: dict = {}
            written_files.setdefault(path, [])

        def create_dataset(self, name: str, data=None, **kwargs):
            ds = _MockDataset(name, data)
            written_files[self.path].append((name, data))
            return ds

        def close(self) -> None:
            pass

    return _MockFile, written_files


def test_frame_saver_worker_branches_on_channel_tag(tmp_path) -> None:
    """MCA-03: frame_saver_worker branches on the channel tag from the
    dequeued (channel_idx, frame) tuple — frameA → filenames_lists[0][0],
    frameB → filenames_lists[1][0]. The single-consumer queue contract
    is preserved (one queue, one consume loop, no split).
    """
    from unittest.mock import patch

    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)
    saver = fs.frame_saver

    # Set up multi-channel filenames_lists (2 channels × 2 planes each)
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
    assert ch0_file in written_files, (
        f"channel 0 file must be opened: {ch0_file}"
    )
    assert ch1_file in written_files, (
        f"channel 1 file must be opened: {ch1_file}"
    )
    assert len(written_files[ch0_file]) == 1, (
        "channel 0 file must have exactly 1 dataset"
    )
    assert len(written_files[ch1_file]) == 1, (
        "channel 1 file must have exactly 1 dataset"
    )
    np.testing.assert_array_equal(written_files[ch0_file][0][1], frameA)
    np.testing.assert_array_equal(written_files[ch1_file][0][1], frameB)


def test_frame_saver_worker_single_channel_bare_ndarray(tmp_path) -> None:
    """Back-compat: a bare ndarray (no channel tag) dequeued by
    frame_saver_worker uses the existing self.filenames_list path —
    written to filenames_list[0]. The multi-channel filenames_lists
    is empty so the worker takes the single-channel branch.
    """
    from unittest.mock import patch

    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)
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
    np.testing.assert_array_equal(
        written_files[saver.filenames_list[0]][0][1], frame
    )


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


def test_save_single_image_multi_channel_writes_two_files(qtbot, request) -> None:
    """Multi-channel single mode: when both auto-laser checkboxes are
    checked, the Save button writes TWO wavelength-suffixed HDF5 files
    (one per channel). set_files is called with wavelengths=[wl1, wl2]
    read from the live ILaser instances, and enqueue_buffer is called
    twice with (0, frameA) and (1, frameB) tagged tuples — one per
    channel. The single-consumer queue contract is preserved (the two
    tagged frames go through the same enqueue_buffer → single queue).
    """
    from _helpers.controller_fixture import make_controller

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
        1, ctrl.save_filepath, "singleImage", 1, "reconstructed_frame",
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


def test_save_single_image_single_channel_unchanged(qtbot, request) -> None:
    """Back-compat: when only one auto-laser is checked (single-channel
    mode), updateUi_save_single_image keeps today's path — set_files
    called WITHOUT wavelengths, enqueue_buffer called once with the bare
    reconstructed_frame (no channel tag). Byte-identical to the
    pre-multi-channel behavior.
    """
    from _helpers.controller_fixture import make_controller

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

    # set_files called with no wavelengths kwarg (single-channel back-compat)
    ctrl._fs.set_files.assert_called_once_with(
        1, ctrl.save_filepath, "singleImage", 1, "reconstructed_frame",
    )
    _, kwargs = ctrl._fs.set_files.call_args
    assert "wavelengths" not in kwargs or kwargs["wavelengths"] is None, (
        f"single-channel set_files must not pass wavelengths; got kwargs={kwargs}"
    )
    ctrl._fs.enqueue_buffer.assert_called_once_with(frameA)
    ctrl._fs.start_saving.assert_called_once()
    ctrl._fs.stop_saving.assert_called_once()
