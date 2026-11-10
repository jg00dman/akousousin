# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Exercise the real unpacked package with no AppImage runtime or FUSE."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

with tempfile.TemporaryDirectory(prefix='akousousin-tar-') as directory:
    root = Path(directory)
    with tarfile.open(sys.argv[1]) as archive:
        archive.extractall(root / 'unpacked', filter='data')
    source = root / 'unpacked/Akousousin'
    env = dict(os.environ, XDG_DATA_HOME=str(root / 'data'), XDG_CONFIG_HOME=str(root / 'config'),
               XDG_STATE_HOME=str(root / 'state'), XDG_RUNTIME_DIR=str(root / 'run'),
               PYINSTALLER_RESET_ENVIRONMENT='1')
    for name in ('APPIMAGE', 'APPDIR', 'AKOUSOUSIN_RESOURCES'):
        env.pop(name, None)
    (root / 'run').mkdir(mode=0o700)
    prefix = root / 'install with spaces'
    def run(*args):
        result = subprocess.run(args, env=env, check=True, capture_output=True, text=True, timeout=90)
        return result.stdout.strip()
    assert run(str(source / 'akousousin'), '--protocol-version') == '2'
    run(str(source / 'install.sh'), '--bundle-prefix', str(prefix))
    installed = prefix / 'lib/akousousin'
    assert run(str(prefix / 'bin/akousousin'), '--protocol-version') == '2'
    assert json.loads((installed / 'resources/build.json').read_text())['distribution'] == 'linux-tar'
    assert (installed / 'licenses/Akousousin-GPL-3.0.txt').is_file()
    assert (installed / 'licenses/Engine-LGPL-2.1.txt').is_file()
    desktop = root / 'data/applications/org.akousousin.Akousousin.desktop'
    assert 'NoDisplay=false' in desktop.read_text() and str(installed) in desktop.read_text()
    dispatcher = root / 'data/Akousousin/speech-dispatcher-module'
    assert dispatcher.is_file() and str(installed / 'akousousin') in dispatcher.read_text()
    preferences = json.loads((root / 'config/Akousousin/settings.json').read_text())
    assert preferences['speechd_setup_pending'], 'Model-free installation must retain the previous default until a voice is ready'
    run(str(source / 'install.sh'), '--bundle-prefix', str(prefix))
    run(str(installed / 'uninstall.sh'))
    assert not installed.exists()
    assert not (prefix / 'bin/akousousin').exists()
    assert not dispatcher.exists(), 'Uninstall left a dangling Speech Dispatcher launcher'
    print('PASS: no-FUSE bundle launch, install, upgrade, menu/default speech setup, licences and uninstall')
