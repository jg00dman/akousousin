#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
: "${WINE:?Set WINE to the patched Wine loader}"
export WINEPREFIX=${WINEPREFIX:-"$project_dir/build/test-prefix"}
export WINEDEBUG=${WINEDEBUG:--all}
if [ -e "$WINEPREFIX" ] && [ ! -f "$WINEPREFIX/.opensapi-test-prefix" ]; then
    echo "Refusing to modify an existing prefix not created by this test script" >&2
    exit 1
fi
mkdir -p "$WINEPREFIX"
touch "$WINEPREFIX/.opensapi-test-prefix"
"$WINE" wineboot.exe -u
python3 "$project_dir/scripts/register-voice.py" --make-default --output "$project_dir/build/test-voice.reg"
"$WINE" regedit.exe /S "Z:$project_dir/build/test-voice.reg"
python3 "$project_dir/tests/test_integration.py"
