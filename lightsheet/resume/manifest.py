"""Resume-manifest value type and atomic sidecar I/O.

Pure-Python, no Qt / no HAL imports — testable with direct import + call
+ assert, mirroring the ``lightsheet/state/types.py`` convention.

The ``ResumeManifest`` is the per-acquisition durability contract: a
``<acquisition>.resume.json`` sidecar written by the save-consumer thread
after each committed plane. Only the save-consumer side calls
``write_manifest``; every other thread contributes state through
``ManifestUpdate`` items staged on an unbounded ``queue.Queue`` that the
save worker drains before each write, so the on-disk cursor is always the
durable truth (never the acquisition worker's in-flight counter).

A manifest stuck in ``state == "in_progress"`` at scan time is the crash
signature: the process died before the save worker could apply the final
lifecycle update.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MANIFEST_SUFFIX = ".resume.json"
QUEUE_MANIFEST_SUFFIX = ".queue-resume.json"

# Lifecycle states. ``in_progress`` doubles as the crash signature: a
# manifest that never received a terminal lifecycle update.
LIFECYCLE_STATES = frozenset({"in_progress", "paused", "interrupted", "completed"})
TERMINAL_STATES = frozenset({"paused", "interrupted", "completed"})

# Cursor namespace: which output format a cursor group belongs to.
CURSOR_FORMATS = frozenset({"hdf5", "zarr"})

# ManifestUpdate kinds accepted on the cross-thread update queue.
UPDATE_KINDS = frozenset(
    {"cursor", "checkpoint", "trajectory", "lifecycle", "motor_position"}
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _is_json_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _json_safe(value: Any, field: str = "manifest") -> Any:
    """Recursively convert a manifest payload to JSON-safe values.

    dict keys are stringified, tuples become lists, and any value whose
    type comes from numpy is rejected — numpy scalars pass
    ``isinstance(x, float)`` (``np.float64`` subclasses ``float``) but
    serialize with surprising dtypes, so the module check runs first.
    """
    module = type(value).__module__
    if module.startswith("numpy"):
        raise ValueError(
            f"{field}: numpy value {type(value).__name__} is not allowed in "
            "the manifest — convert to a plain Python scalar first"
        )
    if _is_json_scalar(value):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v, field) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v, field) for v in value]
    raise ValueError(f"{field}: value of type {type(value).__name__} is not JSON-safe")


def _check_int(name: str, value: Any, *, minimum: int | None = None) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an int; got {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}; got {value}")


def _check_float(name: str, value: Any) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a number; got {type(value).__name__}")


def _check_str(name: str, value: Any, *, allow_empty: bool = True) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a str; got {type(value).__name__}")
    if not allow_empty and not value:
        raise ValueError(f"{name} must be a non-empty str")


def _check_int_map(name: str, value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a dict; got {type(value).__name__}")
    for k, v in value.items():
        if not isinstance(k, str):
            raise ValueError(f"{name} keys must be str; got {type(k).__name__}")
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError(f"{name}[{k!r}] must be a number; got {type(v).__name__}")
        _json_safe(v, f"{name}[{k!r}]")


def _check_dict(name: str, value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a dict; got {type(value).__name__}")
    _json_safe(value, name)


def _check_list(name: str, value: Any) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list; got {type(value).__name__}")
    _json_safe(value, name)


@dataclasses.dataclass(frozen=True)
class ResumeManifest:
    """Frozen per-acquisition resume record.

    Fields are the full frozen spawn parameters plus the durability
    cursors; later plans slot ``adaptive_cfg``/``focus_cfg``/``row_index``
    content in without a format break. All updates go through
    ``dataclasses.replace`` (see ``apply_manifest_update``).
    """

    uuid: str
    state: str
    n_planes: int
    stack_starting_plane: float
    stack_ending_plane: float
    stack_step: float
    save_mode: str
    created_at: str
    start_plane: int = 0
    wavelengths: list[int] | None = None
    multi_channel: bool = False
    adaptive_cfg: dict[str, Any] | None = None
    focus_cfg: dict[str, Any] | None = None
    safety_config: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)
    last_motor_positions: dict[str, float] = dataclasses.field(default_factory=dict)
    cursors: dict[str, dict[str, int]] = dataclasses.field(default_factory=dict)
    trajectory_samples: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    controller_checkpoints: list[dict[str, Any]] = dataclasses.field(
        default_factory=list
    )
    completed_at: str | None = None
    row_index: int | None = None
    # Operator-intent fields restored by MicroscopeState.restore_from_manifest.
    # All optional so manifests written before they existed still validate.
    laser_power_pct: list[float] | None = None
    laser_enabled: list[bool] | None = None
    auto_lasers: list[bool] | None = None
    save_options: dict[str, Any] | None = None
    lightsheet_line_time_s: float | None = None
    save_filepath: str | None = None

    def __post_init__(self) -> None:
        _check_str("uuid", self.uuid, allow_empty=False)
        _check_str("state", self.state, allow_empty=False)
        if self.state not in LIFECYCLE_STATES:
            raise ValueError(
                f"state must be one of {sorted(LIFECYCLE_STATES)}; got {self.state!r}"
            )
        _check_int("n_planes", self.n_planes, minimum=1)
        _check_int("start_plane", self.start_plane, minimum=0)
        if self.start_plane >= self.n_planes:
            raise ValueError(
                f"start_plane {self.start_plane} must be < n_planes {self.n_planes}"
            )
        _check_float("stack_starting_plane", self.stack_starting_plane)
        _check_float("stack_ending_plane", self.stack_ending_plane)
        _check_float("stack_step", self.stack_step)
        _check_str("save_mode", self.save_mode)
        _check_str("created_at", self.created_at, allow_empty=False)
        if self.wavelengths is not None:
            if not isinstance(self.wavelengths, list):
                raise ValueError(
                    "wavelengths must be a list or None; got "
                    f"{type(self.wavelengths).__name__}"
                )
            for w in self.wavelengths:
                _check_int("wavelengths[]", w, minimum=1)
        if not isinstance(self.multi_channel, bool):
            raise ValueError(
                f"multi_channel must be a bool; got {type(self.multi_channel).__name__}"
            )
        if self.adaptive_cfg is not None:
            _check_dict("adaptive_cfg", self.adaptive_cfg)
        if self.focus_cfg is not None:
            _check_dict("focus_cfg", self.focus_cfg)
        if not isinstance(self.safety_config, dict):
            raise ValueError(
                f"safety_config must be a dict; got {type(self.safety_config).__name__}"
            )
        for section, entries in self.safety_config.items():
            _check_str("safety_config key", section)
            _check_dict(f"safety_config[{section!r}]", entries)
        _check_int_map("last_motor_positions", self.last_motor_positions)
        if not isinstance(self.cursors, dict):
            raise ValueError(
                f"cursors must be a dict; got {type(self.cursors).__name__}"
            )
        for fmt, group in self.cursors.items():
            if fmt not in CURSOR_FORMATS:
                raise ValueError(
                    f"cursors key must be one of {sorted(CURSOR_FORMATS)}; got {fmt!r}"
                )
            if not isinstance(group, dict):
                raise ValueError(
                    f"cursors[{fmt!r}] must be a dict; got {type(group).__name__}"
                )
            for key, value in group.items():
                _check_str(f"cursors[{fmt!r}] key", key)
                _check_int(f"cursors[{fmt!r}][{key!r}]", value, minimum=0)
        _check_list("trajectory_samples", self.trajectory_samples)
        _check_list("controller_checkpoints", self.controller_checkpoints)
        if self.completed_at is not None:
            _check_str("completed_at", self.completed_at, allow_empty=False)
        if self.row_index is not None:
            _check_int("row_index", self.row_index, minimum=0)
        for name, value in (
            ("laser_power_pct", self.laser_power_pct),
            ("laser_enabled", self.laser_enabled),
            ("auto_lasers", self.auto_lasers),
        ):
            if value is not None:
                _check_list(name, value)
                if len(value) != 2:
                    raise ValueError(
                        f"{name} must have exactly 2 entries; got {len(value)}"
                    )
        if self.laser_power_pct is not None:
            for v in self.laser_power_pct:
                _check_float("laser_power_pct[]", v)
        for name, value in (
            ("laser_enabled", self.laser_enabled),
            ("auto_lasers", self.auto_lasers),
        ):
            if value is not None:
                for v in value:
                    if not isinstance(v, bool):
                        raise ValueError(
                            f"{name}[] must be bools; got {type(v).__name__}"
                        )
        if self.save_options is not None:
            _check_dict("save_options", self.save_options)
        if self.lightsheet_line_time_s is not None:
            _check_float("lightsheet_line_time_s", self.lightsheet_line_time_s)
        if self.save_filepath is not None:
            _check_str("save_filepath", self.save_filepath)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe plain-dict representation."""
        return _json_safe(dataclasses.asdict(self), "ResumeManifest")

    @staticmethod
    def from_dict(d: dict[str, Any]) -> ResumeManifest:
        """Rebuild a manifest from a plain dict, validating every field.

        Raises ``ValueError``/``TypeError`` on missing required keys, wrong
        types, or an unknown lifecycle state — callers that tolerate
        corrupt input should use ``read_manifest``.
        """
        if not isinstance(d, dict):
            raise ValueError(f"manifest payload must be a dict; got {type(d).__name__}")
        return ResumeManifest(**d)


@dataclasses.dataclass(frozen=True)
class ManifestUpdate:
    """A staged manifest mutation from a non-save thread.

    Frozen, JSON-safe, and picklable so it can cross a ``queue.Queue``
    (and a process boundary if the save side ever moves). The save worker
    drains the queue and applies updates in arrival order before each
    ``write_manifest`` call.
    """

    kind: str
    payload: dict[str, Any]
    plane_index: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in UPDATE_KINDS:
            raise ValueError(
                f"kind must be one of {sorted(UPDATE_KINDS)}; got {self.kind!r}"
            )
        _check_dict("payload", self.payload)
        if self.plane_index is not None:
            _check_int("plane_index", self.plane_index, minimum=0)


def apply_manifest_update(
    manifest: ResumeManifest, update: ManifestUpdate
) -> ResumeManifest:
    """Apply one staged ``ManifestUpdate`` to a manifest, returning the
    updated (new, frozen) manifest."""
    if update.kind == "cursor":
        fmt = str(update.payload["format"])
        key = str(update.payload["key"])
        value = update.payload["value"]
        group = dict(manifest.cursors.get(fmt, {}))
        group[key] = value
        cursors = dict(manifest.cursors)
        cursors[fmt] = group
        return dataclasses.replace(manifest, cursors=cursors)
    if update.kind == "lifecycle":
        state = str(update.payload["state"])
        completed_at = manifest.completed_at
        if state in TERMINAL_STATES:
            completed_at = _utc_now_iso()
        return dataclasses.replace(manifest, state=state, completed_at=completed_at)
    if update.kind == "motor_position":
        positions = dict(manifest.last_motor_positions)
        for k, v in update.payload.items():
            positions[str(k)] = float(v)
        return dataclasses.replace(manifest, last_motor_positions=positions)
    if update.kind == "checkpoint":
        row = dict(update.payload)
        if update.plane_index is not None:
            row.setdefault("plane_index", update.plane_index)
        return dataclasses.replace(
            manifest,
            controller_checkpoints=[*manifest.controller_checkpoints, row],
        )
    if update.kind == "trajectory":
        row = dict(update.payload)
        if update.plane_index is not None:
            row.setdefault("plane_index", update.plane_index)
        return dataclasses.replace(
            manifest,
            trajectory_samples=[*manifest.trajectory_samples, row],
        )
    raise ValueError(f"unknown manifest update kind {update.kind!r}")


def manifest_path_for(acquisition_path: Path | str) -> Path:
    """Return the sidecar manifest path for an acquisition output path.

    ``<stem>.resume.json`` co-located in the same directory.
    """
    p = Path(acquisition_path)
    return p.with_name(p.stem + MANIFEST_SUFFIX)


def write_manifest(path: Path | str, manifest: ResumeManifest) -> None:
    """Atomically write ``manifest`` to ``path`` (temp file + os.replace).

    Only the save-consumer thread may call this during an acquisition —
    concurrent temp-file writes from two threads could interleave the
    replace and lose the last cursor.
    """
    path = Path(path)
    tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    tmp.replace(path)  # os.replace semantics — atomic on POSIX and NTFS


def read_manifest(path: Path | str) -> ResumeManifest | None:
    """Read and validate a sidecar manifest.

    Returns ``None`` when the file is missing, unparsable, or fails
    schema validation (corrupt or hand-edited manifests fail closed — a
    bad manifest must never drive a resume).
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("resume manifest %s is not valid JSON", path)
        return None
    try:
        return ResumeManifest.from_dict(data)
    except (ValueError, TypeError) as e:
        logger.warning("resume manifest %s failed validation: %s", path, e)
        return None


# ---------------------------------------------------------------------------
# Queue-level resume manifest
# ---------------------------------------------------------------------------

QUEUE_LIFECYCLE_STATES = frozenset(
    {"in_progress", "paused", "interrupted", "completed"}
)


@dataclasses.dataclass(frozen=True)
class QueueResumeManifest:
    """Queue-level resume record (``<base>.queue-resume.json``).

    Written by the queue loop in the save directory when a queued stack run
    starts and rewritten before each row with the active ``row_index``. A
    queue manifest stuck in ``in_progress`` is the crash signature: the
    ``row_index``-th row was executing when the queue died. ``row_hash``
    covers the full row list so a tampered or stale manifest is detected;
    ``row_uuids`` identifies the live table rows the manifest belongs to.
    """

    uuid: str
    state: str
    row_index: int
    rows: list[dict[str, Any]]
    row_uuids: list[str]
    row_hash: str
    created_at: str
    save_directory: str = ""
    completed_at: str | None = None

    def __post_init__(self) -> None:
        _check_str("uuid", self.uuid, allow_empty=False)
        _check_str("state", self.state, allow_empty=False)
        if self.state not in QUEUE_LIFECYCLE_STATES:
            raise ValueError(
                f"state must be one of {sorted(QUEUE_LIFECYCLE_STATES)}; "
                f"got {self.state!r}"
            )
        _check_int("row_index", self.row_index, minimum=0)
        _check_list("rows", self.rows)
        _check_list("row_uuids", self.row_uuids)
        for u in self.row_uuids:
            _check_str("row_uuids[]", u)
        _check_str("row_hash", self.row_hash, allow_empty=False)
        _check_str("created_at", self.created_at, allow_empty=False)
        _check_str("save_directory", self.save_directory)
        if self.completed_at is not None:
            _check_str("completed_at", self.completed_at, allow_empty=False)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(dataclasses.asdict(self), "QueueResumeManifest")

    @staticmethod
    def from_dict(d: dict[str, Any]) -> QueueResumeManifest:
        if not isinstance(d, dict):
            raise ValueError(
                f"queue manifest payload must be a dict; got {type(d).__name__}"
            )
        return QueueResumeManifest(**d)


def hash_queue_rows(rows: list[dict[str, Any]]) -> str:
    """Canonical SHA-256 over the row list — order-sensitive."""
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def queue_manifest_path_for(save_directory: Path | str, base_name: str) -> Path:
    """Return the queue manifest path inside ``save_directory``."""
    return Path(save_directory) / f"{base_name}{QUEUE_MANIFEST_SUFFIX}"


def write_queue_manifest(path: Path | str, manifest: QueueResumeManifest) -> None:
    """Atomically write a queue manifest (temp file + os.replace)."""
    path = Path(path)
    tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    tmp.replace(path)


def read_queue_manifest(path: Path | str) -> QueueResumeManifest | None:
    """Read and validate a queue manifest, failing closed on any problem.

    A stored ``row_hash`` that does not match the stored ``rows`` is a
    tamper/corruption signature and is rejected here so a stale manifest
    can never drive a queue resume.
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("queue manifest %s is not valid JSON", path)
        return None
    try:
        manifest = QueueResumeManifest.from_dict(data)
    except (ValueError, TypeError) as e:
        logger.warning("queue manifest %s failed validation: %s", path, e)
        return None
    if manifest.row_hash != hash_queue_rows(manifest.rows):
        logger.warning(
            "queue manifest %s row hash mismatch — rejecting as tampered",
            path,
        )
        return None
    return manifest
