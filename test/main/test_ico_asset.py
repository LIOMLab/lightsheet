"""Asset tests for the committed ``lightsheet.ico`` shortcut icon.

Pins three contracts:

1. ``lightsheet/resources/lightsheet.ico`` exists in the repo, opens as a
   valid ICO, and embeds the multi-resolution size set the Windows shell
   needs (16/32/48/256 px at minimum).
2. ``scripts/build_icon.py`` regenerates an ``.ico`` with the identical
   size set — the committed binary is reproducible from the committed
   ``liom_logo.png`` source.
3. ``pyproject.toml`` declares ``*.ico`` in the ``lightsheet.resources``
   package-data so the icon ships inside any installed copy.
"""

import subprocess
import sys
import tomllib
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
ICO_PATH = REPO_ROOT / "lightsheet" / "resources" / "lightsheet.ico"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_icon.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"

REQUIRED_SIZES = {(16, 16), (32, 32), (48, 48), (256, 256)}


def _ico_sizes(path: Path) -> set[tuple[int, int]]:
    """Return the set of embedded image sizes in an ``.ico`` file."""
    with Image.open(path) as img:
        assert img.format == "ICO"
        return set(img.ico.sizes())


def test_ico_file_exists_and_is_valid() -> None:
    """The committed icon exists, is ICO format, and embeds the required sizes."""
    assert ICO_PATH.is_file(), f"missing committed icon: {ICO_PATH}"
    sizes = _ico_sizes(ICO_PATH)
    assert REQUIRED_SIZES <= sizes, (
        f"icon missing sizes {REQUIRED_SIZES - sizes}; embedded: {sorted(sizes)}"
    )


def test_build_icon_regenerates_identical_sizes(tmp_path: Path) -> None:
    """``scripts/build_icon.py --output <tmp>`` exits 0 and produces an
    ``.ico`` whose embedded size set matches the committed asset."""
    committed_sizes = _ico_sizes(ICO_PATH)
    out = tmp_path / "lightsheet.ico"
    result = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), "--output", str(out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"build_icon.py failed\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert _ico_sizes(out) == committed_sizes


def test_ico_in_package_data() -> None:
    """``*.ico`` is declared in the ``lightsheet.resources`` package-data."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    package_data = data["tool"]["setuptools"]["package-data"]["lightsheet.resources"]
    assert "*.ico" in package_data
