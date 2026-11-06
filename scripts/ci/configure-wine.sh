#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
# This recipe, the patch and the toolchain identity define Wine cache compatibility.
# Run from wine-build; keep compiler flags here rather than in packaging helpers.
set -euo pipefail
../wine-src/configure --enable-win64 --disable-tests --prefix=/usr \
    --without-oss --disable-winemenubuilder CFLAGS='-O2' CXXFLAGS='-O2'
