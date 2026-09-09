#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# Find all lightsheet/gui .ui files (resource .qrc files are excluded for now).
UI_FILES=()
while IFS= read -r ui; do
    UI_FILES+=("$ui")
done < <(find lightsheet/gui -name "*.ui" -not -name "*.qrc")

GENERATED=()
for ui in "${UI_FILES[@]}"; do
    out="${ui%.ui}.py"
    echo "Compiling $ui -> $out"
    uv run pyside6-uic --from-imports -o "$out" "$ui"
    GENERATED+=("$out")
done

if [ ${#GENERATED[@]} -gt 0 ]; then
    uv run python scripts/fix_generated_ui_enums.py "${GENERATED[@]}"
fi

uv run python scripts/tokenize_forms.py
