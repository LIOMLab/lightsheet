"""FrameSaverController extraction tests (Phase 5 god-object split).

``FrameSaverController`` is a plain-Python collaborator that owns the
``FrameSaver`` + ``FrameViewer`` QObject instances and routes the
shell's save/enqueue calls through to them. The QObjects themselves
(``FrameSaver`` / ``FrameViewer``) stay defined in
``lightsheet/gui/controller.py`` per PATTERNS.md — this collaborator just
owns/routes to them. The shell delegates through ``self._fs``.

``Controller_MainWindow`` cannot be instantiated on this Mac (no PyQt5
display), so the tests construct ``FrameSaverController`` directly with a
Mock stand-in shell and assert on the wrapped instances + the routed
calls. The ``FrameSaver`` / ``FrameViewer`` classes ARE constructible on
Mac (they only need a QObject parent + numpy for the default frame) —
PyQt5 is installed in the dev venv, and ``conftest.py`` stubs the hardware
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

pytest.importorskip("PyQt5")  # FrameSaver/FrameViewer are QObjects

from lightsheet.gui.controller import FrameSaver, FrameViewer
from lightsheet.gui.frame_saver_controller import FrameSaverController
from lightsheet.hal import DeviceBundle, MockCamera, MockETLs, MockLaser, MockMotors, MockSigGen


def _make_bundle() -> DeviceBundle:
    """Build a demo DeviceBundle with the camera dimensions
    FrameSaverController reads (bundle.camera.ysize / xsize)."""
    camera = MockCamera(verbose=True)
    siggen = MockSigGen(camera)
    motors = MockMotors()
    lasers = (
        MockLaser(wavelength=555, max_power_mw=300.0, label="Laser 1 (555 nm)"),
        MockLaser(wavelength=640, max_power_mw=150.0, label="Laser 2 (640 nm)"),
    )
    etls = MockETLs()
    return DeviceBundle(camera=camera, siggen=siggen, motors=motors, etls=etls, lasers=lasers)


def _make_shell() -> Mock:
    """Build a Mock stand-in shell exposing the attributes
    FrameSaverController.__init__ touches: ``updateUi_message_printer``
    (the sig_status_message slot) and a ``sig_message`` Mock so any
    incidental emit is a no-op."""
    shell = Mock()
    shell.updateUi_message_printer = Mock()
    shell.sig_message = Mock()
    return shell


def test_init_creates_frame_saver_parented_to_shell() -> None:
    """FrameSaverController(bundle, shell) constructs a FrameSaver
    parented to shell (the QObject parent)."""
    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)
    assert isinstance(fs.frame_saver, FrameSaver), (
        "FrameSaverController must own a FrameSaver instance"
    )
    # FrameSaver.__init__ calls QObject.__init__(self, parent) — the
    # parent is the shell. PyQt5 stores the parent on .parent().
    assert fs.frame_saver.parent() is shell, (
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
    assert fs.frame_viewer.parent() is shell, (
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

    Asserted by inspecting the Qt connection list on the signal: the
    shell.updateUi_message_printer callable appears as a receiver.
    """
    from PyQt5.QtCore import QMetaObject

    bundle = _make_bundle()
    shell = _make_shell()
    fs = FrameSaverController(bundle, shell)
    # Gather the connected receivers via Qt's meta-object introspection.
    # pyqtSignal does not expose a public receiver list, so we use
    # QMetaObject.connections — the receiver is the shell's bound method.
    meta = fs.frame_saver.metaObject()
    # Find the sig_status_message signal index by name.
    sig_idx = meta.indexOfSignal("sig_status_message(QString)")
    assert sig_idx >= 0, "sig_status_message signal must exist on FrameSaver"
    # The connection exists if the slot is in the connection list. PyQt5
    # does not expose a public receiver enumeration, so we assert
    # behaviorally: emitting the signal must call the shell slot.
    fs.frame_saver.sig_status_message.emit("test message")
    shell.updateUi_message_printer.assert_called_once_with("test message")


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
    fs.frame_saver.set_files.assert_called_once_with(1, "name", "singleImage", 1, "ETLscan")

    fs.enqueue_buffer(np.zeros((1, 1), dtype=np.uint16))
    fs.frame_saver.enqueue_buffer.assert_called_once()

    fs.start_saving()
    fs.frame_saver.start_saving.assert_called_once()

    fs.stop_saving()
    fs.frame_saver.stop_saving.assert_called_once()
