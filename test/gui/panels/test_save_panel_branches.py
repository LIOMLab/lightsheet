"""Branch-coverage tests for ``lightsheet/gui/panels/save_panel.py``.

Targets the missing arcs reported by ``coverage report --show-missing``
(missing_branches in coverage.json):

- ``__init__`` FIELD_SPECS policy loop — the ``applySpec`` call arm
  (48->49) that only fires when a panel widget matches a spec entry.
- ``_auto_laser_selection`` fallback arms — ``state`` absent (97->106),
  ``snapshot()`` raising (100/104/105), and a non-tuple ``auto_lasers``
  payload (106->111) all degrade to the legacy shell attributes.
- ``save_options_from_widgets`` loop-exhaust arc (125->129) and the
  unchecked-radio continue arc (126->125).
- ``updateUi_save_mode_checked`` sender-None early return (155->exit)
  and ``updateUi_save_mode`` unmapped-button return (164->165).
- ``updateUi_select_file`` — cancel, empty selection, HDF5, OME-Zarr,
  and corrupt-path arms (211-254).
- ``_list_zarr_datasets`` — unexpected-shape raise (283-284) and the
  3D single-channel fallback (290->293).
- ``updateUi_select_dataset`` — the whole body: the guard return, the
  HDF5/Zarr read dispatch, the first-item attributes table, the
  per-item matplotlib display, and the corrupt-dataset continue arm.
- ``_read_zarr_dataset`` — unrecognized-label raise, missing
  /acquisition group, OME-NGFF channel-wavelength merge, and the
  out-of-range / missing / non-dict ome fallbacks.
- ``updateUi_save_single_image`` — the multi-channel partial-frame
  guard (602-607).

All tests use the real ``Controller_MainWindow`` via the ``controller``
fixture (real ``SavePanelWidget``, real ``QFileDialog`` patched only at
the module-bound name the panel calls, real h5py/zarr stores written to
``tmp_path``). No static-source assertions.
"""

from __future__ import annotations

import contextlib
import typing
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from lightsheet.gui.shell.controller import Controller_MainWindow


# ---------------------------------------------------------------------------
# Store writers (same shape as test_save_panel_open_file.py helpers)
# ---------------------------------------------------------------------------


def _write_hdf5(path: Path, datasets: dict[str, np.ndarray]) -> None:
    import h5py

    with h5py.File(path, "w") as f:  # ty: ignore[invalid-argument-type]
        for name, arr in datasets.items():
            f.create_dataset(name, data=arr)


def _write_hdf5_with_attrs(path: Path) -> None:
    """Write an HDF5 file whose datasets carry displayable attrs."""
    import h5py

    with h5py.File(path, "w") as f:  # ty: ignore[invalid-argument-type]
        ds = f.create_dataset(
            "reconstructed_frame001", data=np.zeros((4, 4), dtype=np.uint16)
        )
        ds.attrs["Sample Name"] = "branch-sample"
        ds.attrs["exposure_time_s"] = 0.05
        f.create_dataset(
            "reconstructed_frame002", data=np.zeros((4, 4), dtype=np.uint16)
        )


def _write_zarr_store(
    path: Path,
    data: np.ndarray,
    with_acquisition: bool = True,
    ome: object = None,
    write_ome: bool = False,
) -> None:
    """Write a minimal OME-Zarr store; optionally attach acquisition
    attrs and/or a raw ``ome`` root attr for the channel-metadata
    merge branches in ``_read_zarr_dataset``."""
    import zarr

    root = zarr.open_group(path, mode="w")
    root.create_array("0", data=data)
    if with_acquisition:
        acq = root.create_group("acquisition")
        acq.attrs["Sample Name"] = "test-sample"
        acq.attrs["exposure_time_s"] = 0.05
    if write_ome:
        root.attrs["ome"] = ome  # ty: ignore[invalid-assignment]


@contextlib.contextmanager
def _patch_select_file_dialog(
    selected: list[str] | None,
    exec_result: int = 1,
) -> typing.Iterator[MagicMock]:
    """Patch the module-bound ``QFileDialog`` name updateUi_select_file
    calls. Yields the dialog instance mock the panel drives."""
    from lightsheet.gui.panels import save_panel as save_panel_mod

    with patch.object(save_panel_mod, "QFileDialog") as dlg_cls:
        inst = dlg_cls.return_value
        inst.exec.return_value = exec_result
        inst.selectedFiles.return_value = selected or []
        yield inst


def _patch_matplotlib(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace pyplot's figure/imshow/show so select_dataset's display
    path runs without creating real matplotlib windows under offscreen
    Qt. Returns the figure mock for call assertions."""
    from matplotlib import pyplot as plt_mod

    figure = MagicMock()
    monkeypatch.setattr(plt_mod, "figure", figure)
    monkeypatch.setattr(plt_mod, "imshow", MagicMock())
    monkeypatch.setattr(plt_mod, "show", MagicMock())
    return figure


# ---------------------------------------------------------------------------
# __init__ FIELD_SPECS policy loop (48->49)
# ---------------------------------------------------------------------------


def test_init_applies_field_spec_to_matching_widget(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a FIELD_SPECS entry names a widget present on the panel's ui
    with an ``applySpec`` method, ``__init__`` calls it — the True arm of
    the policy loop that the stock panel never takes (no FieldSpecSpinBox
    widgets)."""
    import lightsheet.gui.panels.save_panel as save_panel_mod
    from lightsheet.gui.panels.ui_save_panel import Ui_SavePanel

    applied: list[object] = []
    spec = object()

    class _FakeField:
        def applySpec(self, s: object) -> None:
            applied.append(s)

    real_setup = Ui_SavePanel.setupUi

    def _setup_then_add(ui_self: Ui_SavePanel, panel: QWidget) -> None:
        real_setup(ui_self, panel)
        ui_self.fake_field = _FakeField()  # ty: ignore[unresolved-attribute]

    monkeypatch.setattr(Ui_SavePanel, "setupUi", _setup_then_add)
    monkeypatch.setattr(save_panel_mod, "FIELD_SPECS", {"fake_field": spec})

    panel = save_panel_mod.SavePanelWidget(controller)
    qtbot.addWidget(panel)

    assert applied == [spec]


# ---------------------------------------------------------------------------
# _auto_laser_selection fallback arms (97->106, 100-105, 106->111)
# ---------------------------------------------------------------------------


def test_auto_laser_selection_no_state_falls_back_to_legacy(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ``shell.state`` absent (test-double shells), the selection
    falls back to the legacy ``_auto_laser1``/``_auto_laser2`` reads —
    whose property getters themselves degrade to the getattr defaults
    when the model is gone."""
    ctrl = controller
    monkeypatch.setattr(ctrl, "state", None)
    assert ctrl.save_panel._auto_laser_selection() == (False, False)


def test_auto_laser_selection_snapshot_raise_falls_back(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A ``snapshot()`` that raises is logged and degrades to the legacy
    attribute reads (the except arm + the snapshot-None fallback)."""
    ctrl = controller
    ctrl._auto_laser2 = True  # routes through the live model
    monkeypatch.setattr(
        ctrl.state,
        "snapshot",
        Mock(side_effect=RuntimeError("model broken")),
    )
    with caplog.at_level("WARNING"):
        result = ctrl.save_panel._auto_laser_selection()
    assert result == (False, True)
    assert "falling back" in caplog.text


def test_auto_laser_selection_non_tuple_payload_falls_back(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A snapshot whose ``auto_lasers`` is not a tuple (malformed model
    payload) takes the isinstance-False arm to the legacy reads."""
    ctrl = controller
    ctrl._auto_laser1 = True
    bad_snapshot = Mock()
    bad_snapshot.auto_lasers = "laser1"  # truthy non-tuple
    monkeypatch.setattr(ctrl.state, "snapshot", Mock(return_value=bad_snapshot))
    assert ctrl.save_panel._auto_laser_selection() == (True, False)


def test_active_single_channel_wavelength_uses_model_snapshot(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """With a healthy model, the snapshot tuple drives the wavelength:
    auto_laser2-only -> lasers[1].wavelength."""
    ctrl = controller
    ctrl._auto_laser1 = False
    ctrl._auto_laser2 = True
    wl = ctrl.save_panel._active_single_channel_wavelength()
    assert wl == int(ctrl.lasers[1].wavelength)


# ---------------------------------------------------------------------------
# save_options_from_widgets loop arcs (125->129, 126->125)
# ---------------------------------------------------------------------------


def test_save_options_from_widgets_no_radio_checked_defaults_stitch(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """With every save-mode radio unchecked, the scan loop exhausts
    without a hit and the returned SaveOptions keeps the STITCH
    default (the 125->129 loop-exit arc; the unchecked-radio 126->125
    continue arc is exercised on each pass)."""
    from lightsheet.state import SaveMode

    ctrl = controller
    group = ctrl.save_option_button_group
    group.setExclusive(False)
    for radio in ctrl.save_panel._radio_by_mode.values():
        radio.setChecked(False)
    try:
        opts = ctrl.save_panel.save_options_from_widgets()
    finally:
        group.setExclusive(True)
        ctrl.save_panel.ui.radioButton_saveStitch.setChecked(True)
    assert opts.mode == SaveMode.STITCH


def test_save_options_from_widgets_picks_checked_radio(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """A checked non-default radio wins the loop (the break arc) and the
    description text rides along."""
    from lightsheet.state import SaveMode

    ctrl = controller
    # Check the radio FIRST: the commit slot feeds the model, and the
    # model's sig_save_options_changed projection writes the model's
    # description back onto the line edit — setting the text after the
    # check keeps it from being clobbered.
    ctrl.save_panel.ui.radioButton_saveAllFull.setChecked(True)
    ctrl.save_panel.ui.lineEdit_saveDescription.setText("desc text")
    opts = ctrl.save_panel.save_options_from_widgets()
    assert opts.mode == SaveMode.ALL_FULL
    assert opts.description == "desc text"


# ---------------------------------------------------------------------------
# updateUi_save_mode_checked sender-None arm + updateUi_save_mode unmapped
# ---------------------------------------------------------------------------


def test_save_mode_checked_without_sender_returns(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Called directly (not via a toggled signal), ``sender()`` is None
    and the slot returns without touching the model."""
    ctrl = controller
    before = ctrl.state.save_options.mode
    ctrl.save_panel.updateUi_save_mode_checked(True)
    assert ctrl.state.save_options.mode == before


def test_save_mode_checked_unchecked_is_noop(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """``checked=False`` (the exclusive group's uncheck echo) returns
    immediately."""
    ctrl = controller
    before = ctrl.state.save_options.mode
    ctrl.save_panel.updateUi_save_mode_checked(False)
    assert ctrl.state.save_options.mode == before


def test_save_mode_unmapped_button_returns(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """A button that is not one of the four save-mode radios hits the
    ``mode is None`` early return."""
    ctrl = controller
    before = ctrl.state.save_options.mode
    ctrl.save_panel.updateUi_save_mode(Mock())
    assert ctrl.state.save_options.mode == before


def test_save_mode_mapped_button_commits_model(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """A real save-mode radio commits its SaveMode to the model (the
    mapped-button arm of buttonClicked)."""
    from lightsheet.state import SaveMode

    ctrl = controller
    ctrl.save_panel.updateUi_save_mode(ctrl.save_panel.ui.radioButton_saveStitchBlend)
    assert ctrl.state.save_options.mode == SaveMode.STITCH_BLEND


# ---------------------------------------------------------------------------
# updateUi_select_file (211-254)
# ---------------------------------------------------------------------------


def test_select_file_cancel_resets_label(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """Dialog cancelled (exec -> 0) resets the label and returns before
    touching open_directory."""
    ctrl = controller
    ctrl.open_directory = "/still/old"
    with _patch_select_file_dialog(None, exec_result=0):
        ctrl.save_panel.updateUi_select_file()
    assert ctrl.save_panel.ui.label_currentFileDirectory.text() == "Select a file…"
    assert ctrl.open_directory == "/still/old"


def test_select_file_empty_selection_resets_label(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """exec accepted but selectedFiles() empty -> label reset, return."""
    ctrl = controller
    with _patch_select_file_dialog([], exec_result=1):
        ctrl.save_panel.updateUi_select_file()
    assert ctrl.save_panel.ui.label_currentFileDirectory.text() == "Select a file…"


def test_select_file_hdf5_lists_datasets(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Selecting an HDF5 file (not a dir) takes the _list_hdf5_datasets
    arm and populates the dataset list widget."""
    ctrl = controller
    h5_path = tmp_path / "sample_555nm.hdf5"
    _write_hdf5(
        h5_path,
        {
            "reconstructed_frame001": np.zeros((4, 4), dtype=np.uint16),
            "reconstructed_frame002": np.zeros((4, 4), dtype=np.uint16),
        },
    )
    with _patch_select_file_dialog([str(h5_path)], exec_result=1):
        ctrl.save_panel.updateUi_select_file()
    ui = ctrl.save_panel.ui
    assert ctrl.open_directory == str(h5_path)
    assert ui.label_currentFileDirectory.text() == str(h5_path)
    assert ui.listWidget_fileDatasets.count() == 2
    assert ui.listWidget_fileDatasets.item(0).text() == "reconstructed_frame001"
    assert ui.pushButton_selectDataset.isEnabled() is True
    assert f"File {h5_path} opened" in ctrl.ui.plainTextEdit_messageLog.toPlainText()


def test_select_file_zarr_store_lists_planes(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """Selecting a directory takes the _list_zarr_datasets arm."""
    ctrl = controller
    zarr_path = tmp_path / "sample.ome.zarr"
    _write_zarr_store(zarr_path, np.zeros((1, 2, 4, 4), dtype=np.uint16))
    with _patch_select_file_dialog([str(zarr_path)], exec_result=1):
        ctrl.save_panel.updateUi_select_file()
    ui = ctrl.save_panel.ui
    assert ui.listWidget_fileDatasets.count() == 2
    assert ui.listWidget_fileDatasets.item(0).text() == "plane_0001"


def test_select_file_corrupt_path_emits_message(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A path whose open raises (corrupt HDF5) hits the except arm:
    sig_message surfaces the error and the label resets."""
    ctrl = controller
    bad_path = tmp_path / "corrupt.hdf5"
    bad_path.write_bytes(b"this is not an hdf5 file")
    messages: list[str] = []
    ctrl.sig_message.connect(lambda m: messages.append(m))
    with _patch_select_file_dialog([str(bad_path)], exec_result=1):
        ctrl.save_panel.updateUi_select_file()
    ui = ctrl.save_panel.ui
    assert ui.label_currentFileDirectory.text() == "Select a file…"
    assert ui.listWidget_fileDatasets.count() == 0
    assert any("Could not open" in m for m in messages), messages


# ---------------------------------------------------------------------------
# _list_zarr_datasets edge arms (283-284 raise, 290->293 3D fallback)
# ---------------------------------------------------------------------------


def test_list_zarr_datasets_rejects_bad_shape(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """An L0 array with fewer than 3 dims raises ValueError so the
    caller's except path surfaces a clear message."""
    ctrl = controller
    zarr_path = tmp_path / "flat.ome.zarr"
    _write_zarr_store(zarr_path, np.zeros((4, 4), dtype=np.uint16))
    with pytest.raises(ValueError, match="unexpected shape"):
        ctrl.save_panel._list_zarr_datasets(str(zarr_path))


def test_list_zarr_datasets_3d_single_channel_fallback(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A 3D (z, y, x) L0 array (no channel dim) is treated as c=1 and
    yields plane_NNNN labels — the len(shape)==4 else arm."""
    ctrl = controller
    zarr_path = tmp_path / "legacy3d.ome.zarr"
    _write_zarr_store(zarr_path, np.zeros((3, 4, 4), dtype=np.uint16))
    labels = ctrl.save_panel._list_zarr_datasets(str(zarr_path))
    assert labels == ["plane_0001", "plane_0002", "plane_0003"], labels


# ---------------------------------------------------------------------------
# updateUi_select_dataset (303-390)
# ---------------------------------------------------------------------------


def test_select_dataset_no_open_file_returns(
    qtbot: QtBot, controller: Controller_MainWindow
) -> None:
    """With no file opened, the guard returns before touching widgets."""
    ctrl = controller
    ctrl.open_directory = ""
    ctrl.save_panel.updateUi_select_dataset()
    assert ctrl.save_panel.ui.label_currentDataset.text() != "anything-set"


def test_select_dataset_empty_list_returns(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """An opened path with an empty dataset list hits the second guard
    operand (count == 0) and returns."""
    ctrl = controller
    h5_path = tmp_path / "sample.hdf5"
    _write_hdf5(h5_path, {"ds": np.zeros((2, 2), dtype=np.uint16)})
    ctrl.open_directory = str(h5_path)
    ctrl.save_panel.ui.listWidget_fileDatasets.clear()
    ctrl.save_panel.updateUi_select_dataset()
    # No dataset was read — label untouched by this call.
    assert ctrl.dataset_name == ""


def test_select_dataset_hdf5_displays_attributes_and_image(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two selected HDF5 datasets: item 0 populates the attributes table
    (the item==0 arm + attribute loop), item 1 takes the skip-attributes
    arm; both produce a figure + message."""
    ctrl = controller
    h5_path = tmp_path / "sample.hdf5"
    _write_hdf5_with_attrs(h5_path)
    figure = _patch_matplotlib(monkeypatch)

    ctrl.open_directory = str(h5_path)
    lw = ctrl.save_panel.ui.listWidget_fileDatasets
    lw.insertItem(0, "reconstructed_frame001")
    lw.insertItem(1, "reconstructed_frame002")
    lw.item(0).setSelected(True)
    lw.item(1).setSelected(True)

    ctrl.save_panel.updateUi_select_dataset()

    ui = ctrl.save_panel.ui
    assert ui.label_currentDataset.text() == "reconstructed_frame001"
    # First item's attributes table populated: 2 rows (Sample Name +
    # exposure_time_s), header + values.
    assert ui.tableWidget_fileAttributes.rowCount() == 2
    item_00 = ui.tableWidget_fileAttributes.item(0, 0)
    item_01 = ui.tableWidget_fileAttributes.item(0, 1)
    assert item_00 is not None and item_00.text() == "Sample Name"
    assert item_01 is not None and item_01.text() == "branch-sample"
    # One figure per selected dataset.
    assert figure.call_count == 2
    log = ctrl.ui.plainTextEdit_messageLog.toPlainText()
    assert "displayed" in log


def test_select_dataset_zarr_reads_slice(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An opened directory takes the is_zarr read arm."""
    ctrl = controller
    zarr_path = tmp_path / "sample.ome.zarr"
    _write_zarr_store(zarr_path, np.zeros((1, 2, 4, 4), dtype=np.uint16))
    figure = _patch_matplotlib(monkeypatch)

    ctrl.open_directory = str(zarr_path)
    lw = ctrl.save_panel.ui.listWidget_fileDatasets
    lw.insertItem(0, "plane_0001")
    lw.item(0).setSelected(True)

    ctrl.save_panel.updateUi_select_dataset()

    assert ctrl.save_panel.ui.label_currentDataset.text() == "plane_0001"
    assert figure.call_count == 1


def test_select_dataset_missing_key_continues_with_message(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A selected dataset name absent from the file raises KeyError in
    the reader — the except arm emits a per-dataset message and the loop
    continues to the next item instead of crashing the GUI thread."""
    ctrl = controller
    h5_path = tmp_path / "sample.hdf5"
    _write_hdf5(h5_path, {"reconstructed_frame001": np.zeros((2, 2), dtype=np.uint16)})
    _patch_matplotlib(monkeypatch)

    ctrl.open_directory = str(h5_path)
    lw = ctrl.save_panel.ui.listWidget_fileDatasets
    lw.insertItem(0, "missing_dataset")
    lw.insertItem(1, "reconstructed_frame001")
    lw.item(0).setSelected(True)
    lw.item(1).setSelected(True)

    messages: list[str] = []
    ctrl.sig_message.connect(lambda m: messages.append(m))
    ctrl.save_panel.updateUi_select_dataset()

    assert any("Could not open dataset missing_dataset" in m for m in messages), (
        messages
    )
    # The loop continued — the second (valid) dataset still displayed.
    assert "reconstructed_frame001" in ctrl.ui.plainTextEdit_messageLog.toPlainText()


# ---------------------------------------------------------------------------
# _read_zarr_dataset metadata-merge arms (420-421, 434->445)
# ---------------------------------------------------------------------------


def test_read_zarr_dataset_rejects_unrecognized_label(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A label that matches neither plane_NNNN nor chN_plane_NNNN raises
    ValueError."""
    ctrl = controller
    zarr_path = tmp_path / "sample.ome.zarr"
    _write_zarr_store(zarr_path, np.zeros((1, 2, 4, 4), dtype=np.uint16))
    with pytest.raises(ValueError, match="unrecognized zarr plane label"):
        ctrl.save_panel._read_zarr_dataset(str(zarr_path), "not_a_plane")


def test_read_zarr_dataset_without_acquisition_group(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A store with no /acquisition group returns empty attrs (the
    acq-is-None arm) instead of KeyError."""
    ctrl = controller
    zarr_path = tmp_path / "bare.ome.zarr"
    _write_zarr_store(
        zarr_path,
        np.zeros((1, 2, 4, 4), dtype=np.uint16),
        with_acquisition=False,
    )
    data, attrs = ctrl.save_panel._read_zarr_dataset(str(zarr_path), "plane_0001")
    assert data.shape == (4, 4)
    assert "Sample Name" not in attrs


def test_read_zarr_dataset_merges_ome_channel_wavelength(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """An ome dict with omero channels merges the selected channel's
    wavelength into attrs (the full merge arm)."""
    ctrl = controller
    zarr_path = tmp_path / "ome.ome.zarr"
    _write_zarr_store(
        zarr_path,
        np.zeros((2, 2, 4, 4), dtype=np.uint16),
        write_ome=True,
        ome={"omero": {"channels": [{"wavelength": 555}, {"wavelength": 647}]}},
    )
    data, attrs = ctrl.save_panel._read_zarr_dataset(str(zarr_path), "ch1_plane_0001")
    assert attrs["Channel Wavelength"] == 647
    assert data.shape == (4, 4)


def test_read_zarr_dataset_ome_channel_out_of_range(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A channel index past the ome channel list skips the merge (the
    range-guard False arm)."""
    ctrl = controller
    zarr_path = tmp_path / "short_ome.ome.zarr"
    _write_zarr_store(
        zarr_path,
        np.zeros((2, 2, 4, 4), dtype=np.uint16),
        write_ome=True,
        ome={"omero": {"channels": [{"wavelength": 555}]}},
    )
    _, attrs = ctrl.save_panel._read_zarr_dataset(str(zarr_path), "ch1_plane_0001")
    assert "Channel Wavelength" not in attrs


def test_read_zarr_dataset_ome_not_a_dict(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A non-dict ome attr (e.g. a string written by another tool) skips
    the channel merge entirely."""
    ctrl = controller
    zarr_path = tmp_path / "str_ome.ome.zarr"
    _write_zarr_store(
        zarr_path,
        np.zeros((1, 2, 4, 4), dtype=np.uint16),
        write_ome=True,
        ome="not-a-dict",
    )
    _, attrs = ctrl.save_panel._read_zarr_dataset(str(zarr_path), "plane_0001")
    assert "Channel Wavelength" not in attrs


def test_read_zarr_dataset_ome_channel_missing_wavelength(
    qtbot: QtBot, controller: Controller_MainWindow, tmp_path: Path
) -> None:
    """A channel entry without a wavelength key leaves attrs untouched
    (the wl-is-None arm)."""
    ctrl = controller
    zarr_path = tmp_path / "nowl.ome.zarr"
    _write_zarr_store(
        zarr_path,
        np.zeros((1, 2, 4, 4), dtype=np.uint16),
        write_ome=True,
        ome={"omero": {"channels": [{"name": "ch0"}]}},
    )
    _, attrs = ctrl.save_panel._read_zarr_dataset(str(zarr_path), "plane_0001")
    assert "Channel Wavelength" not in attrs


# ---------------------------------------------------------------------------
# updateUi_save_single_image — multi-channel partial-frame guard (602-607)
# ---------------------------------------------------------------------------


def test_save_single_image_multichannel_missing_frame_aborts(
    qtbot: QtBot,
    controller: Controller_MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multi-channel single save with a channel frame missing from
    ``reconstructed_frames`` aborts with an operator message BEFORE
    set_files — a camera timeout on one channel must not raise KeyError
    or write a half-populated fileset."""
    ctrl = controller
    ctrl.state.set_auto_lasers(True, True)
    ctrl.save_panel.ui.lineEdit_saveFilename.setText("test")
    ctrl.image_hor_pos_text = "0.0"
    ctrl.image_ver_pos_text = "0.0"
    ctrl.image_cam_pos_text = "0.0"
    # Stitch mode (default radio) -> reconstructed_frame save path ->
    # the multi-channel branch. No frames captured.
    ctrl.reconstructed_frames = {}

    set_files = Mock()
    monkeypatch.setattr(ctrl._fs.frame_saver, "set_files", set_files)

    ctrl.save_panel.updateUi_save_single_image()

    assert set_files.call_count == 0, (
        "set_files must not run when a channel frame is missing"
    )
    assert (
        "one or both channel frames are missing"
        in ctrl.ui.plainTextEdit_messageLog.toPlainText()
    )
