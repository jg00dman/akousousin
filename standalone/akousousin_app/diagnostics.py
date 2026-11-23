# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""A plain-text report for bug reports. It never includes text that was read or dictated."""
import json
import os
import platform
import sys

from . import __version__, settings


def report(path, status=None):
    config = settings.load(path)
    lines = [f'Akousousin {__version__}',
             f'Platform: {platform.platform()} ({platform.machine()})',
             f'Python: {sys.version.split()[0]}',
             f'Desktop: {os.environ.get("XDG_CURRENT_DESKTOP", "unknown")} '
             f'({"Wayland" if os.environ.get("WAYLAND_DISPLAY") else "X11" if os.environ.get("DISPLAY") else "no display"})',
             f'AppImage: {"yes" if os.environ.get("APPIMAGE") else "no"}']
    if os.name != 'nt':
        from akousousin_backend import audio_system
        lines.append(f'Audio: {audio_system.describe()}')
    try:
        from PySide6 import __version__ as qt
        lines.append(f'PySide6: {qt}')
    except ImportError:
        pass
    lines += ['', 'Settings:', json.dumps(config, indent=2, ensure_ascii=False, sort_keys=True)]
    if status is not None:
        dictation = dict(status.dictation or {})
        dictation.pop('results', None)  # transcripts stay private
        reading = dict(status.reading)
        lines += ['', 'Speech service:', json.dumps(status.speech, indent=2),
                  '', 'Dictation:', json.dumps(dictation, indent=2, ensure_ascii=False),
                  '', 'Reading:', json.dumps({k: v for k, v in reading.items() if k != 'text'}, indent=2, ensure_ascii=False),
                  '', 'Downloads:', json.dumps([{k: v for k, v in item.items() if k in ('name', 'status', 'error')}
                                               for item in status.downloads], indent=2, ensure_ascii=False)]
        if status.error:
            lines += ['', 'Status error: ' + status.error]
    return '\n'.join(lines) + '\n'
