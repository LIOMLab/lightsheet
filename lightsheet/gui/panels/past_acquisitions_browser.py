"""Past-acquisitions browser (D-05).

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
underlying filename and HDF5 root attrs are NOT modified (Pitfall 6).

Graceful degradation: older HDF5 files (pre-Phase-4, May 2025 and
earlier) have ZERO root attrs — the wavelength is inferred from the
filename ``_<wavelength>nm_`` token, and the sample name from the
filename prefix. Files that fail to open are skipped with a per-file
``sig_message``; the table shows the parseable rows.

The scan runs asynchronously (``QThread`` + ``moveToThread``) so a
~30-folder × 2000-dataset scan does not freeze the GUI thread (and the
E-stop kill path stays responsive, AGENTS.md §2). The worker emits a
single ``sig_scan_finished(list)`` signal when done; the table is
populated in one batch on the GUI thread.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import typing
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal

if typing.TYPE_CHECKING:
    from lightsheet.gui.shell.controller import Controller_MainWindow

logger = logging.getLogger(__name__)

# Targets the writer's finalize_with_resolutions uses (mirrored for the
# level-count estimate in the table manager; not used by the parser).
_WAVELENGTH_TOKEN_RE = re.compile(r"_(\d{3})nm_", re.IGNORECASE)
_HDF5_FILENAME_RE = re.compile(
    r"^(?P<sample>.+?)_(?P<wl>\d{3})nm_stack_plane_(?P<idx>\d+)\.hdf5$",
    re.IGNORECASE,
)


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
        shell: "Controller_MainWindow",
        data_dir: str | None = None,
    ) -> None:
        super().__init__()
        self._shell = shell
        self._data_dir = data_dir
        self._thread: QThread | None = None
        self._worker: "_ScanWorker" | None = None

    def _resolve_data_dir(self) -> str:
        if self._data_dir:
            return self._data_dir
        return str(getattr(self._shell, "save_directory", ""))

    def list_acquisitions(self) -> list[PastAcquisitionEntry]:
        """Synchronously scan the save directory and return the parsed
        entries. Skips files that fail to open with a per-file
        ``sig_message``; never raises on a malformed file."""
        data_dir = self._resolve_data_dir()
        if not data_dir or not os.path.isdir(data_dir):
            return []
        return self._scan_directory(data_dir)

    def _scan_directory(self, data_dir: str) -> list[PastAcquisitionEntry]:
        """Scan the top-level sample folders + their immediate children
        (two-level depth, matching the rig probe) for HDF5 + Zarr stores."""
        entries: list[PastAcquisitionEntry] = []
        try:
            top_entries = sorted(os.listdir(data_dir))
        except OSError as exc:
            self.sig_message.emit(
                f"Cannot read past acquisitions: {data_dir} is missing or "
                f"not readable ({exc})."
            )
            return []
        for name in top_entries:
            top_path = os.path.join(data_dir, name)
            # A .ome.zarr directory IS a Zarr store, not a folder to
            # recurse into — check the format suffix before the isdir
            # recursion so the store is parsed as one acquisition.
            if self._is_hdf5(name) or (self._is_zarr(name) and os.path.isdir(top_path)):
                entries.extend(self._parse_file(top_path, sample_hint=name))
                continue
            if os.path.isdir(top_path):
                # Two-level depth: sample folder + immediate child folders.
                entries.extend(self._scan_folder(top_path, sample_hint=name))
                try:
                    children = sorted(os.listdir(top_path))
                except OSError:
                    continue
                for child in children:
                    child_path = os.path.join(top_path, child)
                    if os.path.isdir(child_path) and not self._is_zarr(child):
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
            names = sorted(os.listdir(folder))
        except OSError:
            return out
        for name in names:
            path = os.path.join(folder, name)
            if self._is_hdf5(name):
                out.extend(self._parse_file(path, sample_hint=sample_hint))
            elif self._is_zarr(name) and os.path.isdir(path):
                out.extend(self._parse_file(path, sample_hint=sample_hint))
        return out

    def _parse_file(self, path: str, sample_hint: str) -> list[PastAcquisitionEntry]:
        if self._is_hdf5(path):
            entry = self._parse_hdf5(path, sample_hint)
            if entry is not None:
                return [entry]
            return []
        if self._is_zarr(path) and os.path.isdir(path):
            entry = self._parse_zarr(path, sample_hint)
            if entry is not None:
                return [entry]
            return []
        return []

    # -- HDF5 ---------------------------------------------------------- #

    def _parse_hdf5(
        self, path: str, sample_hint: str
    ) -> PastAcquisitionEntry | None:
        import h5py

        fname = os.path.basename(path)
        try:
            with h5py.File(path, "r") as f:
                n_planes = len(f.keys())
                # Wavelength: root attrs first, else filename token.
                wl = self._hdf5_wavelength(f, fname)
                sample = self._hdf5_sample(f, fname, sample_hint)
        except (OSError, KeyError, Exception) as exc:  # noqa: BLE001
            self.sig_message.emit(
                f"Could not parse {fname}: {exc}. Skipped."
            )
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

    def _hdf5_wavelength(self, f, fname: str) -> int | None:
        # Root attrs first (post-Phase-4 files).
        for key in ("Laser1 Wavelength", "Laser2 Wavelength"):
            val = f.attrs.get(key)
            if val is not None:
                try:
                    return int(val)
                except (TypeError, ValueError):
                    pass
        # Fall back to the filename _<wl>nm_ token (pre-Phase-4 files).
        return self._wavelength_from_filename(fname)

    def _hdf5_sample(self, f, fname: str, sample_hint: str) -> str:
        # The Sample Name attr is empty in all probed files — use the
        # filename prefix (before the _<wavelength>nm_ token) or the
        # folder name.
        m = _HDF5_FILENAME_RE.match(fname)
        if m and m.group("sample"):
            return m.group("sample")
        return sample_hint

    # -- Zarr ---------------------------------------------------------- #

    def _parse_zarr(
        self, path: str, sample_hint: str
    ) -> PastAcquisitionEntry | None:
        import zarr

        fname = os.path.basename(path)
        try:
            root = zarr.open_group(path, mode="r")
            n_planes = self._zarr_n_planes(root)
            wl = self._zarr_wavelength(root, fname)
            sample = self._zarr_sample(fname, sample_hint)
        except (OSError, KeyError, Exception) as exc:  # noqa: BLE001
            self.sig_message.emit(
                f"Could not parse {fname}: {exc}. Skipped."
            )
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

    def _zarr_n_planes(self, root) -> int:
        # L0 is the multiscale level "0" array; shape is (c, z, y, x).
        arr = root.get("0")
        if arr is None:
            return 0
        shape = getattr(arr, "shape", None)
        if not shape or len(shape) < 2:
            return 0
        return int(shape[1])

    def _zarr_wavelength(self, root, fname: str) -> int | None:
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
            return int(os.path.getsize(path))
        except OSError:
            return 0

    @staticmethod
    def _dir_size(path: str) -> int:
        total = 0
        for _root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(_root, f))
                except OSError:
                    pass
        return total

    @staticmethod
    def _date_str(path: str) -> str:
        try:
            mtime = os.path.getmtime(path)
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
        decides whether to populate the table)."""
        if self._thread is not None and self._thread.isRunning():
            return
        data_dir = self._resolve_data_dir()
        self._thread = QThread()
        self._worker = _ScanWorker(self, data_dir)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_worker_finished(self, entries: list) -> None:
        self.sig_scan_finished.emit(entries)

    def stop_scan(self) -> None:
        """Best-effort teardown for shutdown / teardown. The worker is
        allowed to finish its current file; the thread quits and is
        waited on briefly."""
        if self._worker is not None:
            try:
                self._worker.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
        self._thread = None
        self._worker = None


class _ScanWorker(QObject):
    """Worker QObject that runs the scan on a worker thread."""

    finished = Signal(list)

    def __init__(self, browser: PastAcquisitionsBrowser, data_dir: str) -> None:
        super().__init__()
        self._browser = browser
        self._data_dir = data_dir

    def run(self) -> None:
        try:
            if not self._data_dir or not os.path.isdir(self._data_dir):
                self.finished.emit([])
                return
            entries = self._browser._scan_directory(self._data_dir)
            self.finished.emit(entries)
        except Exception as exc:  # noqa: BLE001
            logger.exception("past-acquisitions scan failed: %s", exc)
            self.finished.emit([])
