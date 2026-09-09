"""Generate ``lightsheet/resources/lightsheet.ico`` from the committed logo.

Dev tool: converts ``lightsheet/gui/resources/liom_logo.png`` into a
multi-resolution Windows ``.ico`` for the desktop/Start Menu shortcuts.
The generated ``.ico`` is committed to the repo so the shortcut's
``IconLocation`` resolves even before ``uv sync`` has run on a fresh
checkout. Re-run this script whenever the logo source changes.
"""

import argparse
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "lightsheet" / "gui" / "resources" / "liom_logo.png"
DEFAULT_OUTPUT = REPO_ROOT / "lightsheet" / "resources" / "lightsheet.ico"

# Sizes the Windows shell picks from: 16/32/48 cover the shell's small,
# regular, and large icon slots; 256 is the high-DPI/Vista+ PNG-compressed
# entry; 64/128 fill the intermediate scaling steps.
ICON_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def build_icon(source: Path, output: Path) -> None:
    """Convert ``source`` (a PNG) into a multi-resolution ICO at ``output``."""
    with Image.open(source) as src:
        if src.mode != "RGBA":
            src = src.convert("RGBA")
        output.parent.mkdir(parents=True, exist_ok=True)
        src.save(output, format="ICO", sizes=ICON_SIZES)


def main() -> None:
    """Parse arguments and build the icon."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"PNG source image (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"ICO output path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()
    build_icon(args.source, args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
