# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Focus verification for GNOME Shell. Only opaque window IDs leave the shell."""
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

from . import resources, runtime


def on_gnome():
    return 'gnome' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':')


def install_extension():
    extension = 'focus@akousousin.org'
    env = runtime.host_environment()
    installed = subprocess.run(['gnome-extensions', 'list'], check=True, capture_output=True,
                               text=True, env=env).stdout.splitlines()
    folder = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'gnome-shell/extensions' / extension
    if extension not in installed and not folder.exists():
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / (extension + '.zip')
            with zipfile.ZipFile(file, 'w') as archive:
                for name in ('extension.js', 'metadata.json'):
                    archive.write(resources.root() / 'gnome-focus' / name, name)
            subprocess.run(['gnome-extensions', 'install', str(file)], check=True, env=env)
    result = subprocess.run(['gnome-extensions', 'enable', extension], capture_output=True, env=env)
    if result.returncode:
        return 'Sign out and back in, then enable Akousousin Focus in GNOME Extensions.'
    return 'Akousousin Focus enabled. You can now enable the dictation shortcut.'
