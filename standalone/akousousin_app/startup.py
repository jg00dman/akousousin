# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Start Akousousin when the user logs in.

Linux uses an XDG autostart entry, which GNOME, KDE Plasma, Xfce, Cinnamon and
MATE all honour. Windows uses the per-user Run key. Either one runs
``akousousin --background``: the controller starts with its tray icon and
shortcuts, opens no window, and loads voices and dictation if the user wants
them ready.

Akousousin owns only an entry it wrote (marked on Linux, by value name on
Windows); a user's own autostart file of the same name is never changed.
"""
import os
from pathlib import Path
import tempfile

from . import runtime
from .desktop_identity import APP_ID, MARKER, desktop_exec

ARGUMENT = '--background'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_VALUE = 'Akousousin'


def supported():
    return os.name == 'nt' or (os.name == 'posix' and not os.environ.get('FLATPAK_ID'))


def invocation():
    return runtime.command(ARGUMENT)


# Linux ----------------------------------------------------------------------
def autostart_file():
    base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return base / 'autostart' / (APP_ID + '.desktop')


def _ours(path):
    try:
        return path.is_file() and not path.is_symlink() and MARKER in path.read_text(encoding='utf-8')
    except OSError:
        return False


def _icon():
    """A stable copy of the icon: the AppImage's own files vanish when it exits."""
    from . import resources, settings
    import shutil
    icon = settings.data_path() / 'icons/akousousin.png'
    source = resources.root() / 'akousousin.png'
    if source.is_file() and not icon.is_file():
        icon.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, icon)
    return icon if icon.is_file() else APP_ID


def _entry():
    return ('[Desktop Entry]\nType=Application\nName=Akousousin\n'
            'Comment=Reading aloud and dictation, ready at login\n'
            'Exec=' + desktop_exec(invocation()) + '\n'
            'Icon=' + str(_icon()) + '\nTerminal=false\n'
            'X-GNOME-Autostart-enabled=true\nX-KDE-autostart-phase=2\n' + MARKER + '\n')


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, prefix='.' + path.name,
                                         delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
        temporary.chmod(0o644)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


# Windows --------------------------------------------------------------------
def _command_line():
    import subprocess
    return subprocess.list2cmdline(invocation())


def _run_key(access):
    import winreg
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, access)


def _registered():
    import winreg
    try:
        with _run_key(winreg.KEY_READ) as key:
            return winreg.QueryValueEx(key, RUN_VALUE)[0]
    except OSError:
        return None


# Public ---------------------------------------------------------------------
def enabled():
    if os.name == 'nt':
        return _registered() is not None
    return _ours(autostart_file())


def enable():
    if os.name == 'nt':
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, _command_line())
        return
    path = autostart_file()
    if path.exists() and not _ours(path):
        raise RuntimeError('Another start-at-login entry for Akousousin already exists: ' + str(path))
    _write(path, _entry())


def disable():
    if os.name == 'nt':
        import winreg
        try:
            with _run_key(winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, RUN_VALUE)
        except FileNotFoundError:
            pass
        return
    path = autostart_file()
    if _ours(path):
        path.unlink()


def disable_if_inside(folder):
    """Remove the entry if it starts a program inside folder (used when that folder is uninstalled)."""
    path = autostart_file()
    if _ours(path) and str(Path(folder).resolve()) in path.read_text(encoding='utf-8'):
        path.unlink()


def set_enabled(value):
    enable() if value else disable()
    return enabled()


def refresh():
    """Point an existing entry at the program now running (an AppImage may have moved)."""
    if os.name == 'nt':
        current = _registered()
        if current is not None and current != _command_line():
            enable()
        return
    path = autostart_file()
    if _ours(path) and path.read_text(encoding='utf-8') != _entry():
        _write(path, _entry())
