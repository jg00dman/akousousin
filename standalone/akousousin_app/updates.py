# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""User-requested release checks and verified Linux AppImage replacement."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import threading
import urllib.request

from packaging.version import InvalidVersion, Version

from . import __version__, resources, runtime, settings
from akousousin_backend.downloads import Transfer

REPOSITORY = 'jg00dman/akousousin'
API = f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=100'
RELEASES = f'https://github.com/{REPOSITORY}/releases'
MAX_IMAGE = 1024 * 1024 * 1024


def release_version(tag):
    # Legacy run-number-only tags are not version numbers.
    value = tag.removeprefix('standalone-beta-').removeprefix('v').split('-')[0]
    if '.' not in value:
        return None
    try:
        return Version(value)
    except InvalidVersion:
        return None


def check(current=__version__, windows=None, include_beta=None):
    """Return a strictly newer compatible release from the chosen channel."""
    include_beta = Version(current).is_prerelease if include_beta is None else include_beta
    windows = os.name == 'nt' if windows is None else windows
    filename = 'Akousousin-Windows-x86_64.zip' if windows else 'Akousousin-x86_64.AppImage'
    request = urllib.request.Request(API, headers={'Accept': 'application/vnd.github+json',
                                                 'User-Agent': 'Akousousin-update-check'})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = response.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError('Release response is too large')
    releases = json.loads(data)
    if not isinstance(releases, list):
        raise ValueError('Unexpected response from GitHub releases')
    candidates = []
    for release in releases:
        version = release_version(release.get('tag_name', ''))
        if release.get('draft') or version is None or version <= Version(current):
            continue
        if not include_beta and (release.get('prerelease') or version.is_prerelease or version.is_devrelease):
            continue
        for asset in release.get('assets', []):
            if asset.get('name') != filename:
                continue
            digest = asset.get('digest', '') or ''
            url = asset.get('browser_download_url', '')
            size = asset.get('size', 0)
            if (not re.fullmatch(r'sha256:[0-9a-f]{64}', digest)
                    or not url.startswith(RELEASES + '/download/')
                    or not isinstance(size, int) or not 0 < size <= MAX_IMAGE):
                continue
            candidates.append({'version': str(version), 'url': url, 'sha256': digest[7:],
                               'size': size, 'page': RELEASES + '/tag/' + release['tag_name']})
    return max(candidates, key=lambda item: Version(item['version']), default=None)


def download(update, directory, transfer=None):
    """Stage on the target filesystem; incomplete/bad downloads never replace it."""
    if transfer is None:
        with Transfer('Application update') as progress:
            return download(update, directory, progress)
    descriptor, filename = tempfile.mkstemp(prefix='.akousousin-update-', dir=directory)
    target = Path(filename)
    try:
        os.close(descriptor)
        request = urllib.request.Request(update['url'], headers={'User-Agent': 'Akousousin-update'})
        if not 0 < update['size'] <= MAX_IMAGE:
            raise ValueError('Invalid update size')
        transfer.phase('Downloading update', total=update['size'])
        transfer.fetch(request, target, size=update['size'], sha256=update['sha256'])
        transfer.phase('Verifying update…')
        with target.open('rb') as output:
            os.fsync(output.fileno())
        target.chmod(0o755)
        return target
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def environment():
    value = runtime.environment()
    if 'LD_LIBRARY_PATH_ORIG' in value:
        value['LD_LIBRARY_PATH'] = value['LD_LIBRARY_PATH_ORIG']
    else:
        value.pop('LD_LIBRARY_PATH', None)
    value['APPIMAGE_EXTRACT_AND_RUN'] = '1'
    return value


def install(update, path):
    """Replace the AppImage at its registered path; preserve a rollback image."""
    image = os.environ.get('APPIMAGE')
    if not is_appimage():
        raise RuntimeError('Automatic installation requires the Linux AppImage; use the release download instead')
    target = Path(image).resolve()
    import fcntl
    with target.with_name(target.name + '.update.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Another Akousousin update is already running') from error
        return _install(update, path, target)


def _install(update, path, target):
    with Transfer('Application update') as transfer:
        return _apply(update, path, target, transfer)


def _apply(update, path, target, transfer):
    stage = download(update, target.parent, transfer)
    backup = target.with_name(target.name + '.previous')
    replaced = stopped = False
    env = environment()
    try:
        transfer.phase('Applying update… Speech will stop briefly.')
        shutil.copy2(target, backup)
        runtime.call(path, {'command': 'quit', 'update_pid': os.getpid()}, launch=False)
        stopped = True
        deadline = time.monotonic() + 10
        while runtime.call(path, {'command': 'status'}, launch=False) is not None:
            if time.monotonic() >= deadline:
                raise RuntimeError('Speech has not stopped; update was not installed')
            time.sleep(.1)
        os.replace(stage, target)
        replaced = True
        subprocess.run([str(target), '--settings', str(path), '--refresh-registrations'],
                       env=env, capture_output=True, text=True, check=True, timeout=180)
        # A native client may have woken the old resident during replacement.
        # After the path swap, every subsequent cold start loads the new image.
        runtime.call(path, {'command': 'quit', 'update_pid': os.getpid()}, launch=False)
        deadline = time.monotonic() + 10
        while runtime.call(path, {'command': 'status'}, launch=False) is not None:
            if time.monotonic() >= deadline:
                raise RuntimeError('Speech has not stopped for the updated application restart')
            time.sleep(.1)
        transfer.phase('Update ready — restarting Akousousin…')
        time.sleep(3)  # Keep the warning visible while the GUI continues polling.
        save_update_state(path, installed_version=update['version'], available=None)
        subprocess.Popen([str(target), '--settings', str(path), '--configure'], env=env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return backup
    except Exception as error:
        try:
            save_update_state(path, installed_version=None)
        except OSError:
            pass  # Receipt failure must never prevent restoring the old image.
        if replaced:
            os.replace(backup, target)
            try:
                subprocess.run([str(target), '--settings', str(path), '--refresh-registrations'],
                               env=env, capture_output=True, text=True, check=True, timeout=180)
            except (OSError, subprocess.SubprocessError):
                raise RuntimeError('Previous AppImage restored, but voice registration needs reapplying in Settings') from error
        if stopped:
            try:
                runtime.call(path, {'command': 'wake'})
            except Exception:
                pass
        raise
    finally:
        stage.unlink(missing_ok=True)


def refresh_registrations(path):
    """Refresh active installations only; respect prior uninstall/removal choices."""
    from .install import Installer
    config = settings.load(path)
    for registration in config.get('registrations', []):
        prefix = registration['prefix'] or None
        if os.name != 'nt' and (not prefix or not (Path(prefix).expanduser() / 'system.reg').is_file()):
            continue
        if os.name == 'nt' and prefix:
            continue
        installer = Installer(resources.root(), prefix, registration['wine'] or None)
        if installer.manifest.is_file():
            installer.install(config, path)


WEEK = 7 * 24 * 60 * 60


def is_appimage():
    """Require both a package marker and an actual executable AppImage launch."""
    if os.name == 'nt' or os.environ.get('FLATPAK_ID'):
        return False
    try:
        build = json.loads((resources.root() / 'build.json').read_text())
        image = Path(os.environ.get('APPIMAGE', ''))
        return build.get('distribution') == 'appimage' and image.is_file() and os.access(image, os.X_OK)
    except (OSError, ValueError):
        return False


def update_state(path):
    try:
        value = json.loads(Path(path).with_suffix('.updates.json').read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_update_state(path, **values):
    state = update_state(path)
    state.update(values)
    file = Path(path).with_suffix('.updates.json')
    file.parent.mkdir(parents=True, exist_ok=True)
    # Unique staging names allow manual and scheduled checks to finish safely.
    descriptor, stage = tempfile.mkstemp(dir=file.parent, prefix='.update-state-')
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(state, stream)
        os.replace(stage, file)
    finally:
        Path(stage).unlink(missing_ok=True)
    return state


def perform_check(path):
    if not is_appimage():
        return None
    config = settings.load(path)
    save_update_state(path, attempted_at=time.time())
    candidate = check(include_beta=config['update_betas'])
    save_update_state(path, checked_at=time.time(), available=candidate)
    return candidate


def available_update(path):
    if not is_appimage():
        return None
    candidate = update_state(path).get('available')
    if not isinstance(candidate, dict):
        return None
    try:
        version = Version(candidate['version'])
        if version <= Version(__version__):
            return None
        if not settings.load(path)['update_betas'] and version.is_prerelease:
            return None
        return candidate
    except (KeyError, InvalidVersion):
        return None


def remind_later(path):
    save_update_state(path, remind_after=time.time() + WEEK)


def completed_update(path):
    if update_state(path).get('installed_version') != __version__:
        return None
    save_update_state(path, installed_version=None)
    return 'Updated successfully to ' + __version__


class UpdateMonitor:
    """One controller-owned background check, with persistent weekly timing."""
    def __init__(self, path):
        self.path = path
        self.busy = False
        self.notified = None
        self.notified_at = 0

    def tick(self, quiet=False):
        if not is_appimage():
            return None
        config = settings.load(self.path)
        if not config['update_weekly']:
            return None
        state = update_state(self.path)
        now = time.time()
        if (not self.busy and now - state.get('checked_at', 0) >= WEEK
                and now - state.get('attempted_at', 0) >= 3600):
            self.busy = True
            def work():
                try:
                    perform_check(self.path)
                except Exception:
                    import logging
                    logging.exception('Automatic update check failed')
                finally:
                    self.busy = False
            threading.Thread(target=work, daemon=True).start()
        candidate = available_update(self.path)
        if (candidate and not quiet and now >= state.get('remind_after', 0)
                and (candidate['version'] != self.notified or now - self.notified_at >= WEEK)):
            self.notified = candidate['version']
            self.notified_at = now
            return candidate
        return None
