# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Install, check and uninstall the Windows installer silently (CI runs as administrator)."""
import os
from pathlib import Path
import subprocess
import sys
import time

setup = Path(sys.argv[1]).resolve()
folder = Path(os.environ['ProgramFiles']) / 'Akousousin'
menu = Path(os.environ['ProgramData']) / 'Microsoft/Windows/Start Menu/Programs/Akousousin.lnk'
log = Path('build/standalone-ci/windows-installer.log').resolve()
log.parent.mkdir(parents=True, exist_ok=True)

subprocess.run([str(setup), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', f'/LOG={log}'],
               check=True, timeout=600)
executable = folder / 'akousousin.exe'
assert executable.is_file(), 'akousousin.exe was not installed'
assert menu.is_file(), 'Start menu shortcut is missing'
uninstaller = next(folder.glob('unins*.exe'))
version = subprocess.run([str(executable), '--version'], capture_output=True, text=True, timeout=60)
print('Installed:', version.stdout.strip() or version.stderr.strip(), flush=True)
assert 'Akousousin' in version.stdout + version.stderr, 'Installed program did not report its version'
# The GUI build must still write command-line output to a caller's pipe.
status = subprocess.run([str(executable), '--status'], capture_output=True, text=True, timeout=60)
print('Status:', status.stdout.strip(), status.stderr.strip(), flush=True)
assert status.returncode == 0 and status.stdout.strip().startswith('{'), 'No command-line output from the GUI build'
print('PASS: installer adds the program and Start menu entry; command-line output works', flush=True)

removal_log = log.with_name('windows-uninstaller.log')
try:
    subprocess.run([str(uninstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', f'/LOG={removal_log}'],
                   check=True, timeout=300)
except subprocess.TimeoutExpired:
    # A hidden dialog would block here; show what is still running.
    print(subprocess.run(['tasklist', '/V'], capture_output=True, text=True).stdout, flush=True)
    if removal_log.exists():
        print(removal_log.read_text(errors='replace'), flush=True)
    raise
deadline = time.monotonic() + 60  # the uninstaller finishes in a copy of itself
while (executable.exists() or menu.exists()) and time.monotonic() < deadline:
    time.sleep(1)
assert not executable.exists(), 'Uninstall left akousousin.exe behind'
assert not menu.exists(), 'Uninstall left the Start menu shortcut behind'
print('PASS: uninstaller removes the program and Start menu entry', flush=True)
