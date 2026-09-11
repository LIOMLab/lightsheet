"""Branch-coverage tests for ``lightsheet/gui/coordinators/save_manifest.py``.

Covers the defensive edge paths the golden manifest-lifecycle fixture does
not reach (the golden harness drives the happy path only):

- ``init_manifest`` — non-str ``save_filepath`` coerced to "", non-int /
  bool ``stack_queue_row_index`` coerced to None, and a
  ``collect_safety_config`` failure degrading to an empty fingerprint
  (the manifest still mints — a fingerprint failure must not abort the
  save).
- ``drain_updates`` — a staged update with ``resume_manifest is None``
  is skipped (the queue still drains).
- ``commit_cursor`` / ``finalize`` — manifest write failures are logged
  and swallowed (the image data is already durable; a stale cursor
  resumes into a re-acquire, never a skip).

The saver is a ``SimpleNamespace`` stub carrying only the manifest state
attributes — ``ManifestRecorder`` is a plain-Python collaborator that
reads/writes ``self._saver.*`` and never touches Qt or HAL.
"""

from __future__ import annotations

import datetime
import queue
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from lightsheet.gui.coordinators.save_manifest import ManifestRecorder
from lightsheet.resume.manifest import ResumeManifest


def _make_saver(tmp_path: Path, **parent_attrs: Any) -> SimpleNamespace:
    """A minimal FrameSaver stand-in with the manifest state attrs."""
    parent = SimpleNamespace(save_filepath="", stack_queue_row_index=None)
    for key, value in parent_attrs.items():
        setattr(parent, key, value)
    return SimpleNamespace(
        filenames_lists=[[str(tmp_path / "acq.hdf5")]],
        datasets_name="reconstructed_frame",
        number_of_files=1,
        number_of_datasets=1,
        parent=parent,
        manifest_update_queue=queue.Queue(),
        resume_manifest=None,
        acquisition_uuid="",
        _manifest_path=None,
        _coerce_shell_float=lambda _name: 0.0,
    )


def _real_manifest() -> ResumeManifest:
    """A minimal valid in-progress manifest for the write-failure paths."""
    return ResumeManifest(
        uuid="deadbeef",
        state="in_progress",
        n_planes=10,
        stack_starting_plane=0.0,
        stack_ending_plane=1.0,
        stack_step=0.1,
        save_mode="stitch",
        created_at=datetime.datetime.now(datetime.UTC).isoformat(),
    )


def test_init_manifest_coerces_non_str_save_filepath_and_non_int_row(
    tmp_path: Path,
) -> None:
    """A non-str parent.save_filepath is coerced to "" and a non-int
    stack_queue_row_index to None — a minimal shell stand-in leaves the
    operator-intent fields absent instead of crashing the save."""
    saver = _make_saver(
        tmp_path, save_filepath=12345, stack_queue_row_index="not-an-int"
    )
    recorder = ManifestRecorder(saver)  # ty: ignore[invalid-argument-type]
    recorder.init_manifest([555])
    assert saver.resume_manifest is not None
    assert saver.resume_manifest.save_filepath == ""
    assert saver.resume_manifest.row_index is None
    # The sidecar was written next to the resolved channel-0 file.
    assert (tmp_path / "acq.resume.json").exists()


def test_init_manifest_safety_config_failure_degrades_to_empty(
    tmp_path: Path,
) -> None:
    """A collect_safety_config failure is logged and the manifest mints
    with an empty fingerprint — the resume gate then takes its
    key-absent path rather than the save aborting."""
    saver = _make_saver(tmp_path)
    recorder = ManifestRecorder(saver)  # ty: ignore[invalid-argument-type]
    with patch(
        "lightsheet.resume.gate.collect_safety_config",
        side_effect=RuntimeError("config unreadable"),
    ):
        recorder.init_manifest([555])
    assert saver.resume_manifest is not None
    assert saver.resume_manifest.safety_config == {}


def test_init_manifest_records_valid_int_row_index(tmp_path: Path) -> None:
    """A real int stack_queue_row_index is recorded on the manifest —
    the ``isinstance(row_index, int)`` true arc complements the
    non-int coercion test above."""
    saver = _make_saver(tmp_path, stack_queue_row_index=3)
    recorder = ManifestRecorder(saver)  # ty: ignore[invalid-argument-type]
    recorder.init_manifest([555])
    assert saver.resume_manifest is not None
    assert saver.resume_manifest.row_index == 3


def test_drain_updates_skips_apply_when_manifest_is_none(tmp_path: Path) -> None:
    """A staged update with resume_manifest None is dropped — the queue
    still drains to empty (the `is not None` false branch)."""
    saver = _make_saver(tmp_path)
    saver.manifest_update_queue.put(object())
    recorder = ManifestRecorder(saver)  # ty: ignore[invalid-argument-type]
    recorder.drain_updates()  # must not raise
    assert saver.manifest_update_queue.empty()


def test_commit_cursor_write_failure_is_logged(tmp_path: Path) -> None:
    """An OSError on the cursor-commit write is logged and swallowed —
    the image data is already durable and a stale cursor resumes into
    a re-acquire, never a skip."""
    saver = _make_saver(tmp_path)
    saver.resume_manifest = _real_manifest()
    saver._manifest_path = tmp_path / "acq.resume.json"
    recorder = ManifestRecorder(saver)  # ty: ignore[invalid-argument-type]
    with patch(
        "lightsheet.gui.coordinators.save_manifest.write_manifest",
        side_effect=OSError("disk full"),
    ):
        recorder.commit_cursor("hdf5", str(tmp_path / "acq.hdf5"), 3)


def test_finalize_write_failure_is_logged(tmp_path: Path) -> None:
    """A failure on the final manifest write is logged and swallowed —
    finalize runs at teardown where raising would mask the real exit."""
    saver = _make_saver(tmp_path)
    saver.resume_manifest = _real_manifest()
    saver._manifest_path = tmp_path / "acq.resume.json"
    recorder = ManifestRecorder(saver)  # ty: ignore[invalid-argument-type]
    with patch(
        "lightsheet.gui.coordinators.save_manifest.write_manifest",
        side_effect=RuntimeError("teardown write failed"),
    ):
        recorder.finalize()  # must not raise


def test_commit_cursor_noop_without_manifest(tmp_path: Path) -> None:
    """With no live manifest/path the cursor commit is a no-op — the
    early return before drain_updates."""
    saver = _make_saver(tmp_path)
    saver.resume_manifest = None
    saver._manifest_path = None
    saver.manifest_update_queue = Mock()
    recorder = ManifestRecorder(saver)  # ty: ignore[invalid-argument-type]
    recorder.commit_cursor("hdf5", "key", 1)
    saver.manifest_update_queue.get_nowait.assert_not_called()
