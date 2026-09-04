"""AcquisitionPanelWidget — per-panel widget/controller for acquisition modes.

Owns the preview/live/single/stack mode-button handlers and the mode-button
enable/disable helpers. The QThread spawn pattern for each mode
(PreviewWorker/LiveWorker/SingleWorker/StackWorker on moveToThread) lives here.
"""

from __future__ import annotations

import contextlib
import logging
import typing

import shiboken6
from PySide6.QtCore import SIGNAL, QThread, Slot
from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget

from lightsheet.gui.panels.ui_acquisition_panel import Ui_AcquisitionPanel
from lightsheet.gui.widgets.field_spec import FIELD_SPECS
from lightsheet.gui.workers import LiveWorker, PreviewWorker, SingleWorker, StackWorker

if typing.TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


class AcquisitionPanelWidget(QWidget):
    """Acquisition modes panel -- owns the four mode-button handlers and
    the mode-button enable/disable helpers."""

    def __init__(self, shell: Controller_MainWindow) -> None:
        super().__init__()
        self._shell = shell
        self.ui = Ui_AcquisitionPanel()
        self.ui.setupUi(self)
        # Apply the declarative FieldSpec policy table to every promoted
        # FieldSpecSpinBox by objectName.
        for obj_name, spec in FIELD_SPECS.items():
            w = getattr(self.ui, obj_name, None)
            if w is not None and hasattr(w, "applySpec"):
                w.applySpec(spec)

    def updateUi_modes_buttons(self, buttons_to_enable: list[QPushButton]) -> None:
        """Update mode buttons: disable buttons except those specified enabled."""
        aquisition_buttons = [
            self.ui.pushButton_acqStartPreviewMode,
            self.ui.pushButton_acqStartLiveMode,
            self._shell.stack_panel.ui.pushButton_acqStartStackMode,
            self.ui.pushButton_acqGetSingleImage,
            self._shell.save_panel.ui.pushButton_saveCurrentImage,
            self._shell.calibration_panel.ui.pushButton_calCameraComputeFocus,
            self._shell.calibration_panel.ui.pushButton_calCameraShowInterpolation,
            self._shell.calibration_panel.ui.pushButton_calEtlShowInterpolation,
        ]
        for button in aquisition_buttons:
            if button in buttons_to_enable:
                button.setEnabled(True)
            else:
                button.setEnabled(False)

        # Disable the format + save-option radios during an active
        # acquisition so a format/option change mid-acquisition is
        # impossible (the save worker reads save_format at acquisition start).
        save_ui = self._shell.save_panel.ui
        format_and_option_radios = [
            save_ui.radioButton_saveFormat_hdf5,
            save_ui.radioButton_saveFormat_zarr,
            save_ui.radioButton_saveFormat_both,
            save_ui.radioButton_saveStitch,
            save_ui.radioButton_saveStitchBlend,
            save_ui.radioButton_saveAllCrop,
            save_ui.radioButton_saveAllFull,
        ]
        # Re-enable radios only when idle (full default button set present).
        idle = all(
            b in buttons_to_enable
            for b in [
                self.ui.pushButton_acqStartPreviewMode,
                self.ui.pushButton_acqStartLiveMode,
                self._shell.stack_panel.ui.pushButton_acqStartStackMode,
                self.ui.pushButton_acqGetSingleImage,
            ]
        )
        for radio in format_and_option_radios:
            radio.setEnabled(idle)

    def updateUi_enable_buttons(self, buttons_to_enable: list[QPushButton]) -> None:
        """Enable buttons"""
        for button in buttons_to_enable:
            button.setEnabled(True)

    def updateUi_disable_buttons(self, buttons_to_disable: list[QPushButton]) -> None:
        """Disable buttons"""
        for button in buttons_to_disable:
            button.setEnabled(False)

    def updateUi_preview_mode_button(self) -> None:
        """Start or stop preview mode, depending on the button status"""
        if self._shell.preview_mode_started:
            self._shell.preview_mode_started = False
            self.ui.pushButton_acqStartPreviewMode.setText("Start Preview Mode")
            # Disable until the worker finishes to prevent a restart race
            # that would spawn a second worker accessing the camera concurrently.
            self.ui.pushButton_acqStartPreviewMode.setEnabled(False)
        else:
            self._shell.close_modes()
            self._shell.preview_mode_started = True
            self.ui.pushButton_acqStartPreviewMode.setText("Stop Preview Mode")

            # updating ui before starting preview mode thread
            self.updateUi_modes_buttons([self.ui.pushButton_acqStartPreviewMode])
            self._shell.updateUi_message_printer("->Preview mode started")
            self._shell.ui.statusBar_label.setText("Current Acquisition Mode: Preview ")
            self._shell.ui.statusBar_progress.setValue(100)
            self._shell.ui.statusBar_progress.show()
            self._shell._update_mode_badge("PREVIEW")

            # Sample the auto-laser checkboxes on the GUI thread before
            # spawning the worker.
            self._shell._cache_auto_laser_flags()
            assert self._shell._hw is not None

            # Spawn the preview worker on a QThread (moveToThread pattern).
            self._shell._preview_worker = PreviewWorker(
                self._shell._bundle,
                self._shell._hw,
                self._shell,
            )
            self._shell._preview_thread = QThread()
            self._shell._preview_worker.moveToThread(self._shell._preview_thread)
            self._shell._preview_thread.started.connect(self._shell._preview_worker.run)
            self._shell._preview_worker.finished.connect(
                self.updateUi_post_preview_mode
            )
            self._shell._preview_worker.finished.connect(
                self._shell._preview_thread.quit
            )
            self._shell._preview_thread.finished.connect(
                self._shell._preview_worker.deleteLater
            )
            self._shell._preview_thread.start()

    @Slot()
    def updateUi_post_preview_mode(self) -> None:
        self.updateUi_modes_buttons(self._shell.default_buttons)
        self._shell.updateUi_message_printer("->Preview mode stopped")
        self._shell.ui.statusBar_label.setText("")
        self._shell.ui.statusBar_progress.setValue(0)
        self._shell.ui.statusBar_progress.hide()
        self._shell._update_mode_badge("IDLE")

    def updateUi_live_mode_button(self) -> None:
        """Start or stop live mode, depending on the button status"""
        if self._shell.live_mode_started:
            self._shell.live_mode_started = False
            self.ui.pushButton_acqStartLiveMode.setText("Start Live Mode")
            # Disable until the worker finishes to prevent a restart race
            # that would spawn a second worker accessing the camera concurrently.
            self.ui.pushButton_acqStartLiveMode.setEnabled(False)
        else:
            self._shell.close_modes()
            self._shell.live_mode_started = True
            self.ui.pushButton_acqStartLiveMode.setText("Stop Live Mode")
            # updating ui before starting live mode thread
            self.updateUi_modes_buttons([self.ui.pushButton_acqStartLiveMode])
            self._shell.updateUi_message_printer("->Live mode started")
            self._shell.ui.statusBar_label.setText("Current Acquisition Mode: Live ")
            self._shell.ui.statusBar_progress.setValue(100)
            self._shell.ui.statusBar_progress.show()
            self._shell._update_mode_badge("LIVE")

            # Sample the auto-laser checkboxes on the GUI thread before
            # spawning the worker.
            self._shell._cache_auto_laser_flags()
            assert self._shell._hw is not None

            # Spawn the live worker on a QThread (moveToThread pattern).
            self._shell._live_worker = LiveWorker(
                self._shell._bundle,
                self._shell._hw,
                self._shell,
            )
            self._shell._live_thread = QThread()
            self._shell._live_worker.moveToThread(self._shell._live_thread)
            self._shell._live_thread.started.connect(self._shell._live_worker.run)
            self._shell._live_worker.finished.connect(self.updateUi_post_live_mode)
            self._shell._live_worker.finished.connect(self._shell._live_thread.quit)
            self._shell._live_thread.finished.connect(
                self._shell._live_worker.deleteLater
            )
            self._shell._live_thread.start()

    @Slot()
    def updateUi_post_live_mode(self) -> None:
        self.updateUi_modes_buttons(self._shell.default_buttons)
        self._shell.updateUi_message_printer("->Live mode stopped")
        self._shell.ui.statusBar_label.setText("")
        self._shell.ui.statusBar_progress.setValue(0)
        self._shell.ui.statusBar_progress.hide()
        self._shell._update_mode_badge("IDLE")

    def updateUi_single_mode_button(self) -> None:
        """Acquire a single image"""
        if not self._shell.single_mode_started:
            self._shell.close_modes()

            self._shell.single_mode_started = True
            self.ui.pushButton_acqGetSingleImage.setText("Acquiring...")
            self.updateUi_modes_buttons([self.ui.pushButton_acqGetSingleImage])
            self._shell.updateUi_message_printer("->Getting single image")
            self._shell._update_mode_badge("SINGLE")

            # Sample the auto-laser checkboxes on the GUI thread before
            # spawning the worker.
            self._shell._cache_auto_laser_flags()

            # Multi-channel flag pre-sampled on the GUI thread (no
            # cross-thread widget reads from workers). When both auto-laser
            # checkboxes are checked, SingleWorker.run executes the
            # per-channel cycle; otherwise the single-channel path runs.
            multi_channel = self._shell._auto_laser1 and self._shell._auto_laser2

            # Pre-sample the save-option widgets on the GUI thread before
            # constructing the worker (no cross-thread widget reads from workers).
            save_desc = str(self._shell.save_panel.ui.lineEdit_saveDescription.text())
            save_blend = (
                self._shell.save_panel.ui.radioButton_saveStitchBlend.isChecked()
            )
            assert self._shell._hw is not None

            # Spawn the single-image worker on a QThread (moveToThread pattern).
            self._shell._single_worker = SingleWorker(
                self._shell._bundle,
                self._shell._hw,
                self._shell,
                save_desc,
                save_blend,
                multi_channel,
            )
            self._shell._single_thread = QThread()
            self._shell._single_worker.moveToThread(self._shell._single_thread)
            self._shell._single_thread.started.connect(self._shell._single_worker.run)
            self._shell._single_worker.finished.connect(self.updateUi_post_single_mode)
            self._shell._single_worker.finished.connect(self._shell._single_thread.quit)
            self._shell._single_thread.finished.connect(
                self._shell._single_worker.deleteLater
            )
            self._shell._single_thread.start()

    @Slot()
    def updateUi_post_single_mode(self) -> None:
        self._shell.single_mode_started = False
        self.ui.pushButton_acqGetSingleImage.setText("Get Single Image")
        self._shell._update_mode_badge("IDLE")
        # Only arm the save button when this run actually produced a frame
        # (a failed run leaves buffer None, so the save button stays disabled).
        save_btn = self._shell.save_panel.ui.pushButton_saveCurrentImage
        if self._shell.buffer is not None:
            if save_btn not in self._shell.default_buttons:
                self._shell.default_buttons.append(save_btn)
        elif save_btn in self._shell.default_buttons:
            self._shell.default_buttons.remove(save_btn)
        self.updateUi_modes_buttons(self._shell.default_buttons)

    def updateUi_stack_mode_button(self) -> None:
        """Start or stop stack mode, depending on the button status"""
        if self._shell.stack_mode_started:
            self._shell.stack_mode_started = False
            self._shell.focus_mode_started = False
            # Disable until the worker finishes to prevent a restart race
            # that would spawn a second worker accessing the camera concurrently.
            self._shell.stack_panel.ui.pushButton_acqStartStackMode.setEnabled(False)
        else:
            self._shell.close_modes()
            # Making sure the limits of the volume are set
            step_spin = self._shell.stack_panel.ui.doubleSpinBox_acqPlaneStepSize
            if (
                (not self._shell.stack_first_plane_set)
                or (not self._shell.stack_last_plane_set)
                or (step_spin.value() == 0)
            ):
                msg = "Set starting and ending points and a non-zero plane step"
                self._shell.sig_message.emit(msg)
                self._shell.sig_beep.emit()
                QMessageBox.warning(
                    self._shell,
                    "Stack Acquisition Warning",
                    msg,
                    QMessageBox.StandardButton.Ok,
                    QMessageBox.StandardButton.Ok,
                )
            else:
                # Set stack step sign (taking into account the direction of acquisition)
                if self._shell.stack_starting_plane > self._shell.stack_ending_plane:  # ty: ignore[unsupported-operator]
                    self._shell.stack_step = -1 * step_spin.value()  # ty: ignore[invalid-assignment]
                else:
                    self._shell.stack_step = step_spin.value()  # ty: ignore[invalid-assignment]

                # Check that filename is valid and saving is allowed
                self._shell.save_panel.validate_file_name()

                nosave_answer = QMessageBox.StandardButton.No
                if not self._shell.saving_allowed:
                    self._shell.sig_beep.emit()
                    nosave_answer = QMessageBox.question(
                        self._shell,
                        "Stack Acquisition Question",
                        "Make stack acquisition without saving ?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes,
                    )

                if (
                    self._shell.saving_allowed
                    or nosave_answer == QMessageBox.StandardButton.Yes
                ):
                    self._shell.stack_panel.ui.pushButton_acqStartStackMode.setText(
                        "Stop Stack Mode"
                    )
                    ui: typing.Any = self._shell.ui
                    ui.statusBar_label.setText("Current Acquisition Mode: Stack ")
                    progress = ui.statusBar_progress
                    progress.setValue(0)
                    progress.show()
                    self._shell.stack_mode_started = True

                    # Modes disabling while stack acquisition
                    self.updateUi_modes_buttons(
                        [self._shell.stack_panel.ui.pushButton_acqStartStackMode]
                    )
                    self._shell.motor_panel.updateUi_motor_buttons()
                    self._shell.updateUi_message_printer(
                        "->Stack mode started -- Number of frames to save: "
                        + str(int(self._shell.number_of_planes))
                    )
                    self._shell._update_mode_badge(
                        "STACK",
                        "RUNNING",
                        plane=1,
                        total=int(self._shell.number_of_planes),
                    )

                    # Sample the auto-laser checkboxes on the GUI thread
                    # before spawning the worker.
                    self._shell._cache_auto_laser_flags()

                    # Spawn the stack worker (shared with the queue loop).
                    self._spawn_stack_worker()

    def _spawn_stack_worker(self) -> StackWorker | None:
        """Spawn the stack worker on its QThread (moveToThread pattern),
        wire its finished signal to the post-stack UI cleanup, and start it.
        Shared by the single-stack Start button and the Acquisition Table
        queue loop. Pre-samples the auto-laser flags + save-option widgets
        on the GUI thread so the worker thread never reads ui.*.

        Returns the spawned worker, or ``None`` if the previous stack thread
        did not stop and a new worker cannot be started safely.
        """
        # Disable the adaptive-autofocus controls and show the per-plane
        # progress bar when adaptive focus is active.
        self._shell.stack_panel.set_autofocus_running(True)

        # Reuse the same QThread across queue rows instead of constructing
        # a new one per row — constructing + destroying a QThread C++
        # object while the previous worker's deleteLater is still pending
        # races the C++ destructors and segfaults.
        prev_thread = getattr(self._shell, "_stack_thread", None)
        if prev_thread is not None and prev_thread.isRunning():
            prev_thread.quit()
            if not prev_thread.wait(5000):
                # The previous worker is still blocked in a camera/motor call.
                # Do not start a second worker while the previous one may still
                # own hardware; abort the start and let the UI/queue recover.
                logger.error(
                    "Previous stack worker thread did not finish within 5 s; "
                    "not starting a new stack worker."
                )
                self._shell.sig_message.emit(
                    "Stack start failed: previous stack thread is still running."
                )
                self._shell.sig_beep.emit()
                self.updateUi_post_stack_mode()
                return None

        # If the thread was never created or was destroyed, construct a
        # fresh one; otherwise reuse it and fully disconnect the previous
        # worker's stale finished/deleteLater connections so they cannot
        # fire after the new worker starts.
        if prev_thread is None:
            self._shell._stack_thread = QThread()
        else:
            prev_worker = getattr(self._shell, "_stack_worker", None)
            if prev_worker is not None and shiboken6.isValid(prev_worker):
                with contextlib.suppress(RuntimeError, TypeError):
                    prev_worker.finished.disconnect(prev_thread.quit)
                with contextlib.suppress(RuntimeError, TypeError):
                    prev_worker.finished.disconnect(self.updateUi_post_stack_mode)
                if shiboken6.isValid(prev_thread):
                    with contextlib.suppress(RuntimeError, TypeError):
                        prev_thread.finished.disconnect(prev_worker.deleteLater)
            self._shell._stack_thread = prev_thread

        # Pre-sample the save-option widgets on the GUI thread before
        # constructing the worker (no cross-thread widget reads from workers).
        save_desc = str(self._shell.save_panel.ui.lineEdit_saveDescription.text())
        save_blend = self._shell.save_panel.ui.radioButton_saveStitchBlend.isChecked()
        save_all_crop = self._shell.save_panel.ui.radioButton_saveAllCrop.isChecked()
        save_all_full = self._shell.save_panel.ui.radioButton_saveAllFull.isChecked()
        # Multi-channel flag pre-sampled on the GUI thread (no
        # cross-thread widget reads from workers). When both auto-laser
        # checkboxes are checked, StackWorker.run executes the per-plane
        # sequential cycle; otherwise the single-channel path runs.
        multi_channel = self._shell._auto_laser1 and self._shell._auto_laser2

        # Disconnect the previous worker's started→run connection only.
        # finished.disconnect() is intentionally avoided — it can deadlock
        # under PySide6 if the worker QThread is stuck between run() and
        # exec(). The worker is deleted via the thread's finished signal,
        # so stale finished→thread.quit/updateUi connections become no-ops.

        # Spawn the stack worker on the (reused) QThread (moveToThread
        # pattern). Pre-sample the adaptive config on the GUI thread so
        # the worker thread never reads ui.*. build_adaptive_config
        # returns a frozen AdaptiveConfig (or None when the toggle is
        # unchecked or the fixed-fallback latch is set).
        adaptive_cfg = self._shell.stack_panel.build_adaptive_config()
        focus_cfg = self._shell.stack_panel.build_focus_config()
        focus_curve = self._shell.stack_panel.build_focus_curve()
        autofocus_cfg = self._shell.stack_panel.build_autofocus_config()
        autofocus_curve = (
            self._shell.stack_panel.build_focus_curve()
            if autofocus_cfg is not None and autofocus_cfg.use_curve_seed
            else None
        )
        assert self._shell._hw is not None

        self._shell._stack_worker = StackWorker(
            self._shell._bundle,
            self._shell._hw,
            self._shell,
            save_desc,
            save_blend,
            save_all_crop,
            save_all_full,
            multi_channel,
            adaptive_cfg=adaptive_cfg,
            focus_cfg=focus_cfg,
            focus_curve=focus_curve,
            autofocus_cfg=autofocus_cfg,
            autofocus_curve=autofocus_curve,
        )
        self._shell._stack_worker.moveToThread(self._shell._stack_thread)
        # Connect the per-plane adaptive trajectory signal to the shell's
        # GUI-thread slot. The connection is queued so the worker never
        # calls pyqtgraph directly. Disconnect any prior connection from a
        # previous queue row first so the slot does not fire twice. Only
        # disconnect if there is an existing connection — disconnecting
        # with none emits a libpyside RuntimeWarning that masks real
        # signal-wiring bugs.
        with contextlib.suppress(TypeError, RuntimeError):
            if (
                self._shell._stack_worker.receivers(
                    SIGNAL(
                        "sig_adaptive_trajectory(int,double,double,double,double,QString,bool,bool)"
                    )
                )
                > 0
            ):
                self._shell._stack_worker.sig_adaptive_trajectory.disconnect()
        self._shell._stack_worker.sig_adaptive_trajectory.connect(
            self._shell._on_adaptive_trajectory
        )
        # Connect the per-block focus trajectory signal to the shell's
        # GUI-thread slot. Queued connection so the worker never touches
        # pyqtgraph. Disconnect any prior connection first.
        with contextlib.suppress(TypeError, RuntimeError):
            if (
                self._shell._stack_worker.receivers(
                    SIGNAL("sig_focus_trajectory(int,double,double,double,double)")
                )
                > 0
            ):
                self._shell._stack_worker.sig_focus_trajectory.disconnect()
        self._shell._stack_worker.sig_focus_trajectory.connect(
            self._shell._on_focus_trajectory
        )
        # Connect the per-plane autofocus status signal to the stack panel's
        # GUI-thread slot. Queued connection so the worker never touches
        # Qt widgets. Disconnect any prior connection first.
        with contextlib.suppress(TypeError, RuntimeError):
            if (
                self._shell._stack_worker.receivers(
                    SIGNAL("sig_autofocus_status(int,int,double,double,double,QString)")
                )
                > 0
            ):
                self._shell._stack_worker.sig_autofocus_status.disconnect()
        self._shell._stack_worker.sig_autofocus_status.connect(
            self._shell.stack_panel._on_autofocus_status
        )
        # When reusing the thread (2nd+ queue row), disconnect the prior
        # started→run so the reused thread's started only invokes this
        # row's run. Skip on the first spawn — no prior connection exists
        # and disconnecting with none emits a libpyside RuntimeWarning
        # that masks real signal-wiring bugs.
        if prev_thread is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                if self._shell._stack_thread.receivers(SIGNAL("started()")) > 0:
                    self._shell._stack_thread.started.disconnect()
        self._shell._stack_thread.started.connect(self._shell._stack_worker.run)
        self._shell._stack_worker.finished.connect(self.updateUi_post_stack_mode)
        self._shell._stack_worker.finished.connect(self._shell._stack_thread.quit)
        # thread.finished→worker.deleteLater: this fires each row (the
        # thread quits per row), reaping that row's worker. We do NOT
        # disconnect the previous connection while the thread may still be
        # running — PySide6's disconnect can deadlock against a worker
        # QThread stuck between run() and exec(). Calling deleteLater on an
        # already-deleted worker is a no-op, so an accumulating connection
        # list is safe and avoids the race.
        self._shell._stack_thread.finished.connect(
            self._shell._stack_worker.deleteLater
        )
        # Reset the adaptive trajectory plot at the start of each run so
        # per-plane samples do not accumulate across runs (historical
        # data from a previous run is cleared when the operator starts a
        # new stack). The widget's curves are reused (created once);
        # reset() clears their data and updates the target band. Always
        # clear the data; only show the plot if the dock is currently
        # visible so a hidden dock does not spin up the plot. The
        # per-laser power curves are shown only for lasers under
        # automatic control — plotting a non-auto laser's computed power
        # would be misleading (the loop does not drive it).
        if adaptive_cfg is not None:
            self._shell.adaptiveTrajectoryWidget.reset(
                target_band_lo=adaptive_cfg.target_band_lo,
                target_band_hi=adaptive_cfg.target_band_hi,
            )
        else:
            self._shell.adaptiveTrajectoryWidget.reset()
        self._shell.adaptiveTrajectoryWidget.set_power_visible(
            bool(self._shell._auto_laser1),
            bool(self._shell._auto_laser2),
        )
        # If the dock is hidden, hide the plot again (reset() shows it).
        # The data is cleared and ready; the plot will be shown when the
        # operator reopens the dock via the rail button.
        if not self._shell.dockWidget_adaptiveTrajectory.isVisible():
            self._shell.adaptiveTrajectoryWidget.plotWidget_adaptiveTrajectory.hide()
            if self._shell.adaptiveTrajectoryWidget._legend is not None:
                self._shell.adaptiveTrajectoryWidget._legend.hide()

        # Reset the focus trajectory plot at the start of each run so
        # per-block samples do not accumulate across runs. The X-axis is
        # fixed to "Block" in this phase; the "Stage position (mm)" option
        # has been removed from the UI.
        self._shell.focusTrajectoryWidget.reset()
        if not self._shell.dockWidget_focusTrajectory.isVisible():
            self._shell.focusTrajectoryWidget.plotWidget_focusTrajectory.hide()
            if self._shell.focusTrajectoryWidget._legend is not None:
                self._shell.focusTrajectoryWidget._legend.hide()

        # The mode badge switches to FOCUS RUNNING for the duration of the
        # stack when either legacy focus compensation or per-plane autofocus
        # is enabled.
        self._shell.focus_mode_started = (focus_cfg is not None) or (
            autofocus_cfg is not None
        )

        self._shell._stack_thread.start()
        return self._shell._stack_worker

    @Slot()
    def updateUi_post_stack_mode(self) -> None:
        """Enabling modes after stack mode"""
        queue_active = getattr(
            self._shell.stack_panel.table_manager, "_queue_active", False
        )
        if not queue_active:
            self._shell.stack_panel.ui.pushButton_acqStartStackMode.setText(
                "Start Stack Mode"
            )
            self.updateUi_modes_buttons(self._shell.default_buttons)
            self._shell.motor_panel.updateUi_motor_buttons(disable_button=False)

        # Re-enable the adaptive-autofocus controls and hide the progress bar
        # now that the stack has finished or aborted.
        self._shell.stack_panel.set_autofocus_running(False)

        self._shell.stack_mode_started = False
        self._shell.focus_mode_started = False
        self._shell.updateUi_message_printer("->Stack Mode Acquisition Done")
        self._shell.ui.statusBar_label.setText("")
        self._shell.ui.statusBar_progress.hide()
        self._shell._update_mode_badge("IDLE")
