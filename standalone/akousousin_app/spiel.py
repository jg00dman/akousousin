# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Per-user Spiel provider registration and default voice selection."""
from contextlib import contextmanager
import json
import logging
from pathlib import Path
import re
import shlex
import subprocess
import sys

from . import resources, runtime, settings
from .desktop_identity import APP_ID
from .linux_bundle import atomic_write

INTERFACE = 'org.freedesktop.Speech.Provider'
BUS_NAME = APP_ID + '.Speech.Provider'
OBJECT_PATH = '/' + BUS_NAME.replace('.', '/')
SCHEMA = 'org.monotonous.libspiel'
DEFAULT = 'default-voice'
UNSET = '@m(ss) nothing'
SERVICE_HEADER = f'[D-BUS Service]\nName={BUS_NAME}\n'
RECEIPT_PREFIX = '# Akousousin Spiel registration: '


def service_path():
    return settings.data_path().parent / 'dbus-1/services' / (BUS_NAME + '.service')


def registered():
    return service_path().is_file()


def available():
    """Whether Spiel is installed: its settings schema is where GSettings looks for schemas."""
    environment = runtime.host_environment()
    data = [environment.get('XDG_DATA_HOME') or str(Path.home() / '.local/share'),
            *(environment.get('XDG_DATA_DIRS') or '').split(':'), '/usr/local/share', '/usr/share']
    folders = [*(environment.get('GSETTINGS_SCHEMA_DIR') or '').split(':'),
               *(str(Path(folder) / 'glib-2.0/schemas') for folder in data if folder)]
    return any((Path(folder) / (SCHEMA + '.gschema.xml')).is_file() for folder in folders if folder)


@contextmanager
def registration_lock():
    import fcntl

    lock_path = settings.data_path() / 'spiel.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def gsettings(*args):
    unavailable = 'Install Spiel (libspiel with its GSettings schema) to use Akousousin with Spiel.'
    try:
        return subprocess.run(['gsettings', *args], env=runtime.host_environment(), check=True,
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except FileNotFoundError as error:
        raise RuntimeError(unavailable) from error
    except subprocess.CalledProcessError as error:
        details = error.stderr.strip()
        if 'No such schema' in details or 'No schemas installed' in details:
            raise RuntimeError(unavailable) from error
        raise RuntimeError(details or 'Could not change the default Spiel voice.') from error


def current_default():
    return gsettings('get', SCHEMA, DEFAULT)


def refresh_session_bus():
    # Some session buses retain an unlinked service in their activation list.
    subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus',
                    '--object-path', '/org/freedesktop/DBus', '--method', 'org.freedesktop.DBus.ReloadConfig'],
                   env=runtime.host_environment(), check=True, capture_output=True, text=True, timeout=10)


def is_our_default(default):
    pair = default.removeprefix('@m(ss) ').removeprefix('just ')
    return pair.startswith(f"('{BUS_NAME}',")


def set_default(value):
    if value == UNSET:
        gsettings('reset', SCHEMA, DEFAULT)
    else:
        gsettings('set', SCHEMA, DEFAULT, value)
    if current_default() != value:
        raise RuntimeError('Spiel did not save the default voice. Check the desktop session and its GSettings policy.')


def invocation(path):
    return runtime.command('--settings', str(Path(path).resolve()), '--spiel-provider')


def service_content(record):
    command = record['command']
    if any(any(character in arg for character in '\n\r\0') for arg in command):
        raise ValueError('Application path contains an unsupported control character')
    # D-Bus activation parses shell-style argv without starting a shell.
    return (SERVICE_HEADER + f'Exec={shlex.join(command)}\n' + RECEIPT_PREFIX + json.dumps(record) + '\n').encode()


def load_registration():
    service = service_path()
    if service.is_symlink():
        raise RuntimeError('The Spiel registration is a symbolic link.')
    try:
        data = service.read_bytes()
    except FileNotFoundError:
        return None, None
    receipt = data.decode('utf-8').splitlines()[-1:]
    if not receipt or not receipt[0].startswith(RECEIPT_PREFIX):
        raise RuntimeError('The Spiel provider is registered by another installation.')
    record = json.loads(receipt[0].removeprefix(RECEIPT_PREFIX))
    if data != service_content(record):
        raise RuntimeError('The Spiel registration has been modified.')
    return record, data


def configure(path, remove=False, *, executable=None):
    """Register Akousousin or remove its registration and restore the previous default."""
    if sys.platform != 'linux':
        raise RuntimeError('Spiel integration is available on Linux.')
    service = service_path()
    if remove and not service.exists() and not service.is_symlink():
        return
    with registration_lock():
        record, old_service = load_registration()
        if remove:
            if record is None or (executable is not None
                                  and Path(record['command'][0]).resolve() != Path(executable).resolve()):
                return
            try:
                previous = current_default()
            except RuntimeError:
                previous = None  # Spiel has been uninstalled: there is no default to restore
            if previous is not None and is_our_default(previous):
                set_default(record['previous_default'])
            try:
                service.unlink()
                refresh_session_bus()
            except (OSError, subprocess.SubprocessError):
                if not service.exists():
                    atomic_write(service, old_service)
                if previous is not None and is_our_default(previous):
                    set_default(previous)
                raise
            return

        config = settings.load(path)
        voice = config['voice']
        if not resources.voice_available(config, voice):
            raise RuntimeError('Download or import a default voice in Voices before turning on Spiel support.')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', voice):
            raise ValueError('The default voice has an invalid identifier.')
        previous = current_default()
        saved = (record['previous_default'] if record else UNSET) if is_our_default(previous) else previous
        content = service_content({'command': invocation(path), 'previous_default': saved})
        atomic_write(service, content)
        try:
            refresh_session_bus()
            set_default(f"@m(ss) ('{BUS_NAME}', '{voice}')")
        except Exception:
            if old_service is None:
                service.unlink(missing_ok=True)
            else:
                atomic_write(service, old_service)
            try:
                refresh_session_bus()
            except (OSError, subprocess.SubprocessError):
                logging.getLogger(__name__).warning('Could not refresh Spiel activation after rollback', exc_info=True)
            raise


def retarget(path, source, target):
    """Keep an enabled registration pointed at the installed AppImage after a move."""
    if not registered():
        return False
    with registration_lock():
        record, old_service = load_registration()
        if record and record['command'] == [str(source), *invocation(path)[-3:]]:
            command = [str(target), *record['command'][1:]]
            atomic_write(service_path(), service_content(dict(record, command=command)))
            try:
                refresh_session_bus()
            except (OSError, subprocess.SubprocessError):
                atomic_write(service_path(), old_service)
                raise
            return True
    return False
