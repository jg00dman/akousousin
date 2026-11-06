#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
: "${WINE:?Set WINE to the patched Wine loader}"
export WINEPREFIX=${WINEPREFIX:-"$project_dir/build/test-prefix"}
export WINEDEBUG=${WINEDEBUG:--all}
if [ -e "$WINEPREFIX" ] && [ ! -f "$WINEPREFIX/.akousousin-test-prefix" ]; then
    echo "Refusing to modify an existing prefix not created by this test script" >&2
    exit 1
fi
mkdir -p "$WINEPREFIX"
touch "$WINEPREFIX/.akousousin-test-prefix"
echo '=== Initialize disposable Wine prefix (120-second limit) ==='
timeout --signal=TERM --kill-after=10s 120s "$WINE" wineboot.exe -u
 echo '=== Register test voice (45-second limit) ==='
python3 "$project_dir/scripts/register-voice.py" --make-default --output "$project_dir/build/test-voice.reg"
timeout --signal=TERM --kill-after=10s 45s "$WINE" regedit.exe /S "Z:$project_dir/build/test-voice.reg"
echo '=== Run all 13 deterministic Akousousin integration tests ==='
python3 "$project_dir/tests/test_integration.py"
