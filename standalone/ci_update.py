# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Exercise verified replacement and the real packaged refresh command.

The replacement payload is the just-built AppImage; no live release or user
installation is modified. Only the final GUI launch is intercepted.
"""
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

from akousousin_app import updates, __version__, appimage_install

source = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='akousousin-update-') as directory:
    root = Path(directory)
    image = root / 'Akousousin.AppImage'
    shutil.copy2(source, image)
    config = root / 'settings.json'
    os.environ.update(APPIMAGE=str(image), APPIMAGE_EXTRACT_AND_RUN='1',
                      XDG_DATA_HOME=str(root / 'data'), XDG_CONFIG_HOME=str(root / 'config'),
                      XDG_STATE_HOME=str(root / 'state'), XDG_RUNTIME_DIR=str(root / 'run'))
    update = {'version': __version__, 'url': 'https://example.invalid/test-only', 'size': source.stat().st_size,
              'sha256': hashlib.file_digest(source.open('rb'), 'sha256').hexdigest()}
    import subprocess
    real_popen = subprocess.Popen
    def start(command, **kwargs):
        if '--configure' in command:
            return None
        return real_popen(command, **kwargs)
    with patch.object(updates.resources, 'root', return_value=Path(__file__).resolve().parents[1] / 'build/standalone-package/resources'), \
            patch.object(updates.urllib.request, 'urlopen', side_effect=lambda *args, **kwargs: source.open('rb')), \
            patch.object(updates.subprocess, 'Popen', side_effect=start):
        backup = updates.install(update, config)
    assert hashlib.file_digest(image.open('rb'), 'sha256').hexdigest() == update['sha256']
    assert hashlib.file_digest(backup.open('rb'), 'sha256').hexdigest() == update['sha256']
    assert config.is_file(), 'Packaged registration refresh did not bootstrap its settings'
    print('PASS: verified AppImage staging, replacement, backup and packaged registration refresh')

    # Exercise relocation of the real package, including registration refresh
    # from its final path, persistent artwork and a visible menu entry.
    with patch.object(updates.resources, 'root', return_value=Path(__file__).resolve().parents[1] / 'build/standalone-package/resources'), \
            patch.object(updates.subprocess, 'Popen', side_effect=start):
        installed = appimage_install.install(config)
    assert not image.exists(), 'Relocation retained the unchanged source AppImage'
    assert installed == root / 'data/Akousousin/Akousousin-x86_64.AppImage'
    assert hashlib.file_digest(installed.open('rb'), 'sha256').hexdigest() == update['sha256']
    entry = root / 'data/applications/org.akousousin.Akousousin.desktop'
    assert 'NoDisplay=false' in entry.read_text() and str(installed) in entry.read_text()
    assert (root / 'data/Akousousin/icons/akousousin.png').is_file()
    print('PASS: packaged AppImage relocation, registration refresh and persistent application-menu shortcut')
