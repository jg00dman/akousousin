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

from akousousin_app import updates

source = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='akousousin-update-') as directory:
    root = Path(directory)
    image = root / 'Akousousin.AppImage'
    shutil.copy2(source, image)
    config = root / 'settings.json'
    os.environ.update(APPIMAGE=str(image), APPIMAGE_EXTRACT_AND_RUN='1',
                      XDG_DATA_HOME=str(root / 'data'), XDG_CONFIG_HOME=str(root / 'config'),
                      XDG_STATE_HOME=str(root / 'state'), XDG_RUNTIME_DIR=str(root / 'run'))
    update = {'url': 'https://example.invalid/test-only', 'size': source.stat().st_size,
              'sha256': hashlib.file_digest(source.open('rb'), 'sha256').hexdigest()}
    import subprocess
    real_popen = subprocess.Popen
    def start(command, **kwargs):
        if '--configure' in command:
            return None
        return real_popen(command, **kwargs)
    with patch.object(updates.urllib.request, 'urlopen', side_effect=lambda *args, **kwargs: source.open('rb')), \
            patch.object(updates.subprocess, 'Popen', side_effect=start):
        backup = updates.install(update, config)
    assert hashlib.file_digest(image.open('rb'), 'sha256').hexdigest() == update['sha256']
    assert hashlib.file_digest(backup.open('rb'), 'sha256').hexdigest() == update['sha256']
    assert config.is_file(), 'Packaged registration refresh did not bootstrap its settings'
    print('PASS: verified AppImage staging, replacement, backup and packaged registration refresh')
