# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Per-user controller IPC. Session ownership belongs to Akousousin, not launchers."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from . import settings


def directory(path=None):
    if os.name == 'nt':
        base = settings.data_path() / 'run'
    else:
        base = Path(os.environ.get('XDG_RUNTIME_DIR', f'/tmp/akousousin-{os.getuid()}')) / 'Akousousin'
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != 'nt':
        if base.stat().st_uid != os.getuid() or base.is_symlink():
            raise RuntimeError('Unsafe Akousousin runtime directory')
        base.chmod(0o700)
    return base


def name(path):
    key = hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()[:16]
    return str(directory() / key) if os.name != 'nt' else 'Akousousin-' + key


def command(*args):
    # Keep the AppImage invocation alive for as long as its controller is running.
    # No Python/Piper runtime is copied into the user's data directory.
    image = os.environ.get('APPIMAGE')
    if image and Path(image).is_file():
        # Wine itself may be an AppImage. Its inherited APPIMAGE is not ours.
        from .updates import is_appimage
        if is_appimage():
            return [image, *args]
    if getattr(sys, 'frozen', False):
        return [sys.executable, *args]
    return [sys.executable, '-m', 'akousousin_app.main', *args]


def call(path, request, launch=True, timeout=85):
    if os.name == 'nt':
        return windows_call(path, request, launch)
    import socket
    def connect():
        connection = socket.socket(socket.AF_UNIX)
        connection.settimeout(.5)
        try:
            connection.connect(name(path))
        except OSError:
            connection.close()
            return None
        return connection
    connection = connect()
    if connection is None:
        if not launch:
            return None
        launch_controller(path)
        deadline = time.monotonic() + 20
        while connection is None and time.monotonic() < deadline:
            time.sleep(.1)
            connection = connect()
        if connection is None:
            raise RuntimeError(f'Akousousin could not start; see {log_path()}')
    with connection:
        connection.settimeout(timeout)
        connection.sendall(json.dumps(request).encode() + b'\n')
        data = bytearray()
        while b'\n' not in data and len(data) < 1024 * 1024:
            chunk = connection.recv(8192)
            if not chunk:
                raise RuntimeError('Akousousin controller disconnected')
            data.extend(chunk)
    return result(data)


def owner_gone():
    """For a helper running from its owner's AppImage mount: whether the owner exited.

    The mount, and so the helper's own files, disappears with the owner.
    """
    owner = os.environ.get('AKOUSOUSIN_OWNER_PID', '')
    return owner.isdigit() and os.getppid() != int(owner)


def replace_stale(path):
    """Quit a controller left behind by a login session that has ended.

    It would answer requests but has no screen, no tray icon and shortcuts tied
    to the old session, so a new login must not hand over to it.
    """
    if os.name == 'nt':
        return False
    from . import login_session
    mine = login_session.current()
    if not mine:
        return False
    try:
        status = call(path, {'command': 'status'}, launch=False, timeout=5)
    except (OSError, RuntimeError, ValueError):
        return False
    theirs = (status or {}).get('login_session')
    if not theirs or theirs == mine or login_session.running(theirs):
        return False
    try:
        call(path, {'command': 'quit'}, launch=False, timeout=30)
    except (OSError, RuntimeError, ValueError):
        pass
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            if call(path, {'command': 'status'}, launch=False, timeout=2) is None:
                return True
        except (OSError, RuntimeError, ValueError):
            return True
        time.sleep(.2)
    return True


def environment():
    value = os.environ.copy()
    # A detached controller/panel is an independent frozen application, not a
    # multiprocessing child inheriting the caller's PyInstaller bootloader state.
    value['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return value


def host_environment():
    from akousousin_backend.host import host_environment as clean
    return clean(environment())


def launch_controller(path):
    with log_path().open('ab') as output:
        options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {
            'start_new_session': True}
        subprocess.Popen(command('--controller', '--settings', str(path)), stdin=subprocess.DEVNULL,
                         stdout=output, stderr=output, env=environment(), **options)


def result(data):
    value = json.loads(data.split(b'\n', 1)[0])
    if 'error' in value:
        raise RuntimeError(value['error'])
    return value


_application = None


def initialize():
    global _application
    if os.name == 'nt' and _application is None:
        from PySide6.QtCore import QCoreApplication
        _application = QCoreApplication.instance() or QCoreApplication([])


def windows_call(path, request, launch):
    from PySide6.QtCore import QIODevice
    from PySide6.QtNetwork import QLocalSocket
    initialize()
    socket = QLocalSocket()
    socket.connectToServer(name(path), QIODevice.ReadWrite)
    if not socket.waitForConnected(500):
        if not launch:
            return None
        launch_controller(path)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            socket.abort()
            socket.connectToServer(name(path), QIODevice.ReadWrite)
            if socket.waitForConnected(300):
                break
            time.sleep(.1)
        else:
            raise RuntimeError(f'Akousousin could not start; see {log_path()}')
    socket.write(json.dumps(request).encode() + b'\n')
    socket.waitForBytesWritten(3000)
    data = bytearray()
    deadline = time.monotonic() + 85
    while time.monotonic() < deadline:
        if socket.bytesAvailable() or socket.waitForReadyRead(500):
            data.extend(bytes(socket.readAll()))
            if b'\n' in data:
                return result(data)
        if socket.state() == QLocalSocket.UnconnectedState:
            break
    raise TimeoutError('Akousousin controller did not respond')


def log_path():
    base = settings.data_path() if os.name == 'nt' else Path(
        os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'Akousousin'
    base.mkdir(parents=True, exist_ok=True)
    return base / 'akousousin.log'
