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
    from lightsheet.gui.controller import Controller_MainWindow


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
        """Append a new row with default values (name "Stack N",
        start 0, end 0, step 1). The row is incomplete (start == end) so
        Start Queue stays disabled until the operator fills it in."""
        row = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(row)
        self._set_name_cell(row, f"Stack {row + 1}")
        self._set_numeric_cell(row, _COL_START, 0.0)
        self._set_numeric_cell(row, _COL_END, 0.0)
        self._set_numeric_cell(row, _COL_STEP, 1.0)
        self._set_readonly_cell(row, _COL_NPLANES, "0")
        self._set_readonly_cell(row, _COL_ESTTIME, "0:00")
        self._set_readonly_cell(row, _COL_ESTSIZE, "0.0 MB")
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
        """Snapshot of one row's parsed values (micrometres)."""
        name = self.table.item(row, _COL_NAME).text()
        start = float(self.table.item(row, _COL_START).text() or 0.0)
        end = float(self.table.item(row, _COL_END).text() or 0.0)
        step = float(self.table.item(row, _COL_STEP).text() or 0.0)
        n_planes, est_time_s, est_size_mb = self._compute(start, end, step)
        return _Row(name, start, end, step, n_planes, est_time_s, est_size_mb)

    def is_row_flagged(self, row: int) -> bool:
        """True if the row has any flagged (red-background) cell."""
        for col in (range(self.table.columnCount())):
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
        """Advisory stack size in MB."""
        try:
            rows = int(getattr(self._shell.camera, "rows", 2000))
            cols = int(getattr(self._shell.camera, "columns", 2000))
        except (AttributeError, TypeError, ValueError):
            rows, cols = 2000, 2000
        bytes_per_frame = rows * cols * 2
        return (n_planes * bytes_per_frame) / (1024.0 * 1024.0)

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
        start = float(self.table.item(row, _COL_START).text() or 0.0)
        end = float(self.table.item(row, _COL_END).text() or 0.0)
        step = float(self.table.item(row, _COL_STEP).text() or 0.0)
        n_planes, est_time_s, est_size_mb = self._compute(start, end, step)

        self.table.blockSignals(True)
        self._set_readonly_cell(row, _COL_NPLANES, str(n_planes))
        mm, ss = divmod(int(est_time_s), 60)
        self._set_readonly_cell(row, _COL_ESTTIME, f"{mm}:{ss:02d}")
        self._set_readonly_cell(row, _COL_ESTSIZE, f"{est_size_mb:.1f} MB")
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
        worker. Implemented in Task 2."""
        raise NotImplementedError(
            "_start_queue is implemented in the queue-execution task."
        )
