"""Past-acquisitions browser.

Parses both HDF5 and OME-Zarr acquisitions under the operator's save
directory (``~/Desktop/LightSheetData`` by default) so the operator can
see what has already been acquired, in which format, at what size. The
browser is READ-ONLY — it never modifies, deletes, moves, or renames
existing files (operator filesystem actions stay manual).

Wavelength normalization (operator-locked): filenames use ``555nm``,
``640nm``, and ``647nm``. ``640nm`` and ``647nm`` are the same laser
channel (the iBeam is labeled "Laser 2 (640 nm)" in recent metadata;
older files used ``647nm`` in the filename). The browser normalizes both
to ``647`` in the parsed entry — a DISPLAY transform only. The
underlying filename and HDF5 root attrs are NOT modified.

Graceful degradation: older HDF5 files (pre-Phase-4, May 2025 and
earlier) have ZERO root attrs — the wavelength is inferred from the
filename ``_<wavelength>nm_`` token, and the sample name from the
filename prefix. Files that fail to open are skipped with a per-file
``sig_message``; the table shows the parseable rows.

The scan runs asynchronously (``QThread`` + ``moveToThread``) so a
~30-folder x 2000-dataset scan does not freeze the GUI thread (and the
E-stop kill path stays responsive). The worker emits a
single ``sig_scan_finished(list)`` signal when done; the table is
populated in one batch on the GUI thread.
"""

from __future__ import annotations

import contextlib
import datetime
import logging
import os
import re
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from lightsheet.gui.panels.ui_past_acquisitions_panel import (
    Ui_PastAcquisitionsPanel,
)

if typing.TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)

# Past-acquisitions table columns (display-only). The Planned-queue columns
# stay in acquisition_table_manager.py; these are the dedicated Past panel's
# table columns.
_PAST_HEADERS = ["Sample", "Channel", "#Planes", "Size", "Date", "Format"]
_PAST_COL_SAMPLE = 0
_PAST_COL_CHANNEL = 1
_PAST_COL_NPLANES = 2
_PAST_COL_SIZE = 3
_PAST_COL_DATE = 4
_PAST_COL_FORMAT = 5

_PAST_EMPTY_COPY = (
    "No past acquisitions in {save_directory}. Run an acquisition, then "
    "click Refresh to list saved stacks here."
)
_PAST_SCANNING_COPY = "Scanning {save_directory}\u2026"
_PAST_ERROR_COPY = (
    "Save directory is empty or does not exist: {save_directory}. "
    "Set a save directory in the Files panel first."
)


def _format_bytes(n: int | None) -> str:
    """Format a byte count as a human-readable size string (KB/MB/GB/TB).

    ``n`` is typed ``int | None`` because the size helpers can return 0 on
    OSError and a future caller could plausibly pass None for an unknown
    size; the None guard returns an empty string in that case.
    """
    if n is None:
        return ""
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


# Wavelength token: matches _<3-digit>nm followed by a separator (_ or .)
# or end-of-string. The trailing separator is a lookahead so it is not
# consumed — this lets the regex match both the old naming
# (foo_555nm_stack_plane_00001.hdf5) and the compact naming
# (foo_stack_555nm.hdf5, foo_stack_555nm_01.hdf5).
_WAVELENGTH_TOKEN_RE = re.compile(r"_(\d{3})nm(?=[._]|$)", re.IGNORECASE)
# HDF5 filename pattern — handles BOTH conventions:
#   old:    <sample>_<wl>nm_stack_plane_<idx>.hdf5
#   new:    <sample>_<scan>_<wl>nm.hdf5  /  <sample>_<scan>_<wl>nm_<idx>.hdf5
# The _stack_plane_<idx> segment (old) and the bare _<idx> suffix (new)
# are both optional. For the new convention the `sample` group includes
# the scan-type segment (e.g. "tes1_stack"); _hdf5_sample strips a known
# scan-type suffix to recover the bare sample name.
_HDF5_FILENAME_RE = re.compile(
    r"^(?P<sample>.+?)_(?P<wl>\d{3})nm"
    r"(?:_stack_plane_(?P<oldidx>\d+)|_(?P<idx>\d+))?\.hdf5$",
    re.IGNORECASE,
)
# Known scan-type segments appended to the sample name under the compact
# convention (set_files passes scan_type as the second filename segment).
_SCAN_TYPE_SUFFIXES = ("_stack", "_singleImage", "_z")


@dataclass
class PastAcquisitionEntry:
    """One parsed past-acquisition row.

    ``wavelength`` is the DISPLAY-normalized value (640 -> 647). The
    underlying file is unchanged.
    """

    sample: str
    wavelength: int | None
    n_planes: int
    size_bytes: int
    date_str: str
    format_label: str
    source_path: str


def normalize_wavelength(wl: int | None) -> int | None:
    """Display-only wavelength normalization: 640 -> 647 (the rig-confirmed
    capture wavelength; the iBeam label says 640 but the channel is 647).
    Other wavelengths pass through. ``None`` stays ``None``."""
    if wl is None:
        return None
    if wl == 640:
        return 647
    return wl


class PastAcquisitionsBrowser(QObject):
    """Parse past HDF5 + OME-Zarr acquisitions under the save directory.

    ``list_acquisitions()`` runs the scan synchronously (used by unit
    tests). ``start_scan_async()`` offloads the same scan to a
    ``QThread`` + ``moveToThread`` worker and emits
    ``sig_scan_finished(list)`` when done — the production path so the
    GUI thread (and the E-stop kill path) stays responsive.
    """

    sig_scan_finished = Signal(list)
    sig_message = Signal(str)

    def __init__(
        self,
        shell: Controller_MainWindow,
        data_dir: str | None = None,
    ) -> None:
        super().__init__()
        self._shell = shell
        self._data_dir = data_dir
        self._thread: QThread | None = None
        self._worker: _ScanWorker | None = None

    def _resolve_data_dir(self) -> str:
        if self._data_dir:
            return self._data_dir
        return str(getattr(self._shell, "save_directory", ""))

    def list_acquisitions(self) -> list[PastAcquisitionEntry]:
        """Synchronously scan the save directory and return the parsed
        entries. Skips files that fail to open with a per-file
        ``sig_message``; never raises on a malformed file."""
        data_dir = self._resolve_data_dir()
        if not data_dir or not Path(data_dir).is_dir():
            return []
        return self._scan_directory(data_dir)

    def _scan_directory(self, data_dir: str) -> list[PastAcquisitionEntry]:
        """Scan the top-level sample folders + their immediate children
        (two-level depth, matching the rig probe) for HDF5 + Zarr stores."""
        entries: list[PastAcquisitionEntry] = []
        try:
            top_entries = sorted(
                child.name for child in Path(data_dir).iterdir()
            )
        except OSError as exc:
            self.sig_message.emit(
                f"Cannot read past acquisitions: {data_dir} is missing or "
                f"not readable ({exc})."
            )
            return []
        for name in top_entries:
            top_path = str(Path(data_dir) / name)
            # A .ome.zarr directory IS a Zarr store, not a folder to
            # recurse into — check the format suffix before the isdir
            # recursion so the store is parsed as one acquisition. HDF5
            # stores are regular files, so gate the .hdf5 suffix on
            # isfile too — a directory named foo.hdf5 would otherwise be
            # handed to h5py.File and fail (caught, but wasteful); it
            # falls through to the isdir recursion below instead.
            if (self._is_hdf5(name) and Path(top_path).is_file()) or (
                self._is_zarr(name) and Path(top_path).is_dir()
            ):
                entries.extend(self._parse_file(top_path, sample_hint=name))
                continue
            if Path(top_path).is_dir():
                # Two-level depth: sample folder + immediate child folders.
                entries.extend(self._scan_folder(top_path, sample_hint=name))
                try:
                    children = sorted(
                        child.name for child in Path(top_path).iterdir()
                    )
                except OSError:
                    continue
                for child in children:
                    child_path = str(Path(top_path) / child)
                    if Path(child_path).is_dir() and not self._is_zarr(child):
                        entries.extend(
                            self._scan_folder(child_path, sample_hint=child)
                        )
                    elif self._is_zarr(child):
                        entries.extend(
                            self._parse_file(child_path, sample_hint=child)
                        )
        return entries

    def _scan_folder(self, folder: str, sample_hint: str) -> list[PastAcquisitionEntry]:
        """Parse the HDF5 + Zarr files directly inside one folder."""
        out: list[PastAcquisitionEntry] = []
        try:
            names = sorted(child.name for child in Path(folder).iterdir())
        except OSError:
            return out
        for name in names:
            path = str(Path(folder) / name)
            if self._is_hdf5(name) or (
                self._is_zarr(name) and Path(path).is_dir()
            ):
                out.extend(self._parse_file(path, sample_hint=sample_hint))
        return out

    def _parse_file(self, path: str, sample_hint: str) -> list[PastAcquisitionEntry]:
        if self._is_hdf5(path):
            entry = self._parse_hdf5(path, sample_hint)
            if entry is not None:
                return [entry]
            return []
        if self._is_zarr(path) and Path(path).is_dir():
            entry = self._parse_zarr(path, sample_hint)
            if entry is not None:
                return [entry]
            return []
        return []

    # -- HDF5 ---------------------------------------------------------- #

    def _parse_hdf5(self, path: str, sample_hint: str) -> PastAcquisitionEntry | None:
        import h5py

        fname = Path(path).name
        try:
            with h5py.File(path, "r") as f:
                # Count only actual datasets at the root, not groups or
                # metadata keys — a future writer change adding a non-
                # dataset root key (e.g. a 'metadata' group) would
                # otherwise inflate the plane count. Mirrors the Zarr
                # parser which inspects the array shape instead of keys.
                n_planes = sum(1 for k in f if isinstance(f[k], h5py.Dataset))
                # Wavelength: root attrs first, else filename token.
                wl = self._hdf5_wavelength(f, fname)
                sample = self._hdf5_sample(f, fname, sample_hint)
        except Exception as exc:
            self.sig_message.emit(f"Could not parse {fname}: {exc}. Skipped.")
            logger.debug("past-acquisitions HDF5 parse failed: %s (%s)", path, exc)
            return None
        size = self._file_size(path)
        date_str = self._date_str(path)
        return PastAcquisitionEntry(
            sample=sample,
            wavelength=normalize_wavelength(wl),
            n_planes=n_planes,
            size_bytes=size,
            date_str=date_str,
            format_label="HDF5",
            source_path=path,
        )

    def _hdf5_wavelength(self, f: Any, fname: str) -> int | None:
        # Root attrs: prefer the ACTIVE laser's wavelength. The file
        # stores both lasers' metadata, but only the active one was used
        # for this acquisition. Checking Laser1 first would always
        # return 555nm even when only the 647nm laser was active.
        for i in (1, 2):
            active = f.attrs.get(f"Laser{i} Active")
            if active is not None and bool(active):
                wl = f.attrs.get(f"Laser{i} Wavelength")
                if wl is not None:
                    try:
                        return int(wl)
                    except (TypeError, ValueError):
                        pass
        # Fall back: no active laser attr (pre-Phase-4 files) — try
        # Laser1 then Laser2 wavelength attrs.
        for key in ("Laser1 Wavelength", "Laser2 Wavelength"):
            val = f.attrs.get(key)
            if val is not None:
                try:
                    return int(val)
                except (TypeError, ValueError):
                    pass
        # Fall back to the filename _<wl>nm_ token (pre-Phase-4 files).
        return self._wavelength_from_filename(fname)

    def _hdf5_sample(self, f: Any, fname: str, sample_hint: str) -> str:
        # The Sample Name attr is empty in all probed files — use the
        # filename prefix (before the _<wavelength>nm token) or the
        # folder name.
        m = _HDF5_FILENAME_RE.match(fname)
        if m and m.group("sample"):
            sample = m.group("sample")
            # Under the compact naming convention the sample group
            # includes the scan-type segment (e.g. "tes1_stack"). Strip a
            # known scan-type suffix to recover the bare sample name.
            for suffix in _SCAN_TYPE_SUFFIXES:
                if sample.lower().endswith(suffix):
                    sample = sample[: -len(suffix)]
                    break
            return sample  # ty: ignore[unsound-return-statement]
        # No wavelength token in the filename (e.g. "test5_stack_plane_
        # 00001.hdf5") — strip the _stack_plane_NNNNN suffix to get the
        # sample name. Without this the full filename shows in the
        # Sample column.
        stem = fname
        if stem.lower().endswith(".hdf5"):
            stem = stem[: -len(".hdf5")]
        m2 = re.match(r"^(.+?)_stack_plane_\d+$", stem, re.IGNORECASE)
        if m2 and m2.group(1):
            return m2.group(1)  # ty: ignore[unsound-return-statement]
        return sample_hint

    # -- Zarr ---------------------------------------------------------- #

    def _parse_zarr(self, path: str, sample_hint: str) -> PastAcquisitionEntry | None:
        import zarr

        fname = Path(path).name
        try:
            root = zarr.open_group(path, mode="r")
            n_planes = self._zarr_n_planes(root)
            wl = self._zarr_wavelength(root, fname)
            sample = self._zarr_sample(fname, sample_hint)
        except Exception as exc:
            self.sig_message.emit(f"Could not parse {fname}: {exc}. Skipped.")
            logger.debug("past-acquisitions Zarr parse failed: %s (%s)", path, exc)
            return None
        size = self._dir_size(path)
        date_str = self._date_str(path)
        return PastAcquisitionEntry(
            sample=sample,
            wavelength=normalize_wavelength(wl),
            n_planes=n_planes,
            size_bytes=size,
            date_str=date_str,
            format_label="OME-Zarr",
            source_path=path,
        )

    def _zarr_n_planes(self, root: Any) -> int:
        # L0 is the multiscale level "0" array. The writer produces a 4D
        # (c, z, y, x) array; plane count is shape[1]. A 3D (z, y, x)
        # array (no channel dimension) would return shape[0] instead —
        # fail closed on anything other than the expected 4D shape so a
        # future writer change does not silently report the image height
        # as the plane count.
        arr = root.get("0")
        if arr is None:
            return 0
        shape = getattr(arr, "shape", None)
        if not shape or len(shape) != 4:
            return 0
        return int(shape[1])

    def _zarr_wavelength(self, root: Any, fname: str) -> int | None:
        # The writer nests omero inside the "ome" attrs key. Fall back to
        # a top-level "omero" key for robustness, then the filename token.
        ome = root.attrs.get("ome")
        if isinstance(ome, dict):
            channels = ome.get("omero", {}).get("channels", [])
            if channels:
                wl = channels[0].get("wavelength")
                if wl is not None:
                    try:
                        return int(wl)
                    except (TypeError, ValueError):
                        pass
        omero = root.attrs.get("omero")
        if isinstance(omero, dict):
            channels = omero.get("channels", [])
            if channels:
                wl = channels[0].get("wavelength")
                if wl is not None:
                    try:
                        return int(wl)
                    except (TypeError, ValueError):
                        pass
        return self._wavelength_from_filename(fname)

    def _zarr_sample(self, fname: str, sample_hint: str) -> str:
        # <filename>.ome.zarr -> strip the .ome.zarr suffix.
        stem = fname
        for suffix in (".ome.zarr", ".zarr"):
            if stem.lower().endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        # Strip a trailing _<wl>nm token if present.
        m = _WAVELENGTH_TOKEN_RE.search("_" + stem + "_" if stem else "")
        if m:
            idx = stem.lower().find(f"_{m.group(1)}nm")
            if idx > 0:
                return stem[:idx]
        return stem or sample_hint

    # -- shared helpers ------------------------------------------------ #

    @staticmethod
    def _is_hdf5(name: str) -> bool:
        return name.lower().endswith(".hdf5")

    @staticmethod
    def _is_zarr(name: str) -> bool:
        return name.lower().endswith(".ome.zarr") or name.lower().endswith(".zarr")

    @staticmethod
    def _wavelength_from_filename(fname: str) -> int | None:
        m = _WAVELENGTH_TOKEN_RE.search("_" + fname + "_")
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return None
        return None

    @staticmethod
    def _file_size(path: str) -> int:
        try:
            return int(Path(path).stat().st_size)
        except OSError:
            return 0

    @staticmethod
    def _dir_size(path: str) -> int:
        total = 0
        for _root, _dirs, files in os.walk(path):
            for f in files:
                with contextlib.suppress(OSError):
                    total += (Path(_root) / f).stat().st_size
        return total

    @staticmethod
    def _date_str(path: str) -> str:
        try:
            mtime = Path(path).stat().st_mtime
            return datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
        except OSError:
            return ""

    # -- async scan ---------------------------------------------------- #

    def start_scan_async(self) -> None:
        """Offload the scan to a QThread + moveToThread worker. Emits
        ``sig_scan_finished(list)`` when done. If a scan is already
        running, it is allowed to finish (cancelling an h5py open
        mid-read is not clean); the result is discarded if the operator
        toggled back to Planned by the time it completes (the caller
        decides whether to populate the table).

        The thread's ``finished`` signal is connected to
        ``deleteLater`` for both the worker and the thread so the C++
        QObjects are destroyed deterministically rather than by Python
        GC (which can warn or crash on some Qt versions when a QThread
        is destroyed without an explicit deleteLater). The
        ``_on_worker_finished`` slot clears ``self._thread`` /
        ``self._worker`` so the next ``start_scan_async`` is not blocked
        by a stale reference."""
        if self._thread is not None and self._thread.isRunning():
            return
        data_dir = self._resolve_data_dir()
        self._thread = QThread()
        self._worker = _ScanWorker(self, data_dir)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        # Deterministic C++ cleanup: deleteLater on both the worker and
        # the thread when the thread's event loop exits. Without this,
        # the QThread and worker QObject persist (held by self._thread /
        # self._worker) until Python GC drops them, which can warn or
        # crash on some Qt versions.
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        # Clear the Python references AFTER the thread has actually
        # exited (thread.finished fires after the event loop stops, not
        # when quit() is posted). Clearing them in _on_worker_finished
        # (which fires when the WORKER finishes, before the thread has
        # processed the quit event) lets Python GC collect the QThread
        # wrapper while the C++ QThread is still running — causing
        # "QThread: Destroyed while thread is still running" crash.
        self._thread.finished.connect(self._clear_thread_refs)
        self._thread.start()

    def _on_worker_finished(self, entries: list) -> None:  # ty: ignore[missing-type-argument]
        self.sig_scan_finished.emit(entries)

    def _clear_thread_refs(self) -> None:
        """Clear the thread/worker Python references after the thread has
        actually exited (connected to thread.finished). The C++ objects
        are torn down by the deleteLater connections wired in
        start_scan_async."""
        self._thread = None
        self._worker = None

    def stop_scan(self) -> None:
        """Best-effort teardown for shutdown / teardown. The worker is
        allowed to finish its current file; the thread quits and is
        drained non-blockingly. A blocking QThread.wait() here stalls
        the calling event loop and, under xdist on Windows, can trigger
        heap corruption (0xc0000374) when the quit() races ahead of the
        thread's exec(). The non-blocking poll pumps events so the
        queued quit reaches the thread's event loop deterministically."""
        if self._worker is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                self._worker.finished.disconnect()
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            app = QApplication.instance()
            deadline = 2000
            step_ms = 20
            while self._thread.isRunning() and deadline > 0:
                if app is not None:
                    app.processEvents()
                self._thread.wait(step_ms)
                deadline -= step_ms
        self._thread = None
        self._worker = None

    def is_scanning(self) -> bool:
        """True if an async scan is currently running.

        Public accessor so collaborators (e.g. the panel's refresh slot)
        can query scan state without reaching into the browser's private
        ``_thread`` attribute.
        """
        return self._thread is not None and self._thread.isRunning()


class _ScanWorker(QObject):
    """Worker QObject that runs the scan on a worker thread."""

    finished = Signal(list)

    def __init__(self, browser: PastAcquisitionsBrowser, data_dir: str) -> None:
        super().__init__()
        self._browser = browser
        self._data_dir = data_dir

    def run(self) -> None:
        try:
            if not self._data_dir or not Path(self._data_dir).is_dir():
                self.finished.emit([])
                return
            entries = self._browser._scan_directory(self._data_dir)
            self.finished.emit(entries)
        except Exception as exc:
            logger.exception("past-acquisitions scan failed: %s", exc)
            self.finished.emit([])


class _NumericTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem that sorts by a numeric UserRole value when one
    is set, falling back to the default text comparison otherwise.

    The past-acquisitions table has numeric columns (#Planes, Size) whose
    string text sorts lexically by default ("10" < "2"). Setting a
    numeric sort value on Qt.ItemDataRole.UserRole and overriding __lt__
    makes Qt sort these columns numerically when the operator clicks the
    column header.
    """

    def __lt__(self, other: object) -> bool:
        sv = self.data(Qt.ItemDataRole.UserRole)
        ov = (
            other.data(Qt.ItemDataRole.UserRole)
            if isinstance(other, QTableWidgetItem)
            else None
        )
        if sv is not None and ov is not None:
            try:
                return float(sv) < float(ov)
            except (TypeError, ValueError):
                pass
        return super().__lt__(other)  # ty: ignore[invalid-argument-type]


class PastAcquisitionsPanel(QWidget):
    """Dedicated left-rail panel hosting the past-acquisitions browser.

    Replaces the placeholder QWidget at ``stackedPanels`` index 6. Owns the
    ``PastAcquisitionsBrowser`` (parser + async scan worker), the read-only
    past-acquisitions ``QTableWidget``, the Planned/Past toggle, and the
    Refresh button. The Planned queue + add/edit/remove/start-queue controls
    stay in the Stack panel (``AcquisitionTableManager``); this panel is
    read-only browse of past saves.

    The Planned/Past toggle moves with the browser to this dedicated panel.
    Since the Planned queue now lives in a separate left-rail page (Stack,
    index 2), the "Planned" radio button switches the left-rail to the Stack
    page instead of toggling a table in-place. The "Past" radio button is the
    current page (checked by default).

    The async-scan pattern (``QThread`` + ``moveToThread`` + ``finished →
    deleteLater`` + ``_clear_thread_refs``) is preserved verbatim in the
    ``PastAcquisitionsBrowser`` — it keeps the GUI thread (and the E-stop
    kill path) responsive during a ~30-folder scan.
    """

    # Emitted when the async past-acquisitions scan completes (the list of
    # PastAcquisitionEntry). External observers (e.g. tests) may subscribe;
    # the table is populated internally in _on_scan_finished.
    past_acquisitions_scan_finished = Signal(list)

    def __init__(self, shell: Controller_MainWindow) -> None:
        super().__init__()
        self._shell = shell
        self.ui = Ui_PastAcquisitionsPanel()
        self.ui.setupUi(self)

        # Read-only past table: ResizeToContents + stretch last section +
        # ellipsis on long names. Sorting enabled after the batch populate
        # so the per-row setItem calls do not re-sort mid-populate.
        self.ui.tableWidget_pastAcquisitions.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.ui.tableWidget_pastAcquisitions.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.ui.tableWidget_pastAcquisitions.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        past_header = self.ui.tableWidget_pastAcquisitions.horizontalHeader()
        past_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        past_header.setStretchLastSection(True)
        self.ui.tableWidget_pastAcquisitions.setWordWrap(False)
        self.ui.tableWidget_pastAcquisitions.textElideMode = Qt.TextElideMode.ElideRight  # ty: ignore[invalid-assignment]
        self.ui.tableWidget_pastAcquisitions.setSortingEnabled(True)

        # Status label styling (empty/scanning/error copy).
        self.ui.label_pastStatus.setStyleSheet("color: gray; padding: 12px;")
        self.ui.label_pastStatus.setVisible(False)

        # Planned/Past toggle — exclusive group. "Planned" switches the
        # left-rail to the Stack page (index 2); "Past" is this page.
        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        self._view_group.addButton(self.ui.radioButton_viewPlanned)
        self._view_group.addButton(self.ui.radioButton_viewPast)
        self.ui.radioButton_viewPast.setChecked(True)

        # The past-acquisitions browser (parser + async scan worker).
        self._browser = PastAcquisitionsBrowser(self._shell)
        self._browser.sig_scan_finished.connect(self._on_scan_finished)
        self._browser.sig_message.connect(self._shell.sig_message.emit)

        # Wire the Refresh button + the Planned toggle.
        self.ui.pushButton_refreshPast.clicked.connect(self._on_refresh)
        self._view_group.buttonClicked.connect(self._on_view_changed)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def browser(self) -> PastAcquisitionsBrowser:
        """The owned PastAcquisitionsBrowser (parser + async scan worker)."""
        return self._browser

    def refresh(self) -> None:
        """Trigger an async re-scan of the save directory."""
        self._on_refresh()

    def stop_scan(self) -> None:
        """Best-effort teardown for shutdown (delegates to the browser)."""
        self._browser.stop_scan()

    # ------------------------------------------------------------------ #
    # Internal slots
    # ------------------------------------------------------------------ #

    def _on_view_changed(self, button: object) -> None:
        """Planned/Past toggle handler. "Planned" switches the left-rail to
        the Stack page (index 2); "Past" re-checks itself (this page)."""
        if button is self.ui.radioButton_viewPlanned:
            # Switch the left-rail to the Stack page (Planned queue).
            stacked = getattr(self._shell.ui, "stackedPanels", None)
            if stacked is not None:
                stacked.setCurrentIndex(2)
            # Re-check "Past" so the toggle reflects this page when the
            # operator returns to it.
            self.ui.radioButton_viewPast.setChecked(True)
        # "Past" is the current page — no action needed.

    def _on_refresh(self) -> None:
        """Trigger an async re-scan of the save directory for past
        acquisitions. Shows the 'Scanning ...' label while the worker
        runs; the table is populated in one batch on completion.

        If a scan is already in flight, the table/label are NOT reset —
        the running scan's results will populate the table on
        completion."""
        if self._browser.is_scanning():
            return
        folder = str(getattr(self._shell, "save_directory", ""))
        self.ui.label_pastStatus.setText(
            _PAST_SCANNING_COPY.format(save_directory=folder)
        )
        self.ui.label_pastStatus.setVisible(True)
        self.ui.tableWidget_pastAcquisitions.setVisible(False)
        self.ui.tableWidget_pastAcquisitions.setRowCount(0)
        self._browser.start_scan_async()

    def _on_scan_finished(self, entries: list) -> None:  # ty: ignore[missing-type-argument]
        """Populate the past-acquisitions table in one batch (called on
        the GUI thread via the browser's sig_scan_finished signal)."""
        self.ui.tableWidget_pastAcquisitions.setSortingEnabled(False)
        self.ui.tableWidget_pastAcquisitions.setRowCount(0)
        for entry in entries:
            self._add_past_row(entry)
        self.ui.tableWidget_pastAcquisitions.setSortingEnabled(True)
        # Default sort: Date descending.
        self.ui.tableWidget_pastAcquisitions.sortByColumn(
            _PAST_COL_DATE, Qt.SortOrder.DescendingOrder
        )
        has_rows = self.ui.tableWidget_pastAcquisitions.rowCount() > 0
        self.ui.tableWidget_pastAcquisitions.setVisible(has_rows)
        self.ui.label_pastStatus.setVisible(not has_rows)
        if not has_rows:
            folder = str(getattr(self._shell, "save_directory", ""))
            # Distinguish "directory missing/empty" (point the operator to
            # the Files panel) from "directory exists but has no stacks"
            # (tell them to run an acquisition + Refresh). UI-SPEC
            # §Copywriting Past Acquisitions empty vs empty-save-directory.
            if not folder or not Path(folder).is_dir():
                self.ui.label_pastStatus.setText(
                    _PAST_ERROR_COPY.format(save_directory=folder or "(unset)")
                )
            else:
                self.ui.label_pastStatus.setText(
                    _PAST_EMPTY_COPY.format(save_directory=folder)
                )
        # Re-emit so external observers (tests) can subscribe.
        self.past_acquisitions_scan_finished.emit(entries)

    def _add_past_row(self, entry: PastAcquisitionEntry) -> None:
        row = self.ui.tableWidget_pastAcquisitions.rowCount()
        self.ui.tableWidget_pastAcquisitions.insertRow(row)
        self._set_past_cell(row, _PAST_COL_SAMPLE, entry.sample)
        wl = normalize_wavelength(entry.wavelength)
        self._set_past_cell(
            row,
            _PAST_COL_CHANNEL,
            "" if wl is None else str(wl),
            sort_value=wl if wl is not None else None,
        )
        self._set_past_cell(
            row,
            _PAST_COL_NPLANES,
            str(entry.n_planes),
            sort_value=entry.n_planes,
        )
        self._set_past_cell(
            row,
            _PAST_COL_SIZE,
            _format_bytes(entry.size_bytes),
            sort_value=entry.size_bytes,
        )
        self._set_past_cell(row, _PAST_COL_DATE, entry.date_str)
        self._set_past_cell(row, _PAST_COL_FORMAT, entry.format_label)

    def _set_past_cell(
        self, row: int, col: int, text: str, sort_value: float | None = None
    ) -> None:
        # Use the numeric item subclass when a numeric sort value is
        # provided so Qt sorts the column numerically (via __lt__ on the
        # UserRole data) instead of lexically on the string text.
        item = (
            _NumericTableWidgetItem(text)
            if sort_value is not None
            else QTableWidgetItem(text)
        )
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        item.setToolTip(text)
        if sort_value is not None:
            item.setData(Qt.ItemDataRole.UserRole, sort_value)
        self.ui.tableWidget_pastAcquisitions.setItem(row, col, item)
