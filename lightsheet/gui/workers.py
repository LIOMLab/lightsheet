"""Per-mode acquisition worker QObjects for the threading migration.

This module owns the worker ``QObject`` classes introduced by the
threading-vehicle migration from ``threading.Thread`` to ``QThread`` +
``moveToThread``. Each acquisition mode's worker body relocates here from
``AcquisitionCoordinator`` (which stays plain-Python and keeps its
GUI-thread galvo/ETL slots).

Only ``PreviewWorker`` is present in this file today; ``LiveWorker`` /
``SingleWorker`` / ``StackWorker`` land in later plans as their bodies
relocate. The shell (``Controller_MainWindow``) constructs a worker
``QObject`` + a ``QThread``, calls ``worker.moveToThread(thread)``,
connects ``thread.started -> worker.run`` and
``worker.finished -> shell.updateUi_post_<mode>`` /
``worker.finished -> thread.quit``, then ``thread.start()``. Shutdown in
``closeEvent`` calls ``thread.quit()`` + ``thread.wait(5000)``.

The cooperative cancellation model (``*_mode_started`` bool flag +
``estop_event`` ``threading.Event``) is preserved verbatim — the workers
poll ``self._shell.estop_event.is_set()`` at the same loop sites. The
E-stop kill path stays lock-free on the GUI thread; the workers only
*poll* the event. ``QThread.requestInterruption()`` is NOT adopted.

Workers never touch ``self._shell.ui.*`` widgets directly (AGENTS.md
§11) — all cross-thread UI effects flow through the shell's queued
``pyqtSignal`` connections (``sig_message``, ``sig_progress_update``,
``sig_*_mode_finished``) plus this worker's own ``finished`` signal.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from lightsheet.hal.bundle import DeviceBundle

if TYPE_CHECKING:
    from lightsheet.gui.controller import Controller_MainWindow
    from lightsheet.gui.hardware_manager import HardwareManager

logger = logging.getLogger(__name__)


class PreviewWorker(QObject):
    """Worker ``QObject`` for preview mode (beam-calibration visualization).

    Relocated verbatim from ``AcquisitionCoordinator.preview_mode_worker``.
    The body arms the camera, starts the auto-selected lasers, grabs
    frames in a loop while ``self._shell.preview_mode_started`` is set,
    polls ``self._shell.estop_event`` at each iteration, then stops the
    lasers and disarms the camera. The ``finished`` signal fires exactly
    once in ``finally`` so the GUI-thread slot
    (``updateUi_post_preview_mode``) re-enables the UI whether the run
    completes normally, breaks on E-stop, or an exception propagates.
    """

    finished = pyqtSignal()

    def __init__(
        self,
        bundle: DeviceBundle,
        hw: "HardwareManager",
        shell: "Controller_MainWindow",
    ) -> None:
        super().__init__()
        self.camera = bundle.camera
        self._hw = hw
        self._shell = shell

    @pyqtSlot()
    def run(self) -> None:
        """This thread allows the visualization and manual control of the
        parameters of the beams in the UI. There is no scan here,
        beams only changes when parameters are changed. This the preferred
        mode for beam calibration"""
        try:
            # Setting the camera for self triggered acquisition
            self.camera.set_trigger_mode("auto_trigger")
            self.camera.set_exposure_time(
                int(self._shell.ui.doubleSpinBox_cameraExposureTime.value())
            )
            self.camera.arm()

            # Start the auto-selected lasers after camera.arm() and before
            # the preview loop, mirroring live_mode_worker's shape. Preview
            # mode now drives the lasers so the operator can see the beam
            # while adjusting parameters — the previous shape left the
            # lasers dark during preview, defeating the mode's purpose for
            # beam calibration. start_lasers/stop_lasers read the cached
            # auto-laser flags sampled on the GUI thread by
            # _cache_auto_laser_flags() in updateUi_preview_mode_button.
            self._hw.start_lasers()

            while self._shell.preview_mode_started:
                # E-stop poll point — checked at the top of each iteration
                # before any frame acquisition work. The lasers are already
                # dark (driven off synchronously on the GUI thread in
                # updateUi_estop_pressed); this break just stops acquiring
                # new frames. Preview mode does not drive lasers or scan
                # generation, but the camera stays armed and grabbing until
                # the operator manually stops — polling estop_event aligns
                # preview_mode_worker with live/single/stack per the
                # AGENTS.md §2 rule that E-stop is polled in all acquisition
                # worker loops.
                if self._shell.estop_event.is_set():
                    break

                # # Updating Galvo and ETL voltages
                # self.siggen.update_all()

                # Recording a single image
                self.camera.start_recorder(1)
                self.camera.monitor_recorder(1)
                self.camera.stop_recorder()
                cam_images = self.camera.copy_recorder_images(1)
                self.camera.delete_recorder()

                # Sending first (and should be only) image to display port
                frame = cam_images[0]
                self._shell._fs.enqueue_frame(frame)

            # Stop the lasers before camera.disarm(), mirroring
            # live_mode_worker's cleanup shape. The lasers were started after
            # camera.arm() above; stopping them here ensures no laser is left
            # energized when the camera is disarmed and the mode exits.
            self._hw.stop_lasers()

            # Stopping camera
            self.camera.disarm()
        except Exception as e:
            self._shell.sig_message.emit(
                f"Preview acquisition failed — the run was aborted. Cause: {e}"
            )
            logger.exception("Preview mode worker failed")
        finally:
            # The finished signal must fire exactly once whether the method
            # completes normally or an exception propagates from
            # start_lasers()/acquire_scan()/camera.disarm()/anything else in
            # the body. Without this, a worker that dies mid-cleanup leaves
            # the UI stuck on "Stop Preview Mode" with no slot to re-enable it.
            self.finished.emit()
