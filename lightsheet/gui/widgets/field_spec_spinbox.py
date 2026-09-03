"""FieldSpecSpinBox — promoted QDoubleSpinBox subclass with focus-gated
mouse-wheel input and Ctrl/Shift page-step, driven by a declarative
FieldSpec policy table.

Fixes two UX complaints:
1. Wheel-steal: an unfocused spinbox no longer swallows mouse-wheel events.
2. Page-step: Ctrl/Shift + wheel/arrow steps by ``page_step``.

``applySpec(FieldSpec)`` sets suffix, decimals, singleStep, minimum, and
maximum in one call. The ``minimum``/``maximum`` are a SOFT widget-layer
block only — the HAL motor travel-limit validator is the safety boundary.

Qt Designer promotion: set the promoted class name to ``FieldSpecSpinBox``
and the header to ``lightsheet.gui.widgets.field_spec_spinbox``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QWidget

from lightsheet.gui.widgets.field_spec import FIELD_PURPOSES, FIELD_SPECS, FieldSpec

__all__ = ["FIELD_PURPOSES", "FIELD_SPECS", "FieldSpec", "FieldSpecSpinBox"]


class FieldSpecSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox with focus-gated wheel + Ctrl/Shift page-step.

    A declarative ``FieldSpec`` (applied via ``applySpec``) drives the
    suffix, decimals, single/page step, and soft min/max. Without a spec
    the widget behaves like a plain ``QDoubleSpinBox`` except the wheel is
    still focus-gated.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spec: FieldSpec | None = None

    def applySpec(self, spec: FieldSpec) -> None:
        """Apply a FieldSpec: set suffix, decimals, singleStep, min, max,
        and generate the tooltip."""
        self._spec = spec
        self.setSuffix(f" {spec.unit}" if spec.unit else "")
        self.setDecimals(spec.decimals)
        self.setSingleStep(spec.single_step)
        self.setMinimum(spec.minimum)
        self.setMaximum(spec.maximum)
        self.setToolTip(self._build_tooltip(spec))

    def _build_tooltip(self, spec: FieldSpec) -> str:
        """Generate the tooltip from the FieldSpec + the author-supplied
        purpose. Dimensionless fields omit the unit labels."""
        purpose = FIELD_PURPOSES.get(self.objectName(), "")
        if spec.unit:
            return (
                f"{purpose}. Unit: {spec.unit}. "
                f"Range: {spec.minimum}\u2013{spec.maximum} {spec.unit}. "
                f"Step: {spec.single_step} {spec.unit} "
                f"(Ctrl/Shift = {spec.page_step} {spec.unit}). "
                "Wheel: click in first to scroll."
            )
        return (
            f"{purpose}. "
            f"Range: {spec.minimum}\u2013{spec.maximum}. "
            f"Step: {spec.single_step} (Ctrl/Shift = {spec.page_step}). "
            "Wheel: click in first to scroll."
        )

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Ignore the wheel unless the spinbox has focus."""
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)

    def stepBy(self, steps: int) -> None:
        """Scale ``steps`` by ``page_step / single_step`` when Ctrl/Shift held."""
        mods = QApplication.keyboardModifiers()
        if (
            mods
            & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            and self._spec is not None
            and self._spec.single_step != 0
        ):
            steps = int(steps * (self._spec.page_step / self._spec.single_step))
        super().stepBy(steps)
