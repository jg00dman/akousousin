# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""--purge: remove Akousousin and everything it keeps, as if it was never installed.

Unlike --uninstall (Wine registrations only) and --uninstall-bundle (application
files and the start-at-login entry), this also deletes voices, speech models and settings."""
import os
from pathlib import Path
import shutil
import sys

from . import resources, runtime, settings
from .install import Installer
from .desktop_identity import APP_ID, MARKER
from .linux_bundle import RECEIPT
from . import linux_bundle, speech_dispatcher

WARNING = ('This removes Akousousin completely: the application, its Wine speech registration, '
           'its Speech Dispatcher and Spiel registrations, and all downloaded voices, speech models and settings. '
           'It cannot be undone.')


def data_home():
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))


def bundle_target(prefix=None):
    """The tar installation to remove: the running one, else the one under prefix (~/.local)."""
    candidates = [Path(sys.executable).resolve().parent]
    candidates.append(Path(prefix or Path.home() / '.local').expanduser().resolve() / 'lib/akousousin')
    for candidate in candidates:
        if (candidate / RECEIPT).is_file():
            return candidate
    return None


def desktop_entries():
    """Launchers Akousousin wrote (managed identities and the read-selection action)."""
    applications = data_home() / 'applications'
    found = [applications / 'akousousin-read-selection.desktop']
    for entry in applications.glob(APP_ID + '*.desktop'):
        try:
            if MARKER in entry.read_text(encoding='utf-8'):
                found.append(entry)
        except OSError:
            pass
    return [entry for entry in found if entry.is_file() and not entry.is_symlink()]


def purge(settings_path, wine_prefix=None, wine=None, bundle_prefix=None, report=print):
    """Each step is independent: one failing doesn't stop the rest. Returns the problems."""
    problems = []

    def step(name, action):
        try:
            action()
        except Exception as error:  # report and carry on: the point is to remove everything we can
            problems.append(f'{name}: {error}')

    config = settings.load(settings_path) if Path(settings_path).exists() else {}
    step('quit', lambda: runtime.call(settings_path, {'command': 'quit'}, launch=False))
    prefix = wine_prefix or config.get('wine_prefix')
    if prefix and Path(prefix).is_dir():
        step('Wine registration', lambda: Installer(resources.root(), prefix, wine or config.get('wine') or None)
             .uninstall())
    if os.name == 'posix' and speech_dispatcher.dispatcher_paths()[1].exists():
        step('Speech Dispatcher', lambda: speech_dispatcher.configure(settings_path, remove=True))
    if sys.platform == 'linux':
        from . import spiel
        step('Spiel', lambda: spiel.configure(settings_path, remove=True))
    from . import startup
    step('start at login', startup.disable)
    for entry in desktop_entries():
        step(str(entry), entry.unlink)
    target = bundle_target(bundle_prefix)
    # Last: this may delete the program that is running (already loaded, so that's fine on Linux).
    for folder in (Path(settings_path).parent, settings.config_path().parent, settings.data_path()):
        if folder.is_dir() and folder.name == 'Akousousin':
            step(str(folder), lambda folder=folder: shutil.rmtree(folder))
    if target is not None:
        step('application files', lambda: report(linux_bundle.uninstall(target)))
    for problem in problems:
        report('Not removed: ' + problem)
    return problems
