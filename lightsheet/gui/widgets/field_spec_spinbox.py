"""FieldSpecSpinBox — promoted QDoubleSpinBox subclass with focus-gated
mouse-wheel input and Ctrl/Shift page-step, driven by a declarative
FieldSpec policy table.

This is the foundational widget promoted into every panel ``.ui`` file. It
fixes two long-standing UX complaints at the source:

1. **Wheel-steal**: an unfocused spinbox no longer swallows mouse-wheel
   events — the wheel only steps the value when the spinbox has focus.
   ``wheelEvent`` calls ``event.ignore()`` when unfocused so the event
   propagates to the parent (e.g. a ``QScrollArea``).
2. **Page-step**: Ctrl/Shift + wheel/arrow steps by ``page_step`` instead of
   ``single_step``. The ``stepBy`` override scales the incoming step count
   by ``page_step / single_step`` when a modifier is held and a spec is
   applied.

``applySpec(FieldSpec)`` sets suffix, decimals, singleStep, minimum, and
maximum in one call — the declarative policy table (``FIELD_SPECS``) drives
construction so panel wiring is mechanical.

The ``minimum``/``maximum`` set by ``applySpec`` are a SOFT widget-layer
block only. The HAL motor travel-limit validator (``config_schema.py`` +
``ZaberMotor.move_absolute_position`` ``ValueError``) is the safety
boundary; this subclass never relaxes any HAL validator.

Qt Designer promotion: set the promoted class name to ``FieldSpecSpinBox``
and the header to ``lightsheet.gui.widgets.field_spec_spinbox``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QDoubleSpinBox

from lightsheet.gui.widgets.field_spec import FIELD_PURPOSES, FIELD_SPECS, FieldSpec

__all__ = ["FieldSpecSpinBox", "FieldSpec", "FIELD_SPECS", "FIELD_PURPOSES"]


class FieldSpecSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox with focus-gated wheel + Ctrl/Shift page-step.

    A declarative ``FieldSpec`` (applied via ``applySpec``) drives the
    suffix, decimals, single/page step, and soft min/max. Without a spec
    the widget behaves like a plain ``QDoubleSpinBox`` except the wheel is
    still focus-gated.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._spec: FieldSpec | None = None

    def applySpec(self, spec: FieldSpec) -> None:  # noqa: N802 - Qt API name
        """Apply a FieldSpec: set suffix, decimals, singleStep, min, max,
        and generate the UI-SPEC §Tooltips (D-02) tooltip.

        The suffix is ``" {unit}"`` when ``unit`` is non-empty (leading
        space per Qt convention) and ``""`` otherwise (no leading space).

        The tooltip documents the wheel-gate + Ctrl/Shift page-step so the
        operator discovers the focus-gating by reading the tooltip rather
        than by surprise. Format (UI-SPEC §Tooltips):
        ``{field purpose}. Unit: {unit}. Range: {min}–{max} {unit}. Step:
        {single_step} {unit} (Ctrl/Shift = {page_step} {unit}). Wheel:
        click in first to scroll.`` Dimensionless fields (empty unit) omit
        the unit labels.
        """
        self._spec = spec
        self.setSuffix(f" {spec.unit}" if spec.unit else "")
        self.setDecimals(spec.decimals)
        self.setSingleStep(spec.single_step)
        self.setMinimum(spec.minimum)
        self.setMaximum(spec.maximum)
        self.setToolTip(self._build_tooltip(spec))

    def _build_tooltip(self, spec: FieldSpec) -> str:
        """Generate the UI-SPEC §Tooltips tooltip from the FieldSpec +
        the author-supplied purpose (FIELD_PURPOSES). Dimensionless fields
        (empty unit) omit the unit labels."""
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

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt override
        """Ignore the wheel unless the spinbox has focus.

        This is the root-cause fix for the wheel-steal complaint: an
        unfocused spinbox no longer swallows wheel events, so scrolling a
        panel does not accidentally nudge a value. When focused, defer to
        the base class (which honors ``singleStep`` and the modifier
        scaling done in ``stepBy``).
        """
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)

    def stepBy(self, steps: int) -> None:  # noqa: N802 - Qt override
        """Scale ``steps`` by ``page_step / single_step`` when Ctrl/Shift held.

        Without a modifier the base ``singleStep`` is used. With
        ``ControlModifier`` or ``ShiftModifier`` (and a spec whose
        ``single_step`` is non-zero) the step count is scaled so one
        "page" equals ``page_step``. Negative ``steps`` decrement.
        """
        mods = QApplication.keyboardModifiers()
        if (
            mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            and self._spec is not None
            and self._spec.single_step != 0
        ):
            steps = int(steps * (self._spec.page_step / self._spec.single_step))
        super().stepBy(steps)
