# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Exercise built readers with no host clipboard tools, on a private Xvfb display."""
import os
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

from akousousin_app import resources, selection

package = Path('build/standalone-package/Akousousin/resources').resolve()
with patch.object(resources, 'root', return_value=package), patch.dict(os.environ, {'PATH':'/no-host-clipboard-tools'}):
    for name, flag in [('wl-paste', '--version'), ('xclip', '-version')]:
        command, environment = selection.clipboard_reader(name, name)
        result = subprocess.run([command, flag], env=environment, capture_output=True, timeout=5, check=True)
        print(name, (result.stdout + result.stderr).decode().strip(), flush=True)
    with patch.dict(os.environ, {'XDG_SESSION_TYPE':'x11', 'WAYLAND_DISPLAY':'inherited-unused'}):
        binary, environment = selection.clipboard_reader('xclip', 'xclip')
        owners = []
        try:
            for name, text in [('primary', 'Selected café Ελληνικά'), ('clipboard', 'Copied text עברית')]:
                process = subprocess.Popen([binary, '-selection', name, '-in', '-quiet'], env=environment,
                                           stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                owners.append(process)
                process.stdin.write(text.encode()); process.stdin.close()
                deadline = time.monotonic() + 5
                while True:
                    try:
                        actual = selection.selected_text(clipboard=name == 'clipboard')
                        if actual == text:
                            break
                    except RuntimeError:
                        pass
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise AssertionError('Bundled xclip could not read ' + name)
                    time.sleep(.05)
            print('PASS: bundled clipboard readers, private libraries, X11 PRIMARY and clipboard Unicode', flush=True)
        finally:
            for process in owners:
                process.terminate()
                try:
                    process.wait(3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(3)
                process.stderr.close()
