# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Environment for host executables launched from an embedded Python runtime."""
import os


def host_environment(environment=None):
    value = dict(os.environ if environment is None else environment)
    # ORIG can itself name a previous AppImage mount after a nested launch.
    # Keep audio/session routing variables, but let system tools load host libs.
    for name in ('LD_LIBRARY_PATH', 'LD_LIBRARY_PATH_ORIG', 'LD_PRELOAD',
                 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
        value.pop(name, None)
    return value
