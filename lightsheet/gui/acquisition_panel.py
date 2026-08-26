"""AcquisitionPanelWidget — per-panel widget/controller for acquisition modes.

Owns the acquisition updateUi_* slots grouped by concern (D-01 gui
modularization): mode button enable/disable, preview/live/single/stack mode
button handlers, and post-mode UI refresh. The QThread spawn pattern for each
mode (PreviewWorker/LiveWorker/SingleWorker/StackWorker on moveToThread) lives
here, delegating to ``self._shell._acq`` / ``self._shell._hw`` / ``self._shell._fs``.

The mode-button enable/disable helpers (``updateUi_modes_buttons`` etc.) touch
buttons across multiple panels (acquisition, save, calibration) — they read
them via ``self._shell.ui.<widget>``.
"""

from __future__ import annotations

import typing

from PySide6.QtCore import QThread, Slot
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QWidget

from lightsheet.gui.ui_acquisition_panel import Ui_AcquisitionPanel
from lightsheet.gui.workers import LiveWorker, PreviewWorker, SingleWorker, StackWorker

if typing.TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow


class AcquisitionPanelWidget(QWidget):
    """Acquisition modes panel — owns the four mode-button handlers
    (preview/live/single/stack) and the mode-button enable/disable helpers."""

    def __init__(self, shell: Controller_MainWindow) -> None:
        super().__init__()
        self._shell = shell
        self.ui = Ui_AcquisitionPanel()
        self.ui.setupUi(self)

    def updateUi_modes_buttons(self, buttons_to_enable: list[QPushButton]) -> None:
        """Update mode buttons status : disable buttons, except for those specified to be enabled"""  # noqa: E501
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
            # Disable the button until the worker's finished signal fires
            # (updateUi_post_preview_mode re-enables all default buttons).
            # Without this, the user can click "Start" before the worker
            # exits, spawning a second worker while the first is still
            # running — both would access the camera concurrently.
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
            # spawning the worker (AGENTS.md §11).
            self._shell._cache_auto_laser_flags()

            # Spawn the preview worker on a QThread (moveToThread pattern).
            self._shell._preview_worker = PreviewWorker(self._shell._bundle, self._shell._hw, self._shell)  # noqa: E501
            self._shell._preview_thread = QThread()
            self._shell._preview_worker.moveToThread(self._shell._preview_thread)
            self._shell._preview_thread.started.connect(self._shell._preview_worker.run)
            self._shell._preview_worker.finished.connect(self.updateUi_post_preview_mode)
            self._shell._preview_worker.finished.connect(self._shell._preview_thread.quit)
            self._shell._preview_thread.finished.connect(self._shell._preview_worker.deleteLater)
            self._shell._preview_thread.start()

    @Slot()
    def updateUi_post_preview_mode(self) -> None:
        # updating ui after preview mode thread has completed
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
            # Disable until the worker finishes (updateUi_post_live_mode
            # re-enables all default buttons). Prevents a restart race
            # that would spawn a second worker accessing the camera
            # concurrently with the still-running first worker.
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
            # spawning the worker (AGENTS.md §11).
            self._shell._cache_auto_laser_flags()

            # Spawn the live worker on a QThread (moveToThread pattern).
            self._shell._live_worker = LiveWorker(self._shell._bundle, self._shell._hw, self._shell)  # noqa: E501
            self._shell._live_thread = QThread()
            self._shell._live_worker.moveToThread(self._shell._live_thread)
            self._shell._live_thread.started.connect(self._shell._live_worker.run)
            self._shell._live_worker.finished.connect(self.updateUi_post_live_mode)
            self._shell._live_worker.finished.connect(self._shell._live_thread.quit)
            self._shell._live_thread.finished.connect(self._shell._live_worker.deleteLater)
            self._shell._live_thread.start()

    @Slot()
    def updateUi_post_live_mode(self) -> None:
        # updating ui after live mode thread has completed
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
            # Disabling modes while single frame acquisition
            self.ui.pushButton_acqGetSingleImage.setText("Acquiring...")
            self.updateUi_modes_buttons([self.ui.pushButton_acqGetSingleImage])
            self._shell.updateUi_message_printer("->Getting single image")
            self._shell._update_mode_badge("SINGLE")

            # Sample the auto-laser checkboxes on the GUI thread before
            # spawning the worker (AGENTS.md §11).
            self._shell._cache_auto_laser_flags()

            # B-03: pre-sample the save-option widgets on the GUI thread
            # BEFORE constructing the worker (AGENTS.md §11).
            save_desc = str(self._shell.save_panel.ui.lineEdit_saveDescription.text())
            save_blend = self._shell.save_panel.ui.checkBox_saveStitchBlend.isChecked()

            # Spawn the single-image worker on a QThread (moveToThread pattern).
            self._shell._single_worker = SingleWorker(self._shell._bundle, self._shell._hw, self._shell, save_desc, save_blend)  # noqa: E501
            self._shell._single_thread = QThread()
            self._shell._single_worker.moveToThread(self._shell._single_thread)
            self._shell._single_thread.started.connect(self._shell._single_worker.run)
            self._shell._single_worker.finished.connect(self.updateUi_post_single_mode)
            self._shell._single_worker.finished.connect(self._shell._single_thread.quit)
            self._shell._single_thread.finished.connect(self._shell._single_worker.deleteLater)
            self._shell._single_thread.start()

    @Slot()
    def updateUi_post_single_mode(self) -> None:
        # Re-enabling modes after single frame acquisition
        self._shell.single_mode_started = False
        self.ui.pushButton_acqGetSingleImage.setText("Get Single Image")
        self._shell._update_mode_badge("IDLE")
        if self._shell.save_panel.ui.pushButton_saveCurrentImage not in self._shell.default_buttons:  # noqa: E501
            self._shell.default_buttons.append(self._shell.save_panel.ui.pushButton_saveCurrentImage)
        self.updateUi_modes_buttons(self._shell.default_buttons)

    def updateUi_stack_mode_button(self) -> None:
        """Start or stop stack mode, depending on the button status"""
        if self._shell.stack_mode_started:
            self._shell.stack_mode_started = False
            # Disable until the worker finishes (updateUi_post_stack_mode
            # re-enables all default buttons). Prevents a restart race
            # that would spawn a second worker accessing the camera
            # concurrently with the still-running first worker.
            self._shell.stack_panel.ui.pushButton_acqStartStackMode.setEnabled(False)
        else:
            self._shell.close_modes()
            # Making sure the limits of the volume are set
            if (
                (not self._shell.stack_first_plane_set)
                or (not self._shell.stack_last_plane_set)
                or (self._shell.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.value() == 0)
            ):
                self._shell.sig_message.emit(
                    "Set starting and ending points and select a non-zero plane step value"  # noqa: E501
                )
                self._shell.sig_beep.emit()
                QMessageBox.warning(
                    self._shell,
                    "Stack Acquisition Warning",
                    "Set starting and ending points and select a non-zero plane step value",  # noqa: E501
                    QMessageBox.StandardButton.Ok,
                    QMessageBox.StandardButton.Ok,
                )
            else:
                # Setting stack step size sign (taking into account the direction of acquisition)  # noqa: E501
                if self._shell.stack_starting_plane > self._shell.stack_ending_plane:
                    self._shell.stack_step = (
                        -1 * self._shell.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.value()
                    )
                else:
                    self._shell.stack_step = self._shell.stack_panel.ui.doubleSpinBox_acqPlaneStepSize.value()  # noqa: E501

                # Check that filename is valid and saving is allowed
                self._shell.save_panel.validate_file_name()

                nosave_answer = False
                if not self._shell.saving_allowed:
                    self._shell.sig_beep.emit()
                    nosave_answer = QMessageBox.question(
                        self._shell,
                        "Stack Acquisition Question",
                        "Make stack acquisition without saving ?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes,
                    )

                if self._shell.saving_allowed or nosave_answer:
                    self._shell.stack_panel.ui.pushButton_acqStartStackMode.setText("Stop Stack Mode")  # noqa: E501
                    self._shell.ui.statusBar_label.setText("Current Acquisition Mode: Stack ")  # noqa: E501
                    self._shell.ui.statusBar_progress.setValue(0)  # To reset progress bar  # noqa: E501
                    self._shell.ui.statusBar_progress.show()
                    self._shell.stack_mode_started = True

                    # Modes disabling while stack acquisition
                    self.updateUi_modes_buttons([self._shell.stack_panel.ui.pushButton_acqStartStackMode])
                    self._shell.motor_panel.updateUi_motor_buttons()
                    self._shell.updateUi_message_printer(
                        "->Stack mode started -- Number of frames to save: "
                        + str(int(self._shell.number_of_planes))
                    )
                    self._shell._update_mode_badge(
                        "STACK", "RUNNING", plane=1,
                        total=int(self._shell.number_of_planes),
                    )

                    # Sample the auto-laser checkboxes on the GUI thread
                    # before spawning the worker (AGENTS.md §11).
                    self._shell._cache_auto_laser_flags()

                    # Spawn the stack worker (shared with the queue loop).
                    self._spawn_stack_worker()

    def _spawn_stack_worker(self):
        """Spawn the stack worker on its QThread (moveToThread pattern),
        wire its finished signal to the post-stack UI cleanup, and start
        it. Shared by the single-stack Start button and the Acquisition
        Table queue loop so both re-use the same worker (with its
        per-plane ValueError catch as the physical-safety backstop).

        Pre-samples the auto-laser flags + save-option widgets on the GUI
        thread before constructing the worker (AGENTS.md §11) so the
        worker thread never reaches into the shell's ui.*.
        """
        # If a previous stack thread is still running (e.g. the queue loop
        # re-entering for the next row), drain it before overwriting the
        # reference so no QThread is leaked. The worker's finished signal
        # already queued thread.quit(); this pumps the event loop so the
        # queued quit lands and the thread reaps deterministically.
        prev_thread = getattr(self._shell, "_stack_thread", None)
        if prev_thread is not None and prev_thread.isRunning():
            prev_thread.quit()
            app = QApplication.instance()
            deadline = 2000
            while prev_thread.isRunning() and deadline > 0:
                if app is not None:
                    app.processEvents()
                prev_thread.wait(20)
                deadline -= 20

        # B-03: pre-sample the save-option widgets on the GUI thread
        # BEFORE constructing the worker (AGENTS.md §11).
        save_desc = str(self._shell.save_panel.ui.lineEdit_saveDescription.text())
        save_blend = self._shell.save_panel.ui.checkBox_saveStitchBlend.isChecked()
        save_all_crop = self._shell.save_panel.ui.checkBox_saveAllCrop.isChecked()
        save_all_full = self._shell.save_panel.ui.checkBox_saveAllFull.isChecked()

        # Spawn the stack worker on a QThread (moveToThread pattern).
        self._shell._stack_worker = StackWorker(
            self._shell._bundle, self._shell._hw, self._shell,
            save_desc, save_blend, save_all_crop, save_all_full,
        )
        self._shell._stack_thread = QThread()
        self._shell._stack_worker.moveToThread(self._shell._stack_thread)
        self._shell._stack_thread.started.connect(self._shell._stack_worker.run)
        self._shell._stack_worker.finished.connect(self.updateUi_post_stack_mode)
        self._shell._stack_worker.finished.connect(self._shell._stack_thread.quit)
        self._shell._stack_thread.finished.connect(self._shell._stack_worker.deleteLater)
        self._shell._stack_thread.start()
        return self._shell._stack_worker

    @Slot()
    def updateUi_post_stack_mode(self) -> None:
        """Enabling modes after stack mode"""
        self._shell.stack_panel.ui.pushButton_acqStartStackMode.setText("Start Stack Mode")
        self.updateUi_modes_buttons(self._shell.default_buttons)
        self._shell.motor_panel.updateUi_motor_buttons(disable_button=False)

        self._shell.stack_mode_started = False
        self._shell.updateUi_message_printer("->Stack Mode Acquisition Done")
        self._shell.ui.statusBar_label.setText("")
        self._shell.ui.statusBar_progress.hide()
        self._shell._update_mode_badge("IDLE")
