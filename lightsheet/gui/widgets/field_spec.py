"""Declarative FieldSpec policy table for the FieldSpecSpinBox subclass.

A ``FieldSpec`` is a frozen dataclass describing the per-field display
contract (unit, decimals, single/page step, soft min/max) for one
``QDoubleSpinBox`` in a panel ``.ui`` file. ``FIELD_SPECS`` is the canonical
table keyed by widget ``objectName``.

The ``minimum``/``maximum`` values are a SOFT widget-layer block only. The
HAL motor travel-limit validator is the safety boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lightsheet.config import cfg_read


@dataclass(frozen=True)
class FieldSpec:
    """Per-field display contract for a promoted ``FieldSpecSpinBox``."""

    unit: str  # "mm", "µm", "V", "ms", "µs", "" (dimensionless)
    decimals: int  # displayed decimals
    single_step: float  # unmodified wheel/arrow step
    page_step: float  # Ctrl/Shift page-step (stepBy override)
    minimum: float  # soft widget-layer block (HAL is the safety backstop)
    maximum: float  # soft widget-layer block


# Load motor travel limits from config.ini so the soft widget ranges match
# the rig's physical boundaries. Fallback values are the nominal limits.
_MOTOR_DEFAULTS = {
    "Vertical Limit Low": "0.0",
    "Vertical Limit High": "41.0",
    "Horizontal Limit Low": "0.0",
    "Horizontal Limit High": "18.8",
    "Camera Limit Low": "0.0",
    "Camera Limit High": "35.0",
}
_motor_cfg = cfg_read(
    str(Path(__file__).resolve().parents[3] / "config.ini"),
    "Motors",
    _MOTOR_DEFAULTS,
)
_MOTOR_H_MIN = float(_motor_cfg["Horizontal Limit Low"])
_MOTOR_H_MAX = float(_motor_cfg["Horizontal Limit High"])
_MOTOR_V_MIN = float(_motor_cfg["Vertical Limit Low"])
_MOTOR_V_MAX = float(_motor_cfg["Vertical Limit High"])
_MOTOR_CAM_MIN = float(_motor_cfg["Camera Limit Low"])
_MOTOR_CAM_MAX = float(_motor_cfg["Camera Limit High"])


# Canonical FieldSpec entries — per-field fixed units. Do NOT change
# unit/min/max here without re-affirming against the rig's physical ranges.
FIELD_SPECS: dict[str, FieldSpec] = {
    # Motion panel — motor positions (mm) + step sizes (mm). 2 decimals
    # (0.01 mm = 10 µm) is enough for manual control; the µm precision
    # matters only for the automatic stack plane step, not for jogging.
    "doubleSpinBox_sampleSetHPosition": FieldSpec(
        "mm", 2, 0.1, 1.0, _MOTOR_H_MIN, _MOTOR_H_MAX
    ),
    "doubleSpinBox_sampleSetVPosition": FieldSpec(
        "mm", 2, 0.1, 1.0, _MOTOR_V_MIN, _MOTOR_V_MAX
    ),
    "doubleSpinBox_cameraSetPosition": FieldSpec(
        "mm", 2, 0.1, 1.0, _MOTOR_CAM_MIN, _MOTOR_CAM_MAX
    ),
    "doubleSpinBox_sampleHStepSize": FieldSpec("mm", 2, 0.01, 0.1, 0.0, 5.0),
    "doubleSpinBox_sampleVStepSize": FieldSpec("mm", 2, 0.01, 0.1, 0.0, 5.0),
    "doubleSpinBox_cameraStepSize": FieldSpec("mm", 2, 0.01, 0.1, 0.0, 5.0),
    # Stack panel — first/last plane (mm, motor H travel) + plane step (µm).
    # Plane positions use 2 decimals (manual control); the plane step keeps
    # µm precision (2 decimals in µm = 0.01 µm) for thin-section stacks.
    "doubleSpinBox_acqFirstPlane": FieldSpec(
        "mm", 2, 0.1, 1.0, _MOTOR_H_MIN, _MOTOR_H_MAX
    ),
    "doubleSpinBox_acqLastPlane": FieldSpec(
        "mm", 2, 0.1, 1.0, _MOTOR_H_MIN, _MOTOR_H_MAX
    ),
    "doubleSpinBox_acqPlaneStepSize": FieldSpec("µm", 2, 0.5, 6.5, 0.0, 25000.0),
    # Scan panel — ETL amplitudes/offsets (V, 0-5V) + ETL steps (dimensionless)
    "doubleSpinBox_etlLeftAmplitude": FieldSpec("V", 2, 0.05, 0.5, 0.0, 5.0),
    "doubleSpinBox_etlRightAmplitude": FieldSpec("V", 2, 0.05, 0.5, 0.0, 5.0),
    "doubleSpinBox_etlLeftOffset": FieldSpec("V", 2, 0.05, 0.5, 0.0, 5.0),
    "doubleSpinBox_etlRightOffset": FieldSpec("V", 2, 0.05, 0.5, 0.0, 5.0),
    "doubleSpinBox_etlSteps": FieldSpec("", 0, 1, 10, 0, 1000),
    # Scan panel — galvo amplitudes (V, 0-10V) + offsets (V, ±10V)
    "doubleSpinBox_galvoLeftAmplitude": FieldSpec("V", 2, 0.05, 0.5, 0.0, 10.0),
    "doubleSpinBox_galvoRightAmplitude": FieldSpec("V", 2, 0.05, 0.5, 0.0, 10.0),
    "doubleSpinBox_galvoLeftOffset": FieldSpec("V", 2, 0.05, 0.5, -10.0, 10.0),
    "doubleSpinBox_galvoRightOffset": FieldSpec("V", 2, 0.05, 0.5, -10.0, 10.0),
    # Acquisition panel — camera timing (ms / µs) + line counts (dimensionless)
    "doubleSpinBox_cameraExposureTime": FieldSpec("ms", 0, 1, 10, 25, 1000),
    "doubleSpinBox_cameraLineTime": FieldSpec("µs", 0, 1, 10, 1, 100000),
    "doubleSpinBox_cameraExposedLines": FieldSpec("", 0, 1, 100, 0, 4096),
    "doubleSpinBox_cameraDelayLines": FieldSpec("", 0, 1, 100, 0, 4096),
    # Lasers panel — amplitudes (%, 0-100)
    "doubleSpinBox_laserOneAmplitude": FieldSpec("%", 1, 1.0, 10.0, 0.0, 100.0),
    "doubleSpinBox_laserTwoAmplitude": FieldSpec("%", 1, 1.0, 10.0, 0.0, 100.0),
    # Stack panel — adaptive config group (13 enumerated spinboxes). The
    # exposure bound unit is shutter-mode-dependent (ms in Rolling / lines
    # in Lightsheet) and swapped at runtime. The power bound maximum is
    # narrowed at runtime to min(150.0, live laser max_power).
    "doubleSpinBox_adaptiveMinExposure": FieldSpec("ms", 0, 1, 10, 1, 10000),
    "doubleSpinBox_adaptiveMaxExposure": FieldSpec("ms", 0, 1, 100, 1, 10000),
    "doubleSpinBox_adaptiveLaser1MinPower": FieldSpec("mW", 1, 0.5, 5.0, 0.0, 150.0),
    "doubleSpinBox_adaptiveLaser1MaxPower": FieldSpec("mW", 1, 0.5, 5.0, 0.0, 150.0),
    "doubleSpinBox_adaptiveLaser2MinPower": FieldSpec("mW", 1, 0.5, 5.0, 0.0, 150.0),
    "doubleSpinBox_adaptiveLaser2MaxPower": FieldSpec("mW", 1, 0.5, 5.0, 0.0, 150.0),
    # Stack panel — focus compensation group
    "doubleSpinBox_focusBlockSize": FieldSpec("", 0, 1, 5, 1, 100),
    # Stack panel — predictive adaptive-autofocus group
    "doubleSpinBox_autofocusCadence": FieldSpec("", 0, 1, 5, 1, 1000),
    "doubleSpinBox_autofocusResidualGain": FieldSpec("mm", 3, 0.01, 0.1, 0.0, 1.0),
    "doubleSpinBox_autofocusMaxResidual": FieldSpec("mm", 3, 0.05, 0.1, 0.0, 5.0),
    "doubleSpinBox_autofocusSmoothing": FieldSpec("", 2, 0.05, 0.1, 0.0, 1.0),
}

# Author-supplied one-line purpose per field, used by FieldSpecSpinBox
# .applySpec() to generate the tooltip.
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
    # Stack panel — adaptive config group
    "doubleSpinBox_adaptiveMinExposure": "Adaptive min exposure bound",
    "doubleSpinBox_adaptiveMaxExposure": "Adaptive max exposure bound",
    "doubleSpinBox_adaptiveLaser1MinPower": "Adaptive laser 1 min power bound",
    "doubleSpinBox_adaptiveLaser1MaxPower": "Adaptive laser 1 max power bound",
    "doubleSpinBox_adaptiveLaser2MinPower": "Adaptive laser 2 min power bound",
    "doubleSpinBox_adaptiveLaser2MaxPower": "Adaptive laser 2 max power bound",
    # Stack panel — focus compensation group
    "doubleSpinBox_focusBlockSize": "Focus compensation block size (planes)",
    # Stack panel — predictive adaptive-autofocus group. Each purpose leads
    # with the exact on-widget label text so tooltips and labels stay in sync.
    "doubleSpinBox_autofocusCadence": (
        "Update cadence (planes) — autofocus residual re-evaluated every N planes"
    ),
    "doubleSpinBox_autofocusResidualGain": (
        "Residual gain (mm) — autofocus residual step applied per update"
    ),
    "doubleSpinBox_autofocusMaxResidual": (
        "Max residual (mm) — autofocus residual clamp bound"
    ),
    "doubleSpinBox_autofocusSmoothing": (
        "Smoothing — autofocus EMA learning rate for the reference sharpness"
    ),
}
