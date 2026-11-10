# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Opt-in AppImage relocation and persistent application-menu integration."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from . import resources, runtime, settings, updates
from .desktop_identity import APP_ID, ensure_desktop_entry
from akousousin_backend.downloads import Transfer


def recommended_path():
    return settings.data_path() / 'Akousousin-x86_64.AppImage'


def needs_move():
    return updates.is_appimage() and Path(os.environ['APPIMAGE']).resolve() != recommended_path().resolve()


def create_menu_entry(image=None):
    image = Path(image or os.environ['APPIMAGE']).absolute()
    icon = settings.data_path() / 'icons/akousousin.png'
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(resources.root() / 'akousousin.png', icon)
    entry = ensure_desktop_entry([str(image), '--configure'], visible=True, icon=icon)
    # Preserve a custom portal identity while still providing a visible launcher.
    if 'NoDisplay=true' in entry.read_text():
        entry = ensure_desktop_entry([str(image), '--configure'], app_id=APP_ID + '.Launcher',
                                     visible=True, icon=icon)
    return entry


def fingerprint(file):
    with file.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def install(path, replace=False):
    if not updates.is_appimage():
        raise RuntimeError('AppImage installation requires an AppImage launch')
    source = Path(os.environ['APPIMAGE']).absolute()
    if source.is_symlink():
        raise ValueError('Launch the AppImage file itself before moving it, rather than a symbolic link')
    target = recommended_path()
    if source.resolve() == target.resolve():
        return create_menu_entry(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    import fcntl
    with target.with_name(target.name + '.update.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Another installation or update is already running') from error
        if target.is_symlink() or (target.exists() and (not replace or not target.is_file())):
            raise RuntimeError('The destination already exists; confirm its replacement before installing')
        return _install(source, target, path)


def _install(source, target, path):
    descriptor, name = tempfile.mkstemp(prefix='.akousousin-install-', dir=target.parent)
    os.close(descriptor)
    stage = Path(name)
    backup = target.with_name(target.name + '.previous')
    had_target, replaced, stopped = target.exists(), False, False
    environment = updates.environment()
    environment['APPIMAGE'] = str(target)
    try:
        with Transfer('AppImage installation') as progress:
            progress.phase('Copying AppImage…')
            original_hash = fingerprint(source)
            shutil.copyfile(source, stage)
            stage.chmod(0o755)
            if fingerprint(stage) != original_hash:
                raise ValueError('AppImage copy verification failed; the original has been retained')
            if had_target:
                shutil.copy2(target, backup)
            progress.phase('Applying installation… Speech will stop briefly.')
            runtime.call(path, {'command': 'quit', 'update_pid': os.getpid()}, launch=False)
            stopped = True
            deadline = time.monotonic() + 10
            while runtime.call(path, {'command': 'status'}, launch=False) is not None:
                if time.monotonic() > deadline:
                    raise RuntimeError('Akousousin has not stopped; the original has been retained')
                time.sleep(.1)
            os.replace(stage, target)
            replaced = True
            subprocess.run([str(target), '--settings', str(path), '--refresh-registrations'],
                           env=environment, capture_output=True, text=True, check=True, timeout=180)
            create_menu_entry(target)
            warnings = updates.registration_warnings(path)
            if warnings:
                updates.save_update_state(path, registration_warnings=warnings + [
                    'The original AKS AppImage was retained at ' + str(source) + ' because a skipped registration may still use it.'])
            progress.phase('Installation ready — restarting Akousousin…')
            time.sleep(3)
            subprocess.Popen([str(target), '--settings', str(path), '--configure'], env=environment,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Do not delete a download which was replaced while the dialog was open.
            try:
                if not warnings and source.is_file() and fingerprint(source) == original_hash:
                    source.unlink()
            except OSError:
                pass  # A successful installation must not roll back over cleanup failure.
            return target
    except Exception:
        if replaced:
            if had_target:
                os.replace(backup, target)
            else:
                target.unlink(missing_ok=True)
            subprocess.run([str(source), '--settings', str(path), '--refresh-registrations'],
                           env=updates.environment(), capture_output=True, text=True, check=True, timeout=180)
            create_menu_entry(source)
        if stopped:
            runtime.call(path, {'command': 'wake'})
        raise
    finally:
        stage.unlink(missing_ok=True)
