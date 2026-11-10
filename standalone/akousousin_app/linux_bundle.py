# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Per-user application files; speech setup delegates to AKS's public CLI."""
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import tempfile

from .desktop_identity import APP_ID, MARKER, desktop_exec

RECEIPT = '.akousousin-install.json'


def speech_setup(target, settings_path, remove=False):
    from .speech_dispatcher import run_setup
    return run_setup(Path(target) / 'akousousin', settings_path, remove=remove)


def locations(prefix, data_home):
    return (prefix / 'bin/akousousin', data_home / 'applications' / (APP_ID + '.desktop'),
            data_home / 'icons/hicolor/128x128/apps/akousousin.png',
            data_home / 'applications' / (APP_ID + '.ReadSelection.desktop'))


@contextmanager
def install_lock(prefix):
    import fcntl
    directory = prefix / 'lib'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.akousousin-install.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Another bundle installation is running') from error
        yield


def atomic_write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.akousousin-')
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(data)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def install(source, prefix=None, data_home=None):
    source = Path(source).resolve()
    prefix = Path(prefix or Path.home() / '.local').expanduser().resolve()
    data_home = Path(data_home or os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')).expanduser().resolve()
    target = prefix / 'lib/akousousin'
    if source == target or target in source.parents or source in target.parents:
        raise ValueError('Install from a separately extracted bundle, outside the installation directory')
    build = json.loads((source / 'resources/build.json').read_text(encoding='utf-8'))
    if build.get('distribution') != 'linux-tar' or not os.access(source / 'akousousin', os.X_OK):
        raise ValueError('Not an executable standalone Linux tar bundle')
    with install_lock(prefix):
        backup = target.with_name('akousousin.previous')
        if backup.exists():
            raise RuntimeError('Previous installation requires recovery: ' + str(backup))
        if target.is_symlink() or (target.exists() and not (target / RECEIPT).is_file()):
            raise RuntimeError('Refusing to replace an unowned installation: ' + str(target))
        old_receipt = json.loads((target / RECEIPT).read_text(encoding='utf-8')) if target.exists() else {}
        if old_receipt and old_receipt['data_home'] != str(data_home):
            raise RuntimeError('Use the original XDG_DATA_HOME when upgrading')
        launcher, desktop, icon, reading = locations(prefix, data_home)
        payloads = [('#!/bin/sh\n# ' + MARKER + '\nunset APPIMAGE APPDIR AKOUSOUSIN_RESOURCES\nexec ' + shlex.quote(str(target / 'akousousin')) + ' "$@"\n').encode(),
                    ('[Desktop Entry]\nType=Application\nName=Akousousin\n'
                     'Comment=Local neural speech and dictation\nNoDisplay=false\nTerminal=false\n'
                     'Icon=akousousin\nCategories=AudioVideo;Audio;Accessibility;\nExec=' +
                     desktop_exec([target / 'akousousin', '--configure']) + '\n' + MARKER + '\n').encode(),
                    (source / 'resources/akousousin.png').read_bytes(),
                    ('[Desktop Entry]\nType=Application\nName=Akousousin Read selection\n'
                     'Comment=Local neural speech and dictation\nNoDisplay=true\nTerminal=false\nExec=' +
                     desktop_exec([target / 'akousousin', '--configure']) + '\n' + MARKER + '\n').encode()]
        originals, ownership = [], []
        prior = {entry['path']: entry for entry in old_receipt.get('files', [])}
        for path, data in zip(locations(prefix, data_home), payloads):
            if path.is_symlink():
                raise RuntimeError('Refusing to replace a symlink: ' + str(path))
            before = path.read_bytes() if path.exists() else None
            previous = prior.get(str(path))
            if before is not None:
                managed = previous and hashlib.sha256(before).hexdigest() == previous['sha256']
                # Existing AKS AppImage desktop identity may be replaced, but
                # retain it for uninstall. Never replace custom launchers/icons.
                if not managed and not (path in (desktop, reading) and MARKER.encode() in before):
                    raise RuntimeError('Refusing to replace an unowned or modified file: ' + str(path))
            originals.append(before)
            ownership.append({'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(),
                              'previous': previous['previous'] if previous else
                              (base64.b64encode(before).decode() if before is not None else None)})
        with tempfile.TemporaryDirectory(prefix='.akousousin-stage-', dir=target.parent) as stage_name:
            stage = Path(stage_name)
            package = stage / 'package'
            shutil.copytree(source, package)
            (package / RECEIPT).write_text(json.dumps({'prefix': str(prefix), 'data_home': str(data_home),
                'files': ownership}, indent=2), encoding='utf-8')
            moved = False
            published = False
            changed = []
            try:
                if target.exists():
                    target.rename(backup)
                    moved = True
                package.rename(target)
                published = True
                for index, (path, data) in enumerate(zip(locations(prefix, data_home), payloads)):
                    atomic_write(path, data, 0o755 if index == 0 else 0o644)
                    changed.append(index)
            except BaseException:
                for index in reversed(changed):
                    path = locations(prefix, data_home)[index]
                    if originals[index] is None:
                        path.unlink(missing_ok=True)
                    else:
                        atomic_write(path, originals[index], 0o755 if index == 0 else 0o644)
                if published:
                    shutil.rmtree(target)
                if moved:
                    backup.rename(target)
                raise
            if moved:
                shutil.rmtree(backup)
    return target


def uninstall(target):
    target = Path(target).resolve()
    receipt = json.loads((target / RECEIPT).read_text(encoding='utf-8'))
    prefix, data_home = Path(receipt['prefix']), Path(receipt['data_home'])
    if target != prefix / 'lib/akousousin':
        raise ValueError('Installation receipt does not match this directory')
    with install_lock(prefix):
        allowed = set(locations(prefix, data_home))
        for entry in receipt['files']:
            path = Path(entry['path'])
            if path not in allowed:
                raise ValueError('Invalid installed file path')
            if path.is_symlink() or not path.is_file():
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                continue  # Preserve user modifications.
            if entry['previous'] is None:
                path.unlink()
            else:
                atomic_write(path, base64.b64decode(entry['previous']))
        shutil.rmtree(target)
    return 'Application files removed. Settings, models, voices and Wine registrations were preserved.'
