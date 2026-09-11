"""Plain-Python resume-manifest collaborator for ``FrameSaver``.

Owns the ``.resume.json`` sidecar lifecycle plumbing moved out of
``frame_saver_controller.py``: initial manifest minting (fresh and
resumed runs), the cross-thread ``manifest_update_queue`` drain, the
durable cursor commit, and the race-free final write.

This is NOT a ``QObject`` — it mirrors the ``ZarrSaver`` collaborator
pattern: the constructor takes the owning ``FrameSaver`` and holds it as
``self._saver``. It never owns HAL handles; the shell is reached only
through ``self._saver.parent``.

``FrameSaver`` keeps one-line delegate methods under the original
``_init_resume_manifest`` / ``_init_resume_manifest_from_resume`` /
``_drain_manifest_updates`` / ``_commit_manifest_cursor`` /
``_finalize_manifest`` names, so every existing call site
(``set_files``, ``stop_saving``, the save loops) and every test patch
target resolves unchanged.
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
import queue
import uuid
from typing import TYPE_CHECKING, cast

from lightsheet import CONFIG_PATH, RIG_SPECIFIC_PATH
from lightsheet.resume import (
    ManifestUpdate,
    ResumeManifest,
    apply_manifest_update,
    manifest_path_for,
    write_manifest,
)

if TYPE_CHECKING:
    from lightsheet.gui.coordinators.frame_saver_controller import FrameSaver
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)


class ManifestRecorder:
    """The resume-manifest plumbing for one ``FrameSaver``.

    Holds only the saver back-reference — all mutable manifest state
    (``resume_manifest``, ``_manifest_path``, ``manifest_update_queue``,
    ``acquisition_uuid``) stays on the saver so the save workers and
    ``stop_saving`` see one source of truth regardless of which delegate
    name the caller used.
    """

    def __init__(self, saver: FrameSaver) -> None:
        self._saver = saver

    def init_manifest(self, wavelengths: list[int]) -> None:
        """Mint the acquisition UUID and write the initial sidecar
        ``<acquisition>.resume.json`` with ``state="in_progress"``.

        Called from ``set_files`` before any frame is acquired, so a
        crash between the first frame and the first cursor write still
        leaves a discoverable manifest. The manifest path is derived from
        the first resolved channel-0 filename so the post-collision-bump
        fileset and its manifest always share a stem.
        """
        saver = self._saver
        saver.acquisition_uuid = uuid.uuid4().hex
        # Resolve to an absolute path now: the deferred manifest writes
        # (cursor commits, lifecycle updates) must land next to the
        # fileset chosen here, not wherever the process cwd happens to
        # be when they run.
        saver._manifest_path = manifest_path_for(saver.filenames_lists[0][0]).resolve()
        save_mode = {
            "reconstructed_frame": "stitch",
            "ETLscan": "all_crop",
            "FullETLscan": "all_full",
        }.get(saver.datasets_name, "stitch")
        # Operator-intent fields: captured from the live model snapshot so
        # a resume can restore them through the MicroscopeState mutators.
        # Guarded — a minimal shell stand-in (tests) or an unbuilt model
        # leaves them None instead of crashing the save.
        laser_power_pct = None
        laser_enabled = None
        auto_lasers = None
        save_options = None
        line_time_s = None
        try:
            from lightsheet.state.types import MicroscopeSnapshot

            snap = cast("Controller_MainWindow", saver.parent).state.snapshot()
        except Exception:
            snap = None
        if isinstance(snap, MicroscopeSnapshot):
            laser_power_pct = [float(v) for v in snap.laser_power_pct]
            laser_enabled = [bool(v) for v in snap.laser_enabled]
            auto_lasers = [bool(v) for v in snap.auto_lasers]
            save_options = {
                "mode": str(snap.save_options.mode),
                "description": str(snap.save_options.description),
            }
            line_time_s = float(snap.lightsheet_line_time_s)
        save_filepath = getattr(saver.parent, "save_filepath", "")
        if not isinstance(save_filepath, str):
            save_filepath = ""
        # Safety-config fingerprint for the resume gate's diff check.
        safety_config: dict[str, dict[str, str]] = {}
        try:
            from lightsheet.resume.gate import collect_safety_config

            overlay = str(RIG_SPECIFIC_PATH) if RIG_SPECIFIC_PATH.exists() else None
            safety_config = collect_safety_config(str(CONFIG_PATH), overlay)
        except Exception as e:
            logger.warning("could not snapshot safety config: %s", e)
        row_index = getattr(saver.parent, "stack_queue_row_index", None)
        if not isinstance(row_index, int) or isinstance(row_index, bool):
            row_index = None
        saver.resume_manifest = ResumeManifest(
            uuid=saver.acquisition_uuid,
            state="in_progress",
            n_planes=int(saver.number_of_files) * int(saver.number_of_datasets),
            stack_starting_plane=saver._coerce_shell_float("stack_starting_plane"),
            stack_ending_plane=saver._coerce_shell_float("stack_ending_plane"),
            stack_step=saver._coerce_shell_float("stack_step"),
            save_mode=save_mode,
            wavelengths=[int(w) for w in wavelengths],
            multi_channel=len(wavelengths) > 1,
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
            row_index=row_index,
            laser_power_pct=laser_power_pct,
            laser_enabled=laser_enabled,
            auto_lasers=auto_lasers,
            save_options=save_options,
            lightsheet_line_time_s=line_time_s,
            save_filepath=save_filepath,
            safety_config=safety_config,
        )
        write_manifest(saver._manifest_path, saver.resume_manifest)

    def init_manifest_from_resume(
        self,
        resume_manifest: ResumeManifest,
        wavelengths: list[int],
        hdf5_cursors: dict[str, int],
    ) -> None:
        """Build the resumed sidecar manifest from an existing one.

        The UUID and spawn parameters are inherited; the HDF5 cursor map
        is refreshed to the resolved (or fallback) fileset. The manifest
        is written next to the first resolved channel-0 file.

        The lifecycle is reopened to ``in_progress`` (and any prior
        ``completed_at`` cleared): terminal manifests are immutable, so
        without the reset the resumed run could never record its own
        terminal state — and ``in_progress`` is the correct crash
        signature while the resumed run is in flight.
        """
        saver = self._saver
        saver.acquisition_uuid = resume_manifest.uuid
        saver._manifest_path = manifest_path_for(saver.filenames_lists[0][0]).resolve()
        new_cursors = dict(resume_manifest.cursors)
        # Keep only path-keyed HDF5 cursors — legacy save-mode keys
        # ("stitch"/"all_crop"/"all_full") are retired on the first
        # resume so a re-crash resolves through the path-key schema.
        hdf5_group = {
            k: v for k, v in new_cursors.get("hdf5", {}).items() if k.endswith(".hdf5")
        }
        hdf5_group.update(hdf5_cursors)
        new_cursors["hdf5"] = hdf5_group
        saver.resume_manifest = dataclasses.replace(
            resume_manifest,
            cursors=new_cursors,
            state="in_progress",
            completed_at=None,
        )
        write_manifest(saver._manifest_path, saver.resume_manifest)

    def drain_updates(self) -> None:
        """Apply every staged ``ManifestUpdate`` to ``resume_manifest``.

        Called by the save worker before each manifest write and once more
        on exit, so updates staged by other threads (lifecycle, motor
        positions, checkpoints, trajectory rows) land on disk.
        """
        saver = self._saver
        while True:
            try:
                update = saver.manifest_update_queue.get_nowait()
            except queue.Empty:
                break
            if saver.resume_manifest is not None:
                saver.resume_manifest = apply_manifest_update(
                    saver.resume_manifest, update
                )

    def commit_cursor(self, fmt: str, key: str, value: int) -> None:
        """Update a committed-plane cursor and rewrite the manifest.

        MUST only be called after the underlying write (``create_dataset``
        / ``write_plane``) has returned — the cursor is the
        durable-on-disk truth, not the number of frames enqueued.
        """
        saver = self._saver
        if saver.resume_manifest is None or saver._manifest_path is None:
            return
        self.drain_updates()
        saver.resume_manifest = apply_manifest_update(
            saver.resume_manifest,
            ManifestUpdate(
                kind="cursor",
                payload={"format": fmt, "key": key, "value": int(value)},
            ),
        )
        try:
            write_manifest(saver._manifest_path, saver.resume_manifest)
        except OSError as e:
            # A manifest write failure must not abort the acquisition —
            # the image data is already durable; a stale cursor resumes
            # into a re-acquire, never a skip (probe clamps the cursor).
            logger.warning("resume manifest write failed: %s", e)

    def finalize(self) -> None:
        """Drain staged updates and write the manifest one last time.

        Called at the end of every save-worker body, and again from
        ``stop_saving`` after the worker thread has been joined (the
        worker may have already exited before the lifecycle update was
        staged). Post-join there is exactly one writer, so the call is
        race-free.
        """
        saver = self._saver
        if saver.resume_manifest is None or saver._manifest_path is None:
            return
        try:
            self.drain_updates()
            write_manifest(saver._manifest_path, saver.resume_manifest)
        except Exception as e:
            logger.warning("resume manifest finalize failed: %s", e)
