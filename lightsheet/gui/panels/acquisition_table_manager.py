"""AcquisitionTableManager — a QTableWidget queue of z-stacks specified by
position/range/step.

Each row specifies one z-stack by start position, end position, and step
(per Voigt et al. 2019), enabling sequences of z-stacks without the operator
re-driving the stage to each boundary. The operator adds/edits/removes/
reorders rows; Start Queue (``_start_queue``) executes the rows sequentially,
re-using the existing stack worker per row.

The table manager composes into the Stack panel alongside the existing
single-stack Set-button workflow. The single-stack workflow stays for
one-off stacks; the table is for multi-stack sequences.

Row validation mirrors the single-stack spinbox reject-and-beep pattern:
start/end values are validated against the horizontal motor travel limits
(``get_limit_low`` / ``get_limit_high``) before a row is considered
complete. The worker's per-plane ``move_absolute_position`` ``ValueError``
catch stays as the physical-safety backstop if a row slips past the table
validation.

The queue execution loop runs on the GUI thread so the E-stop kill path
(also GUI thread) can abort it synchronously. Each row's stack runs on the
existing stack worker thread; the GUI thread waits for it via a
``QEventLoop`` with ``quit()`` connected to the worker's ``finished``
signal — NOT ``threading.Event.wait()`` (which would block the event loop
and freeze the GUI, contradicting the responsive-GUI goal and the E-stop
responsiveness invariant).
"""

from __future__ import annotations

import math
import typing

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if typing.TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow


# Column indices in the QTableWidget.
_COL_NAME = 0
_COL_START = 1
_COL_END = 2
_COL_STEP = 3
_COL_NPLANES = 4
_COL_ESTTIME = 5
_COL_ESTSIZE = 6

_HEADERS = [
    "Name",
    "Start (\u03bcm)",
    "End (\u03bcm)",
    "Step (\u03bcm)",
    "#Planes",
    "Est. Time",
    "Est. Size",
]

_EMPTY_COPY = (
    "No stacks in the queue. Add a stack to specify position/range/step "
    "without re-driving the stage to each boundary."
)

_ERROR_COPY = (
    "Cannot start the queue: {reason} (e.g. a stack's range exceeds stage "
    "travel limits, or no save path is set). Fix the flagged row and retry."
)

_FLAG_COLOR = QColor(255, 200, 200)


class _Row:
    """A snapshot of one table row's values (in micrometres)."""

    __slots__ = ("name", "start", "end", "step", "n_planes",
                 "est_time_s", "est_size_mb")

    def __init__(self, name: str, start: float, end: float, step: float,
                 n_planes: int, est_time_s: float, est_size_mb: float) -> None:
        self.name = name
        self.start = start
        self.end = end
        self.step = step
        self.n_planes = n_planes
        self.est_time_s = est_time_s
        self.est_size_mb = est_size_mb


class AcquisitionTableManager(QWidget):
    """QTableWidget-based queue of z-stacks by position/range/step.

    Owns the table widget + Add/Remove/Move Up/Move Down/Start Queue
    buttons. Row values are stored in micrometres (the internal unit the
    worker + motor HAL use), regardless of the display unit.

    The past-acquisitions browser (Planned/Past toggle, Refresh button,
    past table, async scan worker) moved to a dedicated left-rail panel
    (``PastAcquisitionsPanel``) so it has room to breathe. This manager
    keeps only the Planned queue + add/edit/remove/start-queue controls.
    """

    def __init__(self, shell: "Controller_MainWindow") -> None:
        super().__init__()
        self._shell = shell

        layout = QVBoxLayout(self)

        # --- Table ---
        self.table = QTableWidget(0, len(_HEADERS), self)
        self.table.setObjectName("tableWidget_acquisitionQueue")
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
        )
        # Scroll when content exceeds the viewport (E8 overflow).
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        # Long names truncate with ellipsis; the full name is in the tooltip
        # (set per-item in _set_name_cell).
        self.table.setWordWrap(False)
        self.table.textElideMode = Qt.TextElideMode.ElideRight

        # --- Empty-state label (shown when the table has no rows) ---
        self._empty_label = QLabel(_EMPTY_COPY, self)
        self._empty_label.setWordWrap(True)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: gray; padding: 12px;")

        # --- Buttons ---
        btn_row = QHBoxLayout()
        self.pushButton_addStack = QPushButton("Add Stack", self)
        self.pushButton_addStack.setObjectName("pushButton_addStack")
        self.pushButton_removeStack = QPushButton("Remove Stack", self)
        self.pushButton_removeStack.setObjectName("pushButton_removeStack")
        self.pushButton_moveUp = QPushButton("Move Up", self)
        self.pushButton_moveUp.setObjectName("pushButton_moveUp")
        self.pushButton_moveDown = QPushButton("Move Down", self)
        self.pushButton_moveDown.setObjectName("pushButton_moveDown")
        self.pushButton_startQueue = QPushButton("Start Queue", self)
        self.pushButton_startQueue.setObjectName("pushButton_startQueue")
        self.pushButton_startQueue.setEnabled(False)
        for btn in (self.pushButton_addStack, self.pushButton_removeStack,
                    self.pushButton_moveUp, self.pushButton_moveDown,
                    self.pushButton_startQueue):
            btn_row.addWidget(btn)

        layout.addWidget(self._empty_label)
        layout.addWidget(self.table)
        layout.addLayout(btn_row)

        # The table is hidden until the first row is added so the empty
        # state copy is the only visible content.
        self.table.setVisible(False)

        # --- Wire buttons ---
        self.pushButton_addStack.clicked.connect(self.add_stack)
        self.pushButton_removeStack.clicked.connect(self.remove_stack)
        self.pushButton_moveUp.clicked.connect(self.move_up)
        self.pushButton_moveDown.clicked.connect(self.move_down)
        self.pushButton_startQueue.clicked.connect(self._start_queue)
        self.table.cellChanged.connect(self._on_cell_changed)

        # Queue execution state (set by _start_queue, read by the shell's
        # progress-mirror slot so the mode badge includes the row index).
        self._queue_active = False
        self._queue_row_index = 0
        self._queue_rows_total = 0

        # Re-entrancy guard: _recompute_row sets readonly cells via setItem
        # which can re-trigger cellChanged. The guard breaks the loop.
        self._recomputing = False

    # ------------------------------------------------------------------ #
    # Public API (used by tests + the queue loop)
    # ------------------------------------------------------------------ #

    def empty_state_text(self) -> str:
        return _EMPTY_COPY

    def error_state_text(self, reason: str) -> str:
        return _ERROR_COPY.format(reason=reason)

    def add_stack(self) -> None:
        """Append a new row pre-filled with the current stack panel
        values (first plane, last plane, step size). The row name
        defaults to "Stack N". If the stack panel has valid start/end
        values, the row is immediately ready for Start Queue."""
        sp = self._shell.stack_panel.ui
        start = sp.doubleSpinBox_acqFirstPlane.value()
        end = sp.doubleSpinBox_acqLastPlane.value()
        step = sp.doubleSpinBox_acqPlaneStepSize.value()
        if step == 0:
            step = 1.0  # avoid division by zero in n_planes computation
        row = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(row)
        self._set_name_cell(row, f"Stack {row + 1}")
        self._set_numeric_cell(row, _COL_START, start)
        self._set_numeric_cell(row, _COL_END, end)
        self._set_numeric_cell(row, _COL_STEP, step)
        self._set_readonly_cell(row, _COL_NPLANES, "0")
        self._set_readonly_cell(row, _COL_ESTTIME, "0:00")
        self._set_readonly_cell(
            row, _COL_ESTSIZE,
            self._format_size_human_readable(0.0, self._format_label()),
        )
        self.table.blockSignals(False)
        # Recompute + validate the new row (signals re-enabled).
        self._recompute_row(row)
        self._update_empty_state()
        self._update_start_queue_state()

    def remove_stack(self) -> None:
        """Remove the selected row after a Yes/Cancel confirmation dialog
        that names the row."""
        row = self.table.currentRow()
        if row < 0 or row >= self.table.rowCount():
            return
        name = self.table.item(row, _COL_NAME).text()
        answer = QMessageBox.question(
            self,
            "Remove Stack",
            f'Remove "{name}" from the queue?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.table.removeRow(row)
            self._update_empty_state()
            self._update_start_queue_state()

    def move_up(self) -> None:
        """Swap the selected row with the row above it."""
        row = self.table.currentRow()
        if row <= 0:
            return
        self._swap_rows(row, row - 1)
        self.table.selectRow(row - 1)

    def move_down(self) -> None:
        """Swap the selected row with the row below it."""
        row = self.table.currentRow()
        if row < 0 or row >= self.table.rowCount() - 1:
            return
        self._swap_rows(row, row + 1)
        self.table.selectRow(row + 1)

    def set_cell(self, row: int, col: int, value: str) -> None:
        """Set a cell's text (test helper + programmatic edit). Triggers
        the cellChanged → _on_cell_changed recompute path."""
        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem(value)
            self.table.setItem(row, col, item)
        else:
            item.setText(value)
        # cellChanged fires from setText; the recompute runs there.

    def row_at(self, row: int) -> _Row:
        """Snapshot of one row's parsed values (micrometres).

        Non-numeric cell text (the operator typed "abc" or "1.0.0") is
        treated as 0.0 so the row computes to 0 planes and the queue's
        pre-start validation rejects it with a clear message, rather than
        raising an uncaught ValueError that crashes queue start.
        """
        name = self.table.item(row, _COL_NAME).text()
        start = self._safe_float(row, _COL_START)
        end = self._safe_float(row, _COL_END)
        step = self._safe_float(row, _COL_STEP)
        n_planes, est_time_s, est_size_mb = self._compute(start, end, step)
        return _Row(name, start, end, step, n_planes, est_time_s, est_size_mb)

    def _safe_float(self, row: int, col: int) -> float:
        """Parse a numeric cell's text to float, returning 0.0 on
        non-numeric text. The cell is NOT flagged here (flagging happens
        in _recompute_row_impl on edit); this helper only prevents a
        ValueError crash at queue-start time."""
        try:
            return float(self.table.item(row, col).text() or 0.0)
        except (ValueError, TypeError):
            return 0.0

    def _parse_or_flag(self, row: int, col: int, text: str) -> float:
        """Parse a numeric cell's text to float during recompute, flagging
        the cell red if the text is non-numeric so the operator sees the
        bad cell. Returns 0.0 for unparseable text so the downstream
        plane-count computation does not crash."""
        try:
            return float(text or 0.0)
        except (ValueError, TypeError):
            self._flag(row, col)
            return 0.0

    def is_row_flagged(self, row: int) -> bool:
        """True if the row has any flagged (red-background) cell."""
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item is not None and item.background() == _FLAG_COLOR:
                return True
        return False

    def start_queue_enabled(self) -> bool:
        """True if Start Queue should be enabled: at least one row + no
        flagged (incomplete/out-of-range) cells."""
        if self.table.rowCount() == 0:
            return False
        for row in range(self.table.rowCount()):
            if self.is_row_flagged(row):
                return False
        return True

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _set_name_cell(self, row: int, name: str) -> None:
        item = QTableWidgetItem(name)
        # Long names truncate with ellipsis; the full name is in the tooltip.
        item.setToolTip(name)
        self.table.setItem(row, _COL_NAME, item)

    def _set_numeric_cell(self, row: int, col: int, value: float) -> None:
        self.table.setItem(row, col, QTableWidgetItem(str(value)))

    def _set_readonly_cell(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        # Selectable + enabled, but NOT editable (computed columns).
        item.setFlags(Qt.ItemFlag.ItemIsSelectable
                      | Qt.ItemFlag.ItemIsEnabled)
        self.table.setItem(row, col, item)

    def _compute(self, start: float, end: float, step: float
                 ) -> tuple[int, float, float]:
        """Compute (#planes, est. time s, est. size MB) for a row."""
        if step == 0 or start == end:
            return 0, 0.0, 0.0
        n_planes = int(math.ceil(abs((end - start) / step))) + 1
        per_plane_s = self._estimate_per_plane_time()
        est_time_s = n_planes * per_plane_s
        est_size_mb = self._estimate_stack_size_mb(n_planes)
        return n_planes, est_time_s, est_size_mb

    def _estimate_per_plane_time(self) -> float:
        """Advisory per-plane acquisition time in seconds."""
        try:
            exposure = float(self._shell.acquisition_panel.ui
                             .doubleSpinBox_cameraExposureTime.value())
            return exposure / 1000.0 * 1.5
        except (AttributeError, ValueError, TypeError):
            return 0.5

    def _estimate_stack_size_mb(self, n_planes: int) -> float:
        """Advisory stack size in MB, format-aware.

        - ``hdf5`` (and the tiff/legacy fallback): raw bytes —
          ``rows * cols * 2 * n_planes`` (uint16), unchanged from the
          pre-format-aware behavior.
        - ``zarr``: raw L0 bytes plus the multiscale pyramid overhead.
          The pyramid level count is stack_step-dependent: count the
          targets in ``(10, 25, 50, 100)`` µm that are ``>= max(base_res)``
          where ``base_res = (abs(stack_step), 6.5*binning_x,
          6.5*binning_y)`` — the same target-validity filter the writer's
          ``finalize_with_resolutions`` applies (so the estimate tracks
          the real on-disk pyramid, NOT a hardcoded level count). Each
          downsampled level is ~1/4 of the previous (2× Y/X downsample),
          so the total pyramid overhead is
          ``L0 * sum(0.25**i for i in range(level_count))``.
        - ``both``: ``hdf5_estimate + zarr_estimate`` (sum).
        """
        try:
            # The camera HAL exposes ysize/xsize (not rows/columns);
            # reading the wrong attrs always fell back to 2000x2000,
            # making the estimate wrong for any non-2000x2000 camera.
            rows = int(getattr(self._shell.camera, "ysize", 2000) or 2000)
            cols = int(getattr(self._shell.camera, "xsize", 2000) or 2000)
        except (AttributeError, TypeError, ValueError):
            rows, cols = 2000, 2000
        bytes_per_frame = rows * cols * 2
        l0_bytes = n_planes * bytes_per_frame
        l0_mb = l0_bytes / (1024.0 * 1024.0)

        fmt = str(getattr(self._shell, "save_format", "hdf5")).lower()
        if fmt == "zarr":
            return l0_mb * self._zarr_pyramid_multiplier()
        if fmt == "both":
            return l0_mb + l0_mb * self._zarr_pyramid_multiplier()
        # hdf5 / tiff / unknown -> raw bytes.
        return l0_mb

    def _zarr_pyramid_multiplier(self) -> float:
        """Total-size multiplier for the OME-Zarr pyramid relative to L0.

        The level count is derived from the live ``base_res`` (Z from
        ``stack_step``, XY from the camera binning) using the writer's
        target-validity filter: a target resolution is kept only if
        ``target_um >= max(base_res)``. Each retained level is ~1/4 of
        the previous (2× Y/X downsample), so the geometric sum
        ``sum(0.25**i for i in range(level_count))`` is the overhead
        factor on top of L0 (level 0 contributes 1.0).
        """
        try:
            stack_step = float(getattr(self._shell, "stack_step", 0.0))
        except (TypeError, ValueError):
            stack_step = 0.0
        cam = getattr(self._shell, "camera", None)
        binning_x = int(getattr(cam, "binning_x", 1) or 1)
        binning_y = int(getattr(cam, "binning_y", 1) or 1)
        base_res = (abs(stack_step), 6.5 * binning_x, 6.5 * binning_y)
        max_res = max(base_res) if base_res else 0.0
        level_count = sum(1 for t in (10, 25, 50, 100) if t >= max_res)
        # Level 0 (raw) is always present; each downsampled level adds
        # 0.25**i of L0. The multiplier covers L0 + all pyramid levels.
        return sum(0.25 ** i for i in range(level_count))

    def _format_size_human_readable(self, mb: float, fmt: str) -> str:
        """Format an MB value as a human-readable string with a format
        suffix: ``>=1024 GB`` -> TB, ``>=1024 MB`` -> GB, else MB. One
        decimal place. ``fmt`` is the uppercase label (``"HDF5"`` /
        ``"OME-Zarr"`` / ``"Both"``)."""
        if mb >= 1024.0 * 1024.0:
            return f"{mb / 1024.0 / 1024.0:.1f} TB ({fmt})"
        if mb >= 1024.0:
            return f"{mb / 1024.0:.1f} GB ({fmt})"
        return f"{mb:.1f} MB ({fmt})"

    def _format_label(self) -> str:
        """Map ``self._shell.save_format`` to the uppercase suffix label
        used in the Est. Size cell."""
        fmt = str(getattr(self._shell, "save_format", "hdf5")).lower()
        if fmt == "zarr":
            return "OME-Zarr"
        if fmt == "both":
            return "Both"
        return "HDF5"

    def recompute_all_rows(self) -> None:
        """Re-estimate every planned-queue row's Est. Size cell.

        Subscribed to the save-format radio group's ``buttonClicked``
        signal (wired in the controller): when the operator switches
        format, every row's size estimate is re-computed against the new
        format so the format-dependence is visible at planning time. Uses
        the existing ``_recomputing`` re-entrancy guard so the per-row
        ``setItem`` calls do not re-trigger ``cellChanged``.
        """
        if self._recomputing:
            return
        self._recomputing = True
        try:
            for i in range(self.table.rowCount()):
                self._recompute_row_impl(i)
        finally:
            self._recomputing = False

    def _recompute_row(self, row: int) -> None:
        """Recompute #planes/est.time/est.size for a row + validate
        start/end against the motor travel limits. Flag incomplete or
        out-of-range cells with a red background."""
        if self._recomputing:
            return
        self._recomputing = True
        try:
            self._recompute_row_impl(row)
        finally:
            self._recomputing = False

    def _recompute_row_impl(self, row: int) -> None:
        # Parse each editable numeric cell, flagging non-numeric text
        # (e.g. "abc", "1.0.0") instead of crashing on every keystroke.
        # _safe_float returns 0.0 for unparseable text; the flag below
        # surfaces the bad cell to the operator so they can fix it.
        start_text = self.table.item(row, _COL_START).text()
        end_text = self.table.item(row, _COL_END).text()
        step_text = self.table.item(row, _COL_STEP).text()
        start = self._parse_or_flag(row, _COL_START, start_text)
        end = self._parse_or_flag(row, _COL_END, end_text)
        step = self._parse_or_flag(row, _COL_STEP, step_text)
        n_planes, est_time_s, est_size_mb = self._compute(start, end, step)

        self.table.blockSignals(True)
        self._set_readonly_cell(row, _COL_NPLANES, str(n_planes))
        mm, ss = divmod(int(est_time_s), 60)
        self._set_readonly_cell(row, _COL_ESTTIME, f"{mm}:{ss:02d}")
        self._set_readonly_cell(
            row, _COL_ESTSIZE,
            self._format_size_human_readable(est_size_mb, self._format_label()),
        )
        # Update the name tooltip in case the name was edited.
        name_item = self.table.item(row, _COL_NAME)
        if name_item is not None:
            name_item.setToolTip(name_item.text())
        self.table.blockSignals(False)

        # Clear flags then re-validate.
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item is not None:
                item.setBackground(QColor(255, 255, 255))

        flagged = False
        # Incomplete: start == end or step == 0.
        if step == 0:
            self._flag(row, _COL_STEP)
            flagged = True
        if start == end:
            self._flag(row, _COL_START)
            self._flag(row, _COL_END)
            flagged = True
        # Out-of-range: start/end outside the motor travel limits.
        motors = getattr(self._shell, "motors", None)
        if motors is not None:
            try:
                low = float(motors.horizontal.get_limit_low("\u03bcm"))
                high = float(motors.horizontal.get_limit_high("\u03bcm"))
            except (TypeError, ValueError, AttributeError):
                low, high = None, None
            if low is not None and high is not None:
                if start < low or start > high:
                    self._flag(row, _COL_START)
                    flagged = True
                if end < low or end > high:
                    self._flag(row, _COL_END)
                    flagged = True
        if flagged:
            self._shell.sig_message.emit(
                f"Row {row + 1} is incomplete or out of range. "
                "Fix the highlighted cells before starting the queue."
            )

    def _flag(self, row: int, col: int) -> None:
        item = self.table.item(row, col)
        if item is not None:
            item.setBackground(_FLAG_COLOR)

    def _on_cell_changed(self, row: int, col: int) -> None:
        """Recompute + validate on any editable-cell edit. Skip the
        computed (readonly) columns + use a re-entrancy guard so the
        setItem calls inside _recompute_row do not loop."""
        if self._recomputing:
            return
        if col in (_COL_NPLANES, _COL_ESTTIME, _COL_ESTSIZE):
            return
        self._recompute_row(row)
        self._update_start_queue_state()

    def _swap_rows(self, a: int, b: int) -> None:
        """Swap two rows' cell contents (preserving the selection)."""
        self.table.blockSignals(True)
        for col in range(self.table.columnCount()):
            ia = self.table.takeItem(a, col)
            ib = self.table.takeItem(b, col)
            self.table.setItem(a, col, ib)
            self.table.setItem(b, col, ia)
        self.table.blockSignals(False)
        self._update_start_queue_state()

    def _update_empty_state(self) -> None:
        has_rows = self.table.rowCount() > 0
        self._empty_label.setVisible(not has_rows)
        self.table.setVisible(has_rows)

    def _update_start_queue_state(self) -> None:
        self.pushButton_startQueue.setEnabled(self.start_queue_enabled())

    # ------------------------------------------------------------------ #
    # Queue execution (Task 2 — implemented in Task 2)
    # ------------------------------------------------------------------ #

    def _start_queue(self) -> None:
        """Start Queue: execute rows sequentially via the existing stack
        worker, re-using the single-stack worker invocation per row.

        The queue loop runs on the GUI thread so the E-stop kill path
        (also GUI thread) can abort it synchronously. Each row's stack
        runs on the existing stack worker thread; the GUI thread waits
        for it via a QEventLoop with quit() connected to the worker's
        finished signal — NOT threading.Event.wait() (which would block
        the event loop and freeze the GUI). The QEventLoop keeps the
        event loop pumping so timers/signals/paint events fire and the
        E-stop kill path stays responsive.

        Between rows, the queue checks estop_event — if set, it stops
        (no auto-resume; the operator must re-arm + manually restart).
        The worker's per-plane move_absolute_position ValueError catch
        is the physical-safety backstop if a row's start slips past the
        table validation.
        """
        from PySide6.QtCore import QEventLoop

        rows = [self.row_at(i) for i in range(self.table.rowCount())]

        # --- Validate before starting ---
        if not rows:
            self._shell.sig_message.emit(
                self.error_state_text("no stacks in the queue")
            )
            self._shell.sig_beep.emit()
            return
        for i, r in enumerate(rows):
            if r.n_planes == 0:
                self._shell.sig_message.emit(
                    self.error_state_text(
                        f"row {i + 1} ({r.name}) is incomplete \u2014 "
                        "set a valid start/end/step"
                    )
                )
                self._shell.sig_beep.emit()
                return
        # Save-path check: if saving is allowed, a save directory must be
        # set. (If saving is not allowed, the queue runs without saving —
        # the worker checks self._shell.saving_allowed per row.)
        if getattr(self._shell, "saving_allowed", False):
            if not getattr(self._shell, "save_directory", ""):
                self._shell.sig_message.emit(
                    self.error_state_text("no save path is set")
                )
                self._shell.sig_beep.emit()
                return

        # --- Execute the queue ---
        self._queue_active = True
        self._queue_rows_total = len(rows)
        # Disable the table buttons while the queue runs.
        self._set_queue_running(True)
        # Snapshot the operator's single-stack state so it can be
        # restored after the queue completes or aborts (the queue
        # overwrites these per row). Captured BEFORE the loop touches them.
        saved_single_stack = (
            self._shell.stack_starting_plane,
            self._shell.stack_ending_plane,
            self._shell.stack_step,
            self._shell.number_of_planes,
            self._shell.stack_first_plane_set,
            self._shell.stack_last_plane_set,
        )
        try:
            for i, row in enumerate(rows):
                # Between rows, check E-stop — abort the queue if set.
                if self._shell.estop_event.is_set():
                    self._shell.sig_message.emit(
                        "Queue aborted by E-stop. Re-arm and manually "
                        "restart the queue to resume."
                    )
                    break
                self._queue_row_index = i

                # Configure the shell's stack params from the row (μm).
                # Set them directly (not via updateUi_set_number_of_planes,
                # which reads the single-stack spinboxes and would
                # overwrite the row's values). The worker reads
                # stack_starting_plane / stack_step / number_of_planes.
                self._shell.stack_starting_plane = row.start
                self._shell.stack_ending_plane = row.end
                # stack_step carries the direction sign (negative when
                # end < start), matching updateUi_stack_mode_button.
                self._shell.stack_step = (
                    row.step if row.end >= row.start else -row.step
                )
                self._shell.number_of_planes = row.n_planes
                self._shell.stack_first_plane_set = True
                self._shell.stack_last_plane_set = True
                # The stack worker's first-iteration guard
                # (``if not self._shell.stack_mode_started: break``) and
                # its laser-start gate both read this flag, so it MUST be
                # True before the worker is spawned for each row. The
                # single-stack Start button sets it at
                # acquisition_panel.py; the queue bypasses that path, so
                # set it here. Reset to False in the finally block below
                # so a subsequent single-stack Start re-arms cleanly.
                self._shell.stack_mode_started = True
                # Mirror the row's step into the single-stack spinbox for
                # UI consistency (blocked so it does not recompute). The
                # row stores µm; the spinbox displays in micrometres (the
                # fixed stack-display unit; the global units toggle is
                # gone), so the value is passed through unchanged.
                sb_step = self._shell.stack_panel.ui.doubleSpinBox_acqPlaneStepSize
                display_step = row.step
                sb_step.blockSignals(True)
                sb_step.setValue(display_step)
                sb_step.blockSignals(False)

                # Update the mode badge with the row index.
                self._shell._update_mode_badge(
                    "STACK", "RUNNING", plane=1,
                    total=int(self._shell.number_of_planes),
                    queue_row=i + 1, queue_total=len(rows),
                )

                # Move the stage to the row's start position. The
                # worker's per-plane move_absolute_position ValueError
                # catch is the physical-safety backstop if this slips
                # past the table validation.
                #
                # Pre-move E-stop re-check: the loop-top estop check runs
                # once per row, but several GUI-thread statements (param
                # setup, spinbox mirror, mode badge) run between it and
                # this move. Re-check here so an E-stop pressed in that
                # window aborts the queue before the blocking serial
                # move starts. This narrows (does not eliminate) the
                # window in which the GUI thread is blocked by the motor
                # move and cannot process the E-stop button click until
                # the move returns. Fully closing that window requires
                # offloading the move to a worker thread, which is
                # deferred to the threading rework (high-risk on this
                # codebase; a partial threading change could deadlock or
                # desync the lock-free E-stop kill path).
                if self._shell.estop_event.is_set():
                    self._shell.sig_message.emit(
                        "Queue aborted by E-stop. Re-arm and manually "
                        "restart the queue to resume."
                    )
                    break
                try:
                    self._shell.motors.horizontal.move_absolute_position(
                        row.start, "\u03bcm"
                    )
                except ValueError:
                    self._shell.sig_message.emit(
                        self.error_state_text(
                            f"row {i + 1} start {row.start:.2f} \u03bcm "
                            "exceeds stage travel limits"
                        )
                    )
                    self._shell.sig_beep.emit()
                    break

                # Start the stack worker (re-use the existing single-stack
                # invocation — no new worker spawned here; the shared
                # helper in the acquisition panel owns the worker thread).
                worker = self._shell.acquisition_panel._spawn_stack_worker()

                # Non-blocking wait: a QEventLoop with quit() connected to
                # the worker's finished signal. This keeps the GUI event
                # loop pumping (timers, signals, paint events fire) while
                # waiting for the worker thread to signal completion. Do
                # NOT use threading.Event.wait() on the GUI thread — that
                # would block the event loop + freeze the GUI, contradicting
                # the responsive-GUI goal + the E-stop responsiveness
                # invariant.
                loop = QEventLoop()
                worker.finished.connect(loop.quit)
                loop.exec()
        finally:
            # Reset the stack-mode flag so a subsequent single-stack
            # Start re-arms cleanly (the worker's first-iteration guard
            # reads it). This also covers the E-stop abort path between
            # rows: estop_event is set, the loop breaks, and we land here.
            self._shell.stack_mode_started = False
            # Restore the operator's single-stack state that the queue
            # overwrote per row. This runs on both normal completion and
            # abort (E-stop / over-travel ValueError), so the single-stack
            # spinbox/Set-button workflow returns to its pre-queue values.
            (
                self._shell.stack_starting_plane,
                self._shell.stack_ending_plane,
                self._shell.stack_step,
                self._shell.number_of_planes,
                self._shell.stack_first_plane_set,
                self._shell.stack_last_plane_set,
            ) = saved_single_stack
            self._queue_active = False
            self._set_queue_running(False)
            self._update_start_queue_state()

    def _set_queue_running(self, running: bool) -> None:
        """Toggle the table buttons + Start Queue while the queue runs."""
        self.pushButton_addStack.setEnabled(not running)
        self.pushButton_removeStack.setEnabled(not running)
        self.pushButton_moveUp.setEnabled(not running)
        self.pushButton_moveDown.setEnabled(not running)
        self.pushButton_startQueue.setEnabled(not running)
