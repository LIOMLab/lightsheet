"""Behavior tests for the generated PySide6 UI enum normalizer."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_normalizer() -> ModuleType:
    """Load the scripts/fix_generated_ui_enums.py module as a one-off."""
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "fix_generated_ui_enums.py"
    spec = importlib.util.spec_from_file_location("fix_generated_ui_enums", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fix_generated_ui_enums"] = module
    spec.loader.exec_module(module)
    return module


def _load_header_tool() -> ModuleType:
    """Load the scripts/add_generated_header.py module as a one-off."""
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "add_generated_header.py"
    spec = importlib.util.spec_from_file_location("add_generated_header", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["add_generated_header"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def normalizer() -> ModuleType:
    return _load_normalizer()


@pytest.fixture(scope="module")
def header_tool() -> ModuleType:
    return _load_header_tool()


_GENERATED_HEADER = """# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'test.ui'
##
## Created by: Qt User Interface Compiler version 6.11.2
##
## WARNING! All changes made to this file will be lost when recompiling UI file!
################################################################################
"""


def _sample_source() -> str:
    return (
        "from PySide6.QtCore import Qt\n"
        "from PySide6.QtWidgets import QFrame, QToolBar, QWidget\n\n"
        "class Ui_Test(object):\n"
        "    def setupUi(self, Test):\n"
        "        self.splitter.setOrientation(Qt.Horizontal)\n"
        "        self.layout.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)\n"
        "        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)\n"
        "        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)\n"
        "        self.edit.setTextInteractionFlags(Qt.TextSelectableByMouse)\n"
        "        self.button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)\n"
        "        self.shortcut.setContext(Qt.ApplicationShortcut)\n"
        "        Test.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)\n"
        "        self.line.setFrameShadow(QFrame.Raised)\n"
        "        # Unknown tokens are preserved: UnknownEnum.OldValue\n"
        "        unknown = UnknownEnum.OldValue\n"
    )


@pytest.fixture
def generated_ui(tmp_path: Path) -> Path:
    p = tmp_path / "ui_test.py"
    p.write_text(_GENERATED_HEADER + _sample_source())
    return p


class TestRewriteGeneratedUi:
    """Unit tests for ``rewrite_generated_ui(path)``."""

    def test_replaces_known_unscoped_qt_tokens(
        self, normalizer: ModuleType, generated_ui: Path
    ) -> None:
        changed = normalizer.rewrite_generated_ui(generated_ui)
        assert changed is True
        text = generated_ui.read_text()

        assert "Qt.Orientation.Horizontal" in text
        assert "Qt.AlignmentFlag.AlignHCenter" in text
        assert "Qt.AlignmentFlag.AlignVCenter" in text
        assert "Qt.ScrollBarPolicy.ScrollBarAlwaysOn" in text
        assert "Qt.ScrollBarPolicy.ScrollBarAlwaysOff" in text
        assert "Qt.TextInteractionFlag.TextSelectableByMouse" in text
        assert "Qt.ToolButtonStyle.ToolButtonTextUnderIcon" in text
        assert "Qt.ShortcutContext.ApplicationShortcut" in text
        assert "QFrame.Shadow.Raised" in text

        assert "Qt.Horizontal" not in text
        assert "Qt.AlignHCenter" not in text
        assert "Qt.AlignVCenter" not in text
        assert "Qt.ScrollBarAlwaysOn" not in text
        assert "Qt.ScrollBarAlwaysOff" not in text
        assert "Qt.TextSelectableByMouse" not in text
        assert "Qt.ToolButtonTextUnderIcon" not in text
        assert "Qt.ApplicationShortcut" not in text
        assert "QFrame.Raised" not in text
        # Already-scoped tokens must not be rewritten.
        assert "Qt.ToolBarArea.TopToolBarArea" in text

    def test_preserves_unknown_tokens_and_header(
        self, normalizer: ModuleType, generated_ui: Path
    ) -> None:
        normalizer.rewrite_generated_ui(generated_ui)
        text = generated_ui.read_text()
        assert _GENERATED_HEADER in text
        assert "UnknownEnum.OldValue" in text
        assert "# Unknown tokens are preserved" in text

    def test_idempotent_second_run(
        self, normalizer: ModuleType, generated_ui: Path
    ) -> None:
        first = normalizer.rewrite_generated_ui(generated_ui)
        assert first is True
        after_first = generated_ui.read_text()
        second = normalizer.rewrite_generated_ui(generated_ui)
        assert second is False
        assert generated_ui.read_text() == after_first

    def test_returns_false_for_generated_file_without_known_tokens(
        self, normalizer: ModuleType, tmp_path: Path
    ) -> None:
        p = tmp_path / "ui_clean.py"
        p.write_text(
            _GENERATED_HEADER
            + (
                "from PySide6.QtCore import Qt\n"
                "class Ui_Clean(object):\n"
                "    def setupUi(self, w):\n"
                '        self.label.setText("already clean")\n'
            )
        )
        assert normalizer.rewrite_generated_ui(p) is False

    def test_rejects_missing_generated_header(
        self, normalizer: ModuleType, tmp_path: Path
    ) -> None:
        p = tmp_path / "not_generated.py"
        p.write_text("x = Qt.Horizontal\n")
        with pytest.raises(ValueError, match="generated"):
            normalizer.rewrite_generated_ui(p)

    def test_rejects_non_python_file(
        self, normalizer: ModuleType, tmp_path: Path
    ) -> None:
        p = tmp_path / "ui_test.txt"
        p.write_text(_GENERATED_HEADER)
        with pytest.raises(ValueError, match="\\.py"):
            normalizer.rewrite_generated_ui(p)


class TestMainCLI:
    """Tests for ``main(argv)``."""

    def test_cli_reports_changed_then_unchanged(
        self, normalizer: ModuleType, generated_ui: Path
    ) -> None:
        assert normalizer.main(["fix_generated_ui_enums.py", str(generated_ui)]) == 0
        assert normalizer.main(["fix_generated_ui_enums.py", str(generated_ui)]) == 0

    def test_cli_rejects_invalid_path(
        self, normalizer: ModuleType, tmp_path: Path
    ) -> None:
        bad = tmp_path / "bad.txt"
        bad.write_text("not a generated file")
        valid = tmp_path / "good.py"
        valid.write_text(_GENERATED_HEADER + "x = 1\n")
        # Mixing a valid and an invalid path must return non-zero.
        assert normalizer.main(["fix_generated_ui_enums.py", str(valid), str(bad)]) != 0


_RCC_SIGNATURE_BLOCK = """# Resource object code (Python 3)
# Created by: object code
# Created by: The Resource Compiler for Qt version 6.11.2
# WARNING! All changes made in this file will be lost!
"""


class TestAddGeneratedHeader:
    """Tests for ``add_generated_header.add_header(path)``."""

    def test_inserts_header_after_coding_cookie(
        self, header_tool: ModuleType, generated_ui: Path
    ) -> None:
        assert header_tool.add_header(generated_ui) is True
        lines = generated_ui.read_text().splitlines()
        # PEP 263: the coding cookie must stay within the first two lines.
        assert lines[0].startswith("# -*- coding")
        assert "DO NOT HAND-EDIT" in lines[1]
        assert "compile_ui.sh" in lines[2]
        # The stock uic signature block is preserved below the header.
        assert "Form generated from reading UI file" in generated_ui.read_text()

    def test_idempotent_second_run(
        self, header_tool: ModuleType, generated_ui: Path
    ) -> None:
        assert header_tool.add_header(generated_ui) is True
        after_first = generated_ui.read_text()
        assert header_tool.add_header(generated_ui) is False
        assert generated_ui.read_text() == after_first

    def test_rejects_non_generated_python(
        self, header_tool: ModuleType, tmp_path: Path
    ) -> None:
        p = tmp_path / "hand_written.py"
        p.write_text("x = 1\n")
        with pytest.raises(ValueError, match="generator signature"):
            header_tool.add_header(p)

    def test_rejects_non_python_file(
        self, header_tool: ModuleType, tmp_path: Path
    ) -> None:
        p = tmp_path / "ui_test.txt"
        p.write_text(_GENERATED_HEADER)
        with pytest.raises(ValueError, match="\\.py"):
            header_tool.add_header(p)

    def test_rcc_signature_detected_header_at_line_one(
        self, header_tool: ModuleType, tmp_path: Path
    ) -> None:
        p = tmp_path / "ui_test_rc.py"
        p.write_text(_RCC_SIGNATURE_BLOCK + "qt_resource_data = b''\n")
        assert header_tool.add_header(p) is True
        lines = p.read_text().splitlines()
        assert "DO NOT HAND-EDIT" in lines[0]

    def test_detection_still_works_on_headered_output(
        self, header_tool: ModuleType, normalizer: ModuleType, generated_ui: Path
    ) -> None:
        header_tool.add_header(generated_ui)
        # Recognition is content-based, not line-1-based: the project header
        # must not break the signature detection the post-processors rely on.
        assert normalizer._is_generated_file(generated_ui, generated_ui.read_text())
        assert header_tool.is_generated_file(generated_ui.read_text())

    def test_cli_rejects_non_generated_path(
        self, header_tool: ModuleType, tmp_path: Path
    ) -> None:
        bad = tmp_path / "hand_written.py"
        bad.write_text("x = 1\n")
        valid = tmp_path / "ui_test.py"
        valid.write_text(_GENERATED_HEADER + "x = 1\n")
        assert header_tool.main(["add_generated_header.py", str(valid), str(bad)]) != 0
        # The valid file was still processed.
        assert "DO NOT HAND-EDIT" in valid.read_text()
