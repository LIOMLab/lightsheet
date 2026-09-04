# GUI Layout Convention

> Uniform layout convention for the light-sheet microscope controller's
> left-rail + QStackedWidget shell. Phase 9 channel controls (and any
> future panel) follow this convention so resize is uniform by
> construction, not per-panel ad-hoc.

This is a PySide6/Qt6 desktop app (currently PyQt5/Python 3.10 — migration
is separate). The convention uses Qt6 layout primitives
(`QSizePolicy`, `setMinimumSize`/`setMaximumSize`, `setStretchFactor`,
`QSplitter`, `QScrollArea`, `QStackedWidget`, `QToolButton`, `QToolBar`),
not CSS tokens. New panels must be Qt Designer promotable or programmatic
post-construction (`.ui` files are `pyside6-uic`-generated, never
hand-edited).

---

## 1. QScrollArea Wrapping Rule (uniform convention)

**Every panel is wrapped in a `QScrollArea(widgetResizable=True)` added
to the `QStackedWidget`.** This is the root-cause fix for the ad-hoc
resize choices that plagued the earlier shell: a single convention so
resize is uniform by construction.

```python
scroll = QScrollArea()
scroll.setWidgetResizable(True)
scroll.setFrameShape(QScrollArea.Shape.NoFrame)
scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
scroll.setWidget(panel)
stackedPanels.addWidget(scroll)
```

| Property | Value | Reason |
|----------|-------|--------|
| `widgetResizable` | `True` | The panel widget resizes to fit the scroll area's viewport; the scroll area does not clip the panel to its sizeHint |
| Horizontal scrollbar | `ScrollBarAlwaysOff` | Panels are vertical-scroll only; horizontal overflow is never the operator's intent |
| Vertical scrollbar | `ScrollBarAsNeeded` | The scrollbar appears only when the panel's content exceeds the viewport height |
| Frame shape | `NoFrame` | The scroll area is invisible — the panel looks like a direct child of the stacked pane |

**Applies to all 8 panels:** Motion, Acquire, Stack, Scan, Lasers, Files,
Past, Calibrate. Even short panels wrap, so the rule is uniform by
construction — no per-panel "is this tall enough to need a scroll area?"
decision.

---

## 2. Size-Policy & Stretch-Factor Contract

### Top-level shell (`ui_shell.ui`)

| Widget | Size policy | horstretch / verstretch | Min size | Max size | Notes |
|--------|-------------|--------------------------|----------|----------|-------|
| `QMainWindow` (Shell) | — | — | **1280×800** (`setMinimumSize`) | none | Window floor; laptop-friendly; image still large on 1920×1080 lab display |
| `toolBar_estop` (QToolBar, TopToolBarArea) | — | — | — | — | `movable=False`, `floatable=False` (safety — fixed). Hosts E-stop button, Arm/Reset, status label, mode badge. **No units selector.** |
| `splitter` (QSplitter, Horizontal) | — | — | — | — | `handleWidth=5`, `childrenCollapsible=False` |
| `leftRail` (QWidget) | **Fixed / Expanding** | **0 / 1** | **72×0** | **72×16777215** (`setFixedWidth(72)`) | Vertical left rail of `QToolButton`s. Fixed width; tall as the window. |
| `imagesPane` (QWidget) | **Expanding / Expanding** | **1 / 1** | **320×240** | none | Carries the ImageView + LevelsBar; stretch=1 so it wins space from controlsPane |
| `imageView` (ImageView = QGraphicsView) | **Expanding / Expanding** | **1 / 1** | **320×240** | none | `resizeEvent` re-calls `fitInView(sceneRect, KeepAspectRatio)`; scrollbar policy `AlwaysOff` |
| `controlsPane` (QWidget) | **Preferred / Expanding** | **0 / 1** | **360×0** | none | Hosts the `QStackedWidget`; stretch=0 so imagesPane wins the drag |
| `stackedPanels` (QStackedWidget) | **Expanding / Expanding** | 0 / 1 | 0×0 | none | Replaces the old QTabWidget. Hosts the 8 per-panel widgets (each wrapped per §1). |
| `plainTextEdit_messageLog` | **Expanding / Expanding** | 0 / 1 | **0×96** | none | Wrapped in a vertical `QSplitter` section inside `controlsPane`; `readOnly=True` |

### Per-panel size-policy rules (apply to ALL panel `.ui` files)

| Widget class | Size policy | Stretch | Min | Max | Rule |
|--------------|-------------|---------|-----|-----|------|
| Panel root `QWidget` | **Preferred / Preferred** | 0 / 0 | 0×0 | none | Lets the QScrollArea size the panel; the panel does not force the stacked-pane size |
| `QGroupBox` | **Preferred / Preferred** | 0 / 0 | content-driven min (~300×0) | none | The fixed-size caps are removed; do not re-introduce |
| `QLabel` (descriptive) | **Fixed / Preferred** | 0 / 0 | keep existing min width | none | Label width is content-driven |
| `QLabel` (status dot) | **Fixed / Fixed** | 0 / 0 | min width 140 (status) / 80 (readback) | none | Fixed-width so the dot+text does not reflow on status change |
| `QPushButton` (jog arrows) | **Fixed / Fixed** | 0 / 0 | **60×60** (keep) | none | Touch target; cap already dropped |
| `QPushButton` (action) | **Fixed / Fixed** | 0 / 0 | keep existing min | none | Cap already dropped |
| **`FieldSpecSpinBox`** (promoted `QDoubleSpinBox` subclass) | **Minimum / Fixed** | 0 / 0 | 120×0 | none | Replaces every `QDoubleSpinBox` in the panel `.ui` files. `applySpec(FieldSpec)` sets unit/decimals/singleStep/pageStep/min/max once at construction. Wheel-gated on focus; Ctrl/Shift page-step. |
| `QSlider` (selective pairing) | **Expanding / Fixed** | 1 / 0 | 120×0 | none | Paired with wide-range coarse `FieldSpecSpinBox` fields ONLY (galvo/ETL amplitude 0–10V, exposure 25–1000ms, motor travel). Synchronized value with the spinbox; spinbox is the authoritative input. NOT universal. |
| `QCheckBox` | **Preferred / Fixed** | 0 / 0 | 0×20 | none | Cap already dropped |
| `QFrame` (HLine separators) | **Fixed / Preferred** | 0 / 0 | 3×0 | none | Cap already dropped |

---

## 3. `setMaximumSize` Audit Rule

**Drop every `setMaximumSize` that pins a control's max to its min.**
Pinning a control's max to a fixed pixel size is the bug pattern that
broke responsive resize: the control cannot grow with the layout, so the
panel overflows or clips on resize.

```bash
# Audit: grep setMaximumSize in each ui_*.py; for every match where
# max == min (pinning the widget to a fixed size), drop the
# setMaximumSize call and keep the setMinimumSize.
grep -n "setMaximumSize" lightsheet/gui/panels/ui_*.py
```

**Exceptions (keep the max pin — fixed by design):**
- **Status-dot labels** (`label_estopStatus`, `label_laserOneStatus`,
  `label_laserTwoStatus`) — fixed-width so the dot+text does not reflow.
- **E-stop button** (`pushButton_estop`) — fixed minimum 96×48 px (safety
  — the red kill button must never shrink below the touch target).
- **Left-rail width** (`leftRail`) — `setFixedWidth(72)` (shell
  architecture — the rail is a fixed-width column, not collapsible).

---

## 4. QSplitter Stretch Factors

| Property | Value | Reason |
|----------|-------|--------|
| `orientation` | `Qt.Horizontal` | imagesPane left, controlsPane right (left-rail is OUTSIDE the splitter — fixed-width column to the left) |
| `handleWidth` | **5 px** | Visible drag affordance |
| `childrenCollapsible` | **False** | Panes must NOT collapse to 0; the operator drags to resize, not hide. Hiding is via the View menu. |
| Stretch factors | `imagesPane` stretch=1, `controlsPane` stretch=0 | imagesPane wins extra space on window grow; controlsPane stays at its sizeHint |
| Drag semantics | Drag = operator's image-size control | No dedicated zoom/slider; no layout-swap on resize |

**Note:** the left-rail is NOT inside the QSplitter — it is a fixed-width
sibling column to the left of the splitter. The View menu does NOT offer
a "hide left rail" action (single fixed layout, no tearing/docking — the
rail is always visible so every panel is one click away).

---

## 5. Left-Rail Button Spec

| Property | Value |
|----------|-------|
| Widget class | `QToolButton` |
| Button style | `Qt.ToolButtonStyle.ToolButtonTextUnderIcon` (icon-over-text) |
| Minimum size | **48×48 px** (`setMinimumSize(48, 48)`) — Microsoft Fluent / Apple HIG minimum touch target |
| `checkable` | `True` |
| Group | Single exclusive `QButtonGroup` |
| Icon size | **24×24 px** (`setIconSize(QSize(24, 24))`) |
| Rail width | **72 px** (`setFixedWidth(72)`) — fits a 48×48 button + 12 px padding either side |
| Rail collapsible | **No** — single fixed layout (View menu hides panes, not the rail) |
| Selection cue | The active button's `checked=True` state (styled by the theme) |

### Left-rail composition (8 buttons, workflow-frequency ordering)

| # | Button | Stacked pane | Icon (Qt `QStyle::SP_*`) |
|---|--------|--------------|--------------------------|
| 1 | **Motion** | `motor_panel` | `SP_MediaSkipForward` (arrow — stage jog) |
| 2 | **Acquire** | `acquisition_panel` | `SP_MediaPlay` (▶ — start a run) |
| 3 | **Stack** | `stack_panel` | `SP_ToolBarHorizontalExtensionButton` (stacked bars — z-stack) |
| 4 | **Scan** | `scan_panel` | `SP_MediaSeekForward` (waveform — galvo/ETL) |
| 5 | **Lasers** | `laser_panel` | `SP_DialogYesButton` (● — emission) |
| 6 | **Files** | `save_panel` | `SP_DialogSaveButton` (floppy — save) |
| 7 | **Past** | `past_acquisitions_panel` | `SP_DirOpenIcon` (folder — prior saves) |
| 8 | **Calibrate** | `calibration_panel` | `SP_DialogResetButton` (gear/reset — rare) |

---

## 6. Phase 9 Extension Seam

The left rail accommodates a 9th button (e.g. "Channels") without
re-architecting:

1. **Append a `QToolButton`** to the `leftRail`'s `QVBoxLayout` (insert
   before Calibrate per workflow, or append to the bottom).
2. **Add it to the exclusive `QButtonGroup`** with `id=8` (the next
   available index).
3. **Create the panel widget** following the canonical panel pattern:
   `class ChannelsPanel(QWidget)` with `self._shell`, `self.ui =
   Ui_ChannelsPanel()`, `self.ui.setupUi(self)`.
4. **Wrap it in a `QScrollArea(widgetResizable=True)`** per §1 and add
   to `stackedPanels` via `addWidget` — it lands at index 8.
5. **Apply `FieldSpecSpinBox`** to every spinbox in the new panel per §2
   (promote in Qt Designer, `applySpec(FieldSpec(...))` at construction).
6. **Wire `QSlider` pairing** selectively per §2 (only for wide-range
   coarse fields — galvo/ETL amplitude, exposure, motor travel).
7. **Audit `setMaximumSize`** per §3 — drop max==min pins except
   status-dot labels, E-stop button, left-rail width.

The `QButtonGroup.idClicked(int)` → `stackedPanels.setCurrentIndex(int)`
wiring is already in place; a new button at id=8 switches to the page at
index 8 automatically.

---

## 7. FieldSpecSpinBox Usage

Every `QDoubleSpinBox` in a panel `.ui` is promoted to
`FieldSpecSpinBox` (a `QDoubleSpinBox` subclass). The declarative
`FieldSpec` policy table drives `applySpec()` at construction:

```python
@dataclass(frozen=True)
class FieldSpec:
    unit: str  # "mm", "µm", "V", "ms", "" (dimensionless)
    decimals: int  # displayed decimals
    single_step: float  # unmodified wheel/arrow step
    page_step: float  # Ctrl/Shift page-step (stepBy override)
    minimum: float  # soft widget-layer block (HAL is the safety backstop)
    maximum: float  # soft widget-layer block
```

```python
# In the panel __init__:
for obj_name, spec in FIELD_SPECS.items():
    w = getattr(self.ui, obj_name, None)
    if w is not None and hasattr(w, "applySpec"):
        w.applySpec(spec)
```

**Wheel-gating:** `FieldSpecSpinBox.wheelEvent` ignores the wheel unless
`hasFocus()` is True (fixes the wheel-steal complaint — stock
`QAbstractSpinBox::wheelEvent` fires on hover regardless of focus).

**Page-step:** `FieldSpecSpinBox.stepBy(n)` multiplies `n` by
`page_step / single_step` when Ctrl or Shift is held.

**QSlider pairing (selective):** paired sliders are synchronized with
the spinbox; the spinbox is the authoritative input. Slider `setRange` =
spinbox `min`/`max`; slider `setSingleStep` = spinbox `page_step`
(coarse). NOT universal — doubles widget count, poor fine-range
quantization, layout pressure. Adopted ONLY for: galvo/ETL amplitude
0–10V, exposure 25–1000ms, motor travel.

**Safety boundary:** `FieldSpec` min/max are a soft widget-layer block
only. The HAL motor travel-limit validator (`config_schema.py` +
`ZaberMotor.move_absolute_position` ValueError) is the safety boundary.
Never relax HAL validators to "fix" a widget-range issue.

---

## 8. Spacing Scale

All layout margins/spacings are multiples of 4 (Qt `setContentsMargins` /
`setSpacing` integers).

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4 px | Inline icon gaps; fine inter-widget gaps inside group boxes; left-rail button internal icon↔label gap |
| sm | 8 px | Default inter-widget spacing inside group boxes; toolbar widget gaps; left-rail button vertical spacing |
| md | 16 px | Default panel-internal vertical spacing; group-box content margin; stacked-pane page margin; left-rail top/bottom padding |
| lg | 24 px | Section padding between group boxes within a panel; E-stop toolbar internal padding; left-rail group separator gap |
| xl | 32 px | Pane-level gap (the `QSplitter` handle provides this visually — do not add a separate margin) |

**Exceptions (existing — preserve, do not "normalize"):**
- `QSplitter` handle width = **5 px** (a handle, not a gap).
- `imagesPane` right margin = **6 px** (visual separator from the splitter handle).
- Motor-panel step buttons = **60×60 px** minimum (touch-style target for stage jog).
- Left-rail width = **72 px** (fixed — fits a 48×48 button + 12 px padding).
- Left-rail button size = **48×48 px** minimum (touch target; on the 8-multiple, not 4).

---

## 9. Safety-Critical Invariant (load-bearing)

> The E-stop kill path (`pushButton_estop` + F12 `QShortcut`
> (ApplicationShortcut) → `estop_event.set()` →
> `for laser in self.lasers: laser.off()` on the GUI thread) stays
> **synchronous, lock-free, and in the thin shell** — never in a panel,
> never offloaded to a queue/thread. The `ILaser.off()` contract (returns
> `None` immediately, no thread/queue offload) is preserved verbatim.
> The frozen `DeviceBundle` is untouched. The motor travel-limit
> backstop (HAL) stays the safety boundary. No pyqtgraph.

The E-stop button stays in a fixed non-dockable toolbar (`toolBar_estop`,
`movable=False`, `floatable=False`). Safety-semantic per-widget
stylesheets (E-stop red, laser status green/gray/red, LevelsBar
grayscale) intentionally bypass the app stylesheet — they are NOT themed.

**Any new panel MUST NOT** move laser-off logic off the GUI thread, weaken
the kill path, or relax the HAL travel-limit validators.
