"""Plane-count / time / size estimation for ``AcquisitionTableManager``.

Module-level functions taking the table manager (``mgr``) as their first
parameter — the same shape as the module-level
``show_resume_safety_dialog`` in ``acquisition_table_manager.py`` and the
``queue_resume`` sibling module. The manager keeps thin delegate methods
under the original method names so ``row_at``, ``add_stack``,
``_insert_row_at``, ``_on_cell_changed``, the save-format radio wiring,
and every existing call site resolve unchanged.

The estimates are advisory: they guide the operator's queue-depth and
storage decisions at planning time. Every hardware/UI read is
``getattr``-guarded with a warning + fallback so a missing panel or
camera degrades the label, never crashes the table.
"""

from __future__ import annotations

import logging
import math
import typing

from lightsheet.gui.styles import colors as _c

if typing.TYPE_CHECKING:
    from lightsheet.gui.panels.acquisition_table_manager import (
        AcquisitionTableManager,
    )

logger = logging.getLogger(__name__)


def compute(
    mgr: AcquisitionTableManager, start: float, end: float, step: float
) -> tuple[int, float, float]:
    """Compute (#planes, est. time s, est. size MB) for a row."""
    if step <= 0 or start == end:
        return 0, 0.0, 0.0
    n_planes = math.floor(abs((end - start) / step)) + 1
    per_plane_s = estimate_per_plane_time(mgr)
    est_time_s = n_planes * per_plane_s
    est_size_mb = estimate_stack_size_mb(mgr, n_planes)
    return n_planes, est_time_s, est_size_mb


def estimate_per_plane_time(mgr: AcquisitionTableManager) -> float:
    """Advisory per-plane acquisition time in seconds."""
    try:
        exposure = float(
            mgr._shell.acquisition_panel.ui.doubleSpinBox_cameraExposureTime.value()
        )
        return exposure / 1000.0 * 1.5
    except (AttributeError, ValueError, TypeError) as e:
        logger.warning(
            "Failed to read camera exposure time; using default 0.5 s/plane: %s", e
        )
        return 0.5


def estimate_stack_size_mb(mgr: AcquisitionTableManager, n_planes: int) -> float:
    """Advisory stack size in MB, format-aware.

    - ``hdf5``: raw bytes — ``rows * cols * 2 * n_planes`` (uint16),
      unchanged from the pre-format-aware behavior. Any unknown format
      value also falls back to this estimate.
    - ``zarr``: raw L0 bytes plus the multiscale pyramid overhead.
      The pyramid level count is stack_step-dependent: count the
      targets in ``(10, 25, 50, 100)`` µm that are ``>= max(base_res)``
      where ``base_res = (abs(stack_step), 6.5*binning_x,
      6.5*binning_y)`` — the same target-validity filter the writer's
      ``finalize_with_resolutions`` applies (so the estimate tracks
      the real on-disk pyramid, NOT a hardcoded level count). Each
      downsampled level is ~1/4 of the previous (2x Y/X downsample),
      so the total pyramid overhead is
      ``L0 * sum(0.25**i for i in range(level_count))``.
    - ``both``: ``hdf5_estimate + zarr_estimate`` (sum).
    """
    try:
        # The camera HAL exposes ysize/xsize (not rows/columns);
        # reading the wrong attrs always fell back to 2000x2000,
        # making the estimate wrong for any non-2000x2000 camera.
        rows = int(getattr(mgr._shell.camera, "ysize", 2000) or 2000)
        cols = int(getattr(mgr._shell.camera, "xsize", 2000) or 2000)
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning(
            "Failed to read camera ysize/xsize; "
            "falling back to 2000x2000 for size estimate: %s",
            e,
        )
        rows, cols = 2000, 2000
    bytes_per_frame = rows * cols * 2
    l0_bytes = n_planes * bytes_per_frame
    l0_mb = l0_bytes / (1024.0 * 1024.0)

    fmt = str(getattr(mgr._shell, "save_format", "hdf5")).lower()
    if fmt == "zarr":
        return l0_mb * zarr_pyramid_multiplier(mgr)
    if fmt == "both":
        return l0_mb + l0_mb * zarr_pyramid_multiplier(mgr)
    # hdf5 / unknown -> raw bytes.
    return l0_mb


def zarr_pyramid_multiplier(mgr: AcquisitionTableManager) -> float:
    """Total-size multiplier for the OME-Zarr pyramid relative to L0.

    The level count is derived from the live ``base_res`` (Z from
    ``stack_step``, XY from the camera binning) using the writer's
    target-validity filter: a target resolution is kept only if
    ``target_um >= max(base_res)``. Each retained level is ~1/4 of
    the previous (2x Y/X downsample), so the geometric sum
    ``sum(0.25**i for i in range(level_count))`` is the overhead
    factor on top of L0 (level 0 contributes 1.0).
    """
    try:
        stack_step = float(getattr(mgr._shell, "stack_step", 0.0))
    except (TypeError, ValueError) as e:
        logger.warning(
            "Failed to parse stack_step; disabling Zarr pyramid overhead estimate: %s",
            e,
        )
        stack_step = 0.0
    cam = getattr(mgr._shell, "camera", None)
    binning_x = int(getattr(cam, "binning_x", 1) or 1)
    binning_y = int(getattr(cam, "binning_y", 1) or 1)
    base_res = (abs(stack_step), 6.5 * binning_x, 6.5 * binning_y)
    max_res = max(base_res)
    level_count = sum(1 for t in (10, 25, 50, 100) if t >= max_res)
    # Level 0 (raw) is always present and each retained target adds one
    # downsampled level at ~0.25**i of L0, so the on-disk pyramid has
    # 1 + level_count levels and the multiplier can never be 0 — when no
    # target is reachable (stack_step above 100 µm or binning >= 16 ->
    # level_count == 0) the writer still produces the L0 array.
    return sum(0.25**i for i in range(1 + level_count))


def format_size_human_readable(mb: float, fmt: str) -> str:
    """Format an MB value as a human-readable string with a format
    suffix: ``>=1024 GB`` -> TB, ``>=1024 MB`` -> GB, else MB. One
    decimal place. ``fmt`` is the uppercase label (``"HDF5"`` /
    ``"OME-Zarr"`` / ``"Both"``)."""
    if mb >= 1024.0 * 1024.0:
        return f"{mb / 1024.0 / 1024.0:.1f} TB ({fmt})"
    if mb >= 1024.0:
        return f"{mb / 1024.0:.1f} GB ({fmt})"
    return f"{mb:.1f} MB ({fmt})"


def format_label(mgr: AcquisitionTableManager) -> str:
    """Map ``mgr._shell.save_format`` to the uppercase suffix label
    used in the Est. Size cell."""
    fmt = str(getattr(mgr._shell, "save_format", "hdf5")).lower()
    if fmt == "zarr":
        return "OME-Zarr"
    if fmt == "both":
        return "Both"
    return "HDF5"


def recompute_all_rows(mgr: AcquisitionTableManager) -> None:
    """Re-estimate every planned-queue row's Est. Size cell.

    Subscribed to the save-format radio group's ``buttonClicked``
    signal (wired in the controller): when the operator switches
    format, every row's size estimate is re-computed against the new
    format so the format-dependence is visible at planning time. Uses
    the existing ``_recomputing`` re-entrancy guard so the per-row
    ``setItem`` calls do not re-trigger ``cellChanged``.
    """
    if mgr._recomputing:
        return
    mgr._recomputing = True
    try:
        for i in range(mgr.table.rowCount()):
            recompute_row_impl(mgr, i)
    finally:
        mgr._recomputing = False


def recompute_row(mgr: AcquisitionTableManager, row: int) -> None:
    """Recompute #planes/est.time/est.size for a row + validate
    start/end against the motor travel limits. Flag incomplete or
    out-of-range cells with a red background."""
    if mgr._recomputing:
        return
    mgr._recomputing = True
    try:
        recompute_row_impl(mgr, row)
    finally:
        mgr._recomputing = False


def recompute_row_impl(mgr: AcquisitionTableManager, row: int) -> None:
    # Local import: the column constants live in the manager module,
    # which imports this module for its delegates — a module-level
    # import would be circular.
    from lightsheet.gui.panels.acquisition_table_manager import (
        _COL_END,
        _COL_ESTSIZE,
        _COL_ESTTIME,
        _COL_NAME,
        _COL_NPLANES,
        _COL_START,
        _COL_STEP,
    )

    # Parse each editable numeric cell, flagging empty or non-numeric
    # text (e.g. "", "abc", "1.0.0") instead of crashing on every
    # keystroke. _safe_float returns 0.0 for unparseable text; the
    # flag below surfaces the bad cell to the operator so they can fix
    # it. Guard missing items (None) so a partially-populated row does
    # not raise AttributeError.
    start_item = mgr.table.item(row, _COL_START)
    end_item = mgr.table.item(row, _COL_END)
    step_item = mgr.table.item(row, _COL_STEP)
    start_text = start_item.text() if start_item is not None else ""
    end_text = end_item.text() if end_item is not None else ""
    step_text = step_item.text() if step_item is not None else ""
    bad_parses: set[int] = set()
    start = mgr._parse_or_flag(row, _COL_START, start_text, bad_parses)
    end = mgr._parse_or_flag(row, _COL_END, end_text, bad_parses)
    step = mgr._parse_or_flag(row, _COL_STEP, step_text, bad_parses)
    # Start/End cells display in mm; convert to µm for the plane-count
    # computation + limit check (the step cell is already µm, so all
    # three must share the µm unit inside compute).
    start_um = start * 1000.0
    end_um = end * 1000.0
    n_planes, est_time_s, est_size_mb = compute(mgr, start_um, end_um, step)

    mgr.table.blockSignals(True)
    mgr._set_readonly_cell(row, _COL_NPLANES, str(n_planes))
    mm, ss = divmod(int(est_time_s), 60)
    mgr._set_readonly_cell(row, _COL_ESTTIME, f"{mm}:{ss:02d}")
    mgr._set_readonly_cell(
        row,
        _COL_ESTSIZE,
        format_size_human_readable(est_size_mb, format_label(mgr)),
    )
    # Update the name tooltip in case the name was edited.
    name_item = mgr.table.item(row, _COL_NAME)
    if name_item is not None:
        name_item.setToolTip(name_item.text())
    mgr.table.blockSignals(False)

    # Clear flags then re-validate.
    mgr.table.blockSignals(True)
    for col in range(mgr.table.columnCount()):
        mgr._flagged_cells.discard((row, col))
        item = mgr.table.item(row, col)
        if item is not None:
            item.setBackground(_c.Q_FLAG_NORMAL)
    mgr.table.blockSignals(False)

    flagged = False
    # Bad parses (empty or non-numeric) survive the re-validation pass.
    for col in bad_parses:
        mgr._flag(row, col)
        flagged = True
    # Incomplete: start == end or step <= 0.
    if step <= 0:
        mgr._flag(row, _COL_STEP)
        flagged = True
    if start == end:
        mgr._flag(row, _COL_START)
        mgr._flag(row, _COL_END)
        flagged = True
    # Out-of-range: start/end outside the motor travel limits.
    motors = getattr(mgr._shell, "motors", None)
    if motors is not None:
        try:
            low = float(motors.horizontal.get_limit_low("\u03bcm"))
            high = float(motors.horizontal.get_limit_high("\u03bcm"))
        except (TypeError, ValueError, AttributeError) as e:
            logger.warning(
                "Failed to read horizontal motor limits; "
                "disabling travel-limit check: %s",
                e,
            )
            low, high = None, None
        if low is not None and high is not None:
            # start/end are mm cell values; limits are µm — compare in µm.
            if start_um < low or start_um > high:
                mgr._flag(row, _COL_START)
                flagged = True
            if end_um < low or end_um > high:
                mgr._flag(row, _COL_END)
                flagged = True
    if flagged:
        mgr._shell.sig_message.emit(
            f"Row {row + 1} is incomplete or out of range. "
            "Fix the highlighted cells before starting the queue."
        )
