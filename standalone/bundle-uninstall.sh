#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
set -eu
bundle_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
unset APPIMAGE APPDIR AKOUSOUSIN_RESOURCES
exec "$bundle_dir/akousousin" --uninstall-bundle "$bundle_dir" "$@"
