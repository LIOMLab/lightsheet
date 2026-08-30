"""Declarative FieldSpec policy table for the FieldSpecSpinBox subclass.

A ``FieldSpec`` is a frozen dataclass describing the per-field display
contract (unit, decimals, single/page step, soft min/max) for one
``QDoubleSpinBox`` in a panel ``.ui`` file. ``FIELD_SPECS`` is the canonical
table keyed by widget ``objectName`` — the 24 entries below are copied
verbatim from the UI-SPEC FieldSpec Policy Table.

The ``minimum``/``maximum`` values are a SOFT widget-layer block only. The
HAL motor travel-limit validator (``config_schema.py`` +
``ZaberMotor.move_absolute_position`` ``ValueError``) is the safety
boundary. The subclass never relaxes any HAL validator.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    """Per-field display contract for a promoted ``FieldSpecSpinBox``.

    Fields are ordered to match the UI-SPEC dataclass shape exactly:
    ``unit`` first (drives the suffix), then numeric display/step/range.
    """

    unit: str  # "mm", "µm", "V", "ms", "µs", "" (dimensionless)
    decimals: int  # displayed decimals
    single_step: float  # unmodified wheel/arrow step
    page_step: float  # Ctrl/Shift page-step (stepBy override)
    minimum: float  # soft widget-layer block (HAL is the safety backstop)
    maximum: float  # soft widget-layer block


# Canonical FieldSpec entries — per-field fixed units (UI-SPEC §FieldSpec
# Policy Table). The 24 objectName keys are the widgets promoted to
# FieldSpecSpinBox in the panel .ui files. Do NOT change unit/min/max here
# without re-affirming against the rig's physical ranges; the HAL is the
# safety backstop, but the widget soft-block should still match the rig.
FIELD_SPECS: dict[str, FieldSpec] = {
    # Motion panel — motor positions (mm) + step sizes (mm). 2 decimals
    # (0.01 mm = 10 µm) is enough for manual control; the µm precision
    # matters only for the automatic stack plane step, not for jogging.
    "doubleSpinBox_sampleSetHPosition": FieldSpec("mm", 2, 0.1, 1.0, 0.0, 41.0),
    "doubleSpinBox_sampleSetVPosition": FieldSpec("mm", 2, 0.1, 1.0, 0.0, 18.8),
    "doubleSpinBox_cameraSetPosition": FieldSpec("mm", 2, 0.1, 1.0, 0.0, 35.0),
    "doubleSpinBox_sampleHStepSize": FieldSpec("mm", 2, 0.01, 0.1, 0.0, 5.0),
    "doubleSpinBox_sampleVStepSize": FieldSpec("mm", 2, 0.01, 0.1, 0.0, 5.0),
    "doubleSpinBox_cameraStepSize": FieldSpec("mm", 2, 0.01, 0.1, 0.0, 5.0),
    # Stack panel — first/last plane (mm, motor H travel) + plane step (µm).
    # Plane positions use 2 decimals (manual control); the plane step keeps
    # µm precision (2 decimals in µm = 0.01 µm) for thin-section stacks.
    "doubleSpinBox_acqFirstPlane": FieldSpec("mm", 2, 0.1, 1.0, 0.0, 41.0),
    "doubleSpinBox_acqLastPlane": FieldSpec("mm", 2, 0.1, 1.0, 0.0, 41.0),
    "doubleSpinBox_acqPlaneStepSize": FieldSpec("µm", 2, 0.5, 5.0, 0.0, 25000.0),
    # Scan panel — ETL amplitudes/offsets (V, 0–5V) + ETL steps (dimensionless)
    "doubleSpinBox_etlLeftAmplitude": FieldSpec("V", 2, 0.05, 0.5, 0.0, 5.0),
    "doubleSpinBox_etlRightAmplitude": FieldSpec("V", 2, 0.05, 0.5, 0.0, 5.0),
    "doubleSpinBox_etlLeftOffset": FieldSpec("V", 2, 0.05, 0.5, 0.0, 5.0),
    "doubleSpinBox_etlRightOffset": FieldSpec("V", 2, 0.05, 0.5, 0.0, 5.0),
    "doubleSpinBox_etlSteps": FieldSpec("", 0, 1, 10, 0, 1000),
    # Scan panel — galvo amplitudes (V, 0–10V) + offsets (V, ±10V)
    "doubleSpinBox_galvoLeftAmplitude": FieldSpec("V", 2, 0.05, 0.5, 0.0, 10.0),
    "doubleSpinBox_galvoRightAmplitude": FieldSpec("V", 2, 0.05, 0.5, 0.0, 10.0),
    "doubleSpinBox_galvoLeftOffset": FieldSpec("V", 2, 0.05, 0.5, -10.0, 10.0),
    "doubleSpinBox_galvoRightOffset": FieldSpec("V", 2, 0.05, 0.5, -10.0, 10.0),
    # Acquisition panel — camera timing (ms / µs) + line counts (dimensionless)
    "doubleSpinBox_cameraExposureTime": FieldSpec("ms", 0, 1, 10, 25, 1000),
    "doubleSpinBox_cameraLineTime": FieldSpec("µs", 0, 1, 10, 1, 100000),
    "doubleSpinBox_cameraExposedLines": FieldSpec("", 0, 1, 100, 0, 4096),
    "doubleSpinBox_cameraDelayLines": FieldSpec("", 0, 1, 100, 0, 4096),
    # Lasers panel — amplitudes (%, 0–100)
    "doubleSpinBox_laserOneAmplitude": FieldSpec("%", 1, 1.0, 10.0, 0.0, 100.0),
    "doubleSpinBox_laserTwoAmplitude": FieldSpec("%", 1, 1.0, 10.0, 0.0, 100.0),
}

# Author-supplied one-line purpose per field, used by FieldSpecSpinBox
# .applySpec() to generate the UI-SPEC §Tooltips (D-02) tooltip:
# ``{field purpose}. Unit: {unit}. Range: {min}–{max} {unit}. Step: …
# (Ctrl/Shift = …). Wheel: click in first to scroll.`` The purpose is the
# only author-supplied part; the rest is generated from the FieldSpec.
FIELD_PURPOSES: dict[str, str] = {
    # Motion panel
    "doubleSpinBox_sampleSetHPosition": "Horizontal stage position",
    "doubleSpinBox_sampleSetVPosition": "Vertical stage position",
    "doubleSpinBox_cameraSetPosition": "Camera focus stage position",
    "doubleSpinBox_sampleHStepSize": "Horizontal stage jog step size",
    "doubleSpinBox_sampleVStepSize": "Vertical stage jog step size",
    "doubleSpinBox_cameraStepSize": "Camera stage jog step size",
    # Stack panel
    "doubleSpinBox_acqFirstPlane": "Stack first plane position",
    "doubleSpinBox_acqLastPlane": "Stack last plane position",
    "doubleSpinBox_acqPlaneStepSize": "Stack plane step size",
    # Scan panel — ETL
    "doubleSpinBox_etlLeftAmplitude": "ETL left amplitude",
    "doubleSpinBox_etlRightAmplitude": "ETL right amplitude",
    "doubleSpinBox_etlLeftOffset": "ETL left offset",
    "doubleSpinBox_etlRightOffset": "ETL right offset",
    "doubleSpinBox_etlSteps": "ETL steps per scan cycle",
    # Scan panel — galvo
    "doubleSpinBox_galvoLeftAmplitude": "Galvo left amplitude",
    "doubleSpinBox_galvoRightAmplitude": "Galvo right amplitude",
    "doubleSpinBox_galvoLeftOffset": "Galvo left offset",
    "doubleSpinBox_galvoRightOffset": "Galvo right offset",
    # Acquisition panel — camera timing
    "doubleSpinBox_cameraExposureTime": "Camera exposure time",
    "doubleSpinBox_cameraLineTime": "Camera line time",
    "doubleSpinBox_cameraExposedLines": "Camera exposed lines per line time",
    "doubleSpinBox_cameraDelayLines": "Camera delay lines per line time",
    # Lasers panel
    "doubleSpinBox_laserOneAmplitude": "Laser 1 power",
    "doubleSpinBox_laserTwoAmplitude": "Laser 2 power",
}
