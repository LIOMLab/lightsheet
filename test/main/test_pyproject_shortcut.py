"""Verify the no-console ``lightsheetw`` gui-script entry point.

One test parses the source ``pyproject.toml``; the other asserts on the
installed distribution metadata (requires an editable install, regenerated
by ``uv sync`` before the test is exercised).
"""

import importlib.metadata
import tomllib
from pathlib import Path


def test_gui_script_entry_point_in_pyproject() -> None:
    """``pyproject.toml`` declares ``lightsheetw = "lightsheet.__main__:main"``."""
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    assert data["project"]["gui-scripts"]["lightsheetw"] == "lightsheet.__main__:main"


def test_gui_script_entry_point_registered() -> None:
    """The installed distribution exposes a ``gui_scripts`` entry point
    matching the declaration."""
    eps = importlib.metadata.entry_points(group="gui_scripts")
    matches = [
        e
        for e in eps
        if e.name == "lightsheetw" and e.value == "lightsheet.__main__:main"
    ]
    assert matches, (
        "lightsheetw = lightsheet.__main__:main not registered in gui_scripts"
    )
