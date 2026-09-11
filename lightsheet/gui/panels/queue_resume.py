"""Resume-row + queue-manifest plumbing for ``AcquisitionTableManager``.

Module-level functions taking the table manager (``mgr``) as their first
parameter — the same shape as the module-level
``show_resume_safety_dialog`` in ``acquisition_table_manager.py``. The
manager keeps thin delegate methods under the original method names so
``_start_queue``, the past-acquisitions browser, and every existing call
site resolve unchanged.

The resume safety contract moves verbatim with the code: these functions
never start hardware — the safety gate and the report-then-confirm
dialog run at spawn time inside ``_spawn_stack_worker``, and a
cancelled/blocked resume moves nothing.
"""

from __future__ import annotations

import logging
import math
import typing
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidgetItem

from lightsheet.gui.styles import colors as _c
from lightsheet.gui.styles import typography as _t
from lightsheet.resume import (
    QueueResumeManifest,
    hash_queue_rows,
    read_manifest,
    read_queue_manifest,
)
from lightsheet.resume import (
    write_queue_manifest as _write_queue_manifest_file,
)

if typing.TYPE_CHECKING:
    from lightsheet.gui.panels.acquisition_table_manager import (
        AcquisitionTableManager,
        _Row,
    )

logger = logging.getLogger(__name__)


def enqueue_resume_row(
    mgr: AcquisitionTableManager,
    manifest_path: Path | str,
    queue_manifest: Path | str | None = None,
) -> bool:
    """Enqueue a flagged resume row for an interrupted acquisition.

    Reads the per-acquisition ``ResumeManifest`` and appends a row
    whose ``start_plane``/``save_filepath`` come from the manifest.
    The row is inert until Start Queue reaches it; the safety gate
    and report-then-confirm dialog run at spawn time inside
    ``_spawn_stack_worker`` — this function never starts hardware.

    When ``queue_manifest`` is given, the queue-level manifest is
    validated against the live table (T-16-07-02): a mismatch is
    rejected with an operator-visible error. On success the table
    becomes exactly ``[resume row] + remaining rows`` so Start Queue
    resumes the interrupted row and continues the rest.
    """
    # Local import: ``_Row`` lives in the manager module, which imports
    # this module for its delegates — a module-level import would be
    # circular.
    from lightsheet.gui.panels.acquisition_table_manager import _Row

    manifest = read_manifest(manifest_path)
    if manifest is None:
        mgr._shell.sig_message.emit(
            f"Cannot resume: {manifest_path} is missing, unreadable, "
            "or failed validation. The acquisition was not modified."
        )
        mgr._shell.sig_beep.emit()
        return False
    if manifest.state == "completed":
        mgr._shell.sig_message.emit(
            "Cannot resume: the acquisition already completed. "
            "The acquisition was not modified."
        )
        mgr._shell.sig_beep.emit()
        return False

    # Nominal resume plane from the committed cursors; the gate
    # recomputes the durable plane from on-disk probes at spawn time.
    cursors = [v for group in manifest.cursors.values() for v in group.values()]
    start_plane = min(cursors) if cursors else manifest.start_plane
    resume_start = manifest.stack_starting_plane + start_plane * manifest.stack_step
    if manifest.save_filepath:
        base_name = Path(manifest.save_filepath).name
    else:
        base_name = Path(str(manifest_path)).stem.removesuffix(".resume")
    row = _Row(
        name=f"Resume: {base_name}",
        start=resume_start,
        end=manifest.stack_ending_plane,
        step=abs(manifest.stack_step),
        n_planes=manifest.n_planes,
        est_time_s=0.0,
        est_size_mb=0.0,
    )
    meta = {
        "start_plane": int(start_plane),
        "n_planes": manifest.n_planes,
        "resume_manifest": manifest,
        "save_filepath": manifest.save_filepath or "",
    }

    if queue_manifest is not None:
        return apply_queue_resume(mgr, row, meta, queue_manifest)
    mgr._insert_row_at(mgr.table.rowCount(), row, meta)
    return True


def apply_queue_resume(
    mgr: AcquisitionTableManager,
    resume_row: _Row,
    meta: dict[str, typing.Any],
    queue_manifest: Path | str,
) -> bool:
    """Validate a queue-level manifest against the live table and
    arrange ``[resume row] + remaining rows`` for execution."""
    # Local import — see enqueue_resume_row (circular-import guard).
    from lightsheet.gui.panels.acquisition_table_manager import _Row

    qm = read_queue_manifest(queue_manifest)
    if qm is None:
        mgr._shell.sig_message.emit(
            f"Cannot resume: the queue manifest {queue_manifest} is "
            "missing, unreadable, or failed validation. The "
            "acquisition was not modified."
        )
        mgr._shell.sig_beep.emit()
        return False

    remaining = qm.rows[qm.row_index + 1 :]
    live = [row_to_dict(mgr.row_at(i)) for i in range(mgr.table.rowCount())]

    if rows_match(live, qm.rows):
        # Untouched pre-crash queue: drop the completed rows and the
        # interrupted row; the resume row replaces the interrupted
        # one at the head.
        removed = min(qm.row_index + 1, mgr.table.rowCount())
        for _ in range(removed):
            mgr.table.removeRow(0)
            if mgr._row_uuids:
                mgr._row_meta.pop(mgr._row_uuids[0], None)
                del mgr._row_uuids[0]
        # Re-index the flagged-cell set: flags recorded against the
        # removed leading rows are dropped and every surviving flag
        # shifts down with its row (same contract as remove_stack).
        mgr._flagged_cells = {
            (r - removed, c) for (r, c) in mgr._flagged_cells if r >= removed
        }
        mgr._insert_row_at(0, resume_row, meta)
        return True
    if rows_match(live, remaining):
        # The table already holds exactly the remaining rows.
        mgr._insert_row_at(0, resume_row, meta)
        return True
    if not live:
        # Fresh session: rebuild the queue from the manifest.
        mgr._insert_row_at(0, resume_row, meta)
        for rd in remaining:
            row = _Row(
                name=str(rd.get("name", "Stack")),
                start=float(rd.get("start", 0.0)),
                end=float(rd.get("end", 0.0)),
                step=float(rd.get("step", 0.0)),
                n_planes=int(rd.get("n_planes", 0)),
                est_time_s=0.0,
                est_size_mb=0.0,
            )
            mgr._insert_row_at(mgr.table.rowCount(), row)
        return True

    mgr._shell.sig_message.emit(
        "Cannot resume: the queue table no longer matches "
        "the recorded queue manifest — the queue was edited after the "
        "interruption. Rebuild the queue manually and restart it. "
        "The acquisition was not modified."
    )
    mgr._shell.sig_beep.emit()
    return False


def write_queue_manifest(
    mgr: AcquisitionTableManager,
    path: Path,
    state: str,
    row_index: int,
    rows: list[dict[str, typing.Any]],
    row_uuids: list[str],
    queue_uuid: str,
    created_at: str,
) -> None:
    """Atomically (re)write the queue-level resume manifest."""
    try:
        _write_queue_manifest_file(
            path,
            QueueResumeManifest(
                uuid=queue_uuid,
                state=state,
                row_index=row_index,
                rows=rows,
                row_uuids=row_uuids,
                row_hash=hash_queue_rows(rows),
                created_at=created_at,
                save_directory=str(path.parent),
            ),
        )
    except OSError as e:
        logger.warning("could not write queue manifest %s: %s", path, e)


def row_to_dict(row: _Row) -> dict[str, typing.Any]:
    return {
        "name": row.name,
        "start": row.start,
        "end": row.end,
        "step": row.step,
        "n_planes": row.n_planes,
    }


def rows_match(a: list[dict[str, typing.Any]], b: list[dict[str, typing.Any]]) -> bool:
    if len(a) != len(b):
        return False
    for ra, rb in zip(a, b, strict=True):
        if ra.get("name") != rb.get("name"):
            return False
        for key in ("start", "end", "step"):
            try:
                if not math.isclose(float(ra[key]), float(rb[key])):
                    return False
            except (KeyError, TypeError, ValueError):
                return False
    return True


def apply_resume_row_display(
    mgr: AcquisitionTableManager, index: int, row: _Row, start_plane: int
) -> None:
    """Write the ``RESUME start/total`` marker into the #Planes cell —
    the ``is_resume`` branch of ``AcquisitionTableManager._insert_row_at``,
    which calls this while the table's signals are blocked."""
    # Local import — same circular-import guard as enqueue_resume_row.
    from lightsheet.gui.panels.acquisition_table_manager import _COL_NPLANES

    n_planes_text = f"RESUME {start_plane}/{row.n_planes}"
    item = QTableWidgetItem(n_planes_text)
    item.setFont(_t.body_font())
    item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
    item.setToolTip(f"Resuming from plane {start_plane} of {row.n_planes}")
    item.setForeground(QColor(_c.BREEZE_ACCENT))
    mgr.table.setItem(index, _COL_NPLANES, item)
