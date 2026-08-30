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
import warnings

from PySide6.QtCore import QThread, Slot
from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget

from lightsheet.gui.panels.ui_acquisition_panel import Ui_AcquisitionPanel
from lightsheet.gui.widgets.field_spec import FIELD_SPECS
from lightsheet.gui.workers import LiveWorker, PreviewWorker, SingleWorker, StackWorker

if typing.TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


class AcquisitionPanelWidget(QWidget):
    """Acquisition modes panel — owns the four mode-button handlers
    (preview/live/single/stack) and the mode-button enable/disable helpers."""

    def __init__(self, shell: Controller_MainWindow) -> None:
        super().__init__()
        self._shell = shell
        self.ui = Ui_AcquisitionPanel()
        self.ui.setupUi(self)
        # Apply the declarative FieldSpec policy table to every promoted
        # FieldSpecSpinBox by objectName (suffix/decimals/step/soft min-max).
        for obj_name, spec in FIELD_SPECS.items():
            w = getattr(self.ui, obj_name, None)
            if w is not None and hasattr(w, "applySpec"):
                w.applySpec(spec)
        # Selective QSlider pairing for the wide-range coarse camera
        # exposure-time field. Bare bound-method connections (no lambdas).
        field_name = "doubleSpinBox_cameraExposureTime"
        spinbox = getattr(self.ui, field_name, None)
        slider = getattr(self.ui, f"slider_{field_name}", None)
        if spinbox is not None and slider is not None:
            spec = FIELD_SPECS[field_name]
            slider.setRange(int(spec.minimum), int(spec.maximum))
            slider.setSingleStep(int(spec.page_step))
            slider.setValue(int(spinbox.value()))
            spinbox.valueChanged.connect(slider.setValue)
            slider.valueChanged.connect(spinbox.setValue)

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

        # Disable the format + save-option radios during an active
        # acquisition and re-enable on idle. The radios are not in the
        # aquisition_buttons list (they are not QPushButtons); they are
        # toggled here alongside the mode buttons so a format/option
        # change mid-acquisition is impossible (the save worker reads
        # save_format at acquisition start).
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
        # Re-enable when the default buttons are being restored (idle
        # state); disable when only the active mode button is enabled.
        # Use all() so idle is True only when the full default button set
        # is present — during an active acquisition only the active mode's
        # stop button is in buttons_to_enable, so all() returns False and
        # the radios are disabled. The previous any() heuristic always
        # returned True (the active stop button is also a start button),
        # so the radios were never disabled mid-acquisition.
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
            save_blend = self._shell.save_panel.ui.radioButton_saveStitchBlend.isChecked()

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
        # Only arm the save button when this run actually produced a frame.
        # SingleWorker.run clears buffer before acquire_scan; acquire_scan
        # repopulates it only on a successful scan. A failed run (siggen
        # error / camera timeout early-return) leaves buffer None, so the
        # save button is dropped from the default-buttons list and stays
        # disabled rather than offering to save a missing or stale frame.
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
        # Reuse the same QThread across queue rows instead of constructing
        # a new one per row. Constructing + destroying a QThread C++ object
        # while the previous worker's deleteLater is still pending races
        # the C++ destructors and segfaults under xdist. A QThread can be
        # start()ed again after quit()+wait() returns, so we keep the
        # thread object alive for the controller's lifetime and only
        # replace the per-row worker (a plain Python object whose
        # finished signal drives thread.quit each row).
        prev_thread = getattr(self._shell, "_stack_thread", None)
        if prev_thread is not None and prev_thread.isRunning():
            prev_thread.quit()
            prev_thread.wait(5000)
        # If the thread was never created (first stack ever) or was
        # destroyed (teardown), construct a fresh one; otherwise reuse it.
        if prev_thread is None:
            self._shell._stack_thread = QThread()
        else:
            self._shell._stack_thread = prev_thread

        # B-03: pre-sample the save-option widgets on the GUI thread
        # BEFORE constructing the worker (AGENTS.md §11).
        save_desc = str(self._shell.save_panel.ui.lineEdit_saveDescription.text())
        save_blend = self._shell.save_panel.ui.radioButton_saveStitchBlend.isChecked()
        save_all_crop = self._shell.save_panel.ui.radioButton_saveAllCrop.isChecked()
        save_all_full = self._shell.save_panel.ui.radioButton_saveAllFull.isChecked()

        # Disconnect the previous worker's signals so its finished→quit
        # can't fire the reused thread a second time and its started→run
        # can't double-fire when the reused thread starts for the new row.
        prev_worker = getattr(self._shell, "_stack_worker", None)
        if prev_worker is not None:
            # libpyside emits a RuntimeWarning ("Failed to disconnect (None)
            # from signal finished()...") via warnings.warn when the signal
            # has no connections to disconnect — that is not a raised
            # exception, so the try/except below does not catch it. Suppress
            # it scoped to this call so -W error::RuntimeWarning does not
            # promote it to a fatal error. The try/except stays as a second
            # layer for the typed-exception arc.
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message='.*Failed to disconnect .* from signal "finished\\(\\)"',
                    category=RuntimeWarning,
                )
                try:
                    prev_worker.finished.disconnect()
                except (TypeError, RuntimeError):
                    pass

        # Spawn the stack worker on the (reused) QThread (moveToThread
        # pattern). A new worker per row is fine — it's a Python object
        # whose C++ side is just QObject, torn down by deleteLater on
        # thread.finished without racing another QThread destructor.
        self._shell._stack_worker = StackWorker(
            self._shell._bundle, self._shell._hw, self._shell,
            save_desc, save_blend, save_all_crop, save_all_full,
        )
        self._shell._stack_worker.moveToThread(self._shell._stack_thread)
        # When reusing the thread (2nd+ queue row), disconnect the prior
        # started→run so the reused thread's started only invokes this
        # row's run. Skip on the first spawn — no prior connection exists
        # and disconnect() would warn.
        if prev_thread is not None:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message='.*Failed to disconnect .* from signal "started\\(\\)"',
                    category=RuntimeWarning,
                )
                try:
                    self._shell._stack_thread.started.disconnect()
                except (TypeError, RuntimeError):
                    pass
        self._shell._stack_thread.started.connect(self._shell._stack_worker.run)
        self._shell._stack_worker.finished.connect(self.updateUi_post_stack_mode)
        self._shell._stack_worker.finished.connect(self._shell._stack_thread.quit)
        # thread.finished→worker.deleteLater: this fires each row (the
        # thread quits per row), reaping that row's worker. Disconnect any
        # prior thread.finished→deleteLater connection from a previous
        # queue row first — otherwise thread.finished accumulates one
        # deleteLater connection per row, and when the thread finishes it
        # calls deleteLater on already-deleted QObjects from prior rows
        # (Qt warns "QObject::deleteLater called on a deleted object" or
        # crashes under heavy queue use). The prev_worker.finished
        # disconnect above only clears the worker's own signals, not the
        # thread's finished signal.
        if prev_thread is not None:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message='.*Failed to disconnect .* from signal "finished\\(\\)"',
                    category=RuntimeWarning,
                )
                try:
                    self._shell._stack_thread.finished.disconnect()
                except (TypeError, RuntimeError):
                    pass
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
