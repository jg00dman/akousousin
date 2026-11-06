#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
set -eu
project_dir=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
wine_source=${WINE_SRC:-/workspace/wine}
wine_build=${WINE_BUILD:-/workspace/build-wine}
cross_cc=${CC_PE:-x86_64-w64-mingw32-gcc}
mkdir -p "$project_dir/build"
"$cross_cc" -std=c11 -Wall -Wextra -municode \
    -o "$project_dir/build/sapi-probe.exe" "$project_dir/examples/sapi-probe.c" \
    -lole32 -loleaut32 -lsapi -luuid
# MinGW does not ship the SAPI engine DDK. Use Wine's generated DDK headers.
"$cross_cc" -std=c11 -Wall -Wextra -Wno-unused-parameter -municode \
    -I"$wine_build/include" -I"$wine_source/include" -I"$wine_source/include/msvcrt" \
    -D__WINESRC__ -D__WINE_PE_BUILD \
    -o "$project_dir/build/engine-probe.exe" "$project_dir/tests/engine-probe.c" \
    -lole32 -lsapi -luuid -lucrt

# Registry enumeration used by .NET System.Speech voice attributes.
"$cross_cc" -std=c11 -Wall -Wextra -municode \
    -I"$wine_build/include" -I"$wine_source/include" -I"$wine_source/include/msvcrt" \
    -D__WINESRC__ -D__WINE_PE_BUILD \
    -o "$project_dir/build/token-enum-probe.exe" "$project_dir/tests/token-enum-probe.c" \
    -lole32 -ladvapi32 -lsapi -luuid -lucrt
