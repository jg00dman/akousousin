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


def check(current=__version__, windows=None):
    """Return the newest compatible published version, including betas."""
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


def download(update, directory):
    """Stage on the target filesystem; incomplete/bad downloads never replace it."""
    descriptor, filename = tempfile.mkstemp(prefix='.akousousin-update-', dir=directory)
    target = Path(filename)
    try:
        os.close(descriptor)
        with Transfer('Application update') as transfer:
            request = urllib.request.Request(update['url'], headers={'User-Agent': 'Akousousin-update'})
            if not 0 < update['size'] <= MAX_IMAGE:
                raise ValueError('Invalid update size')
            transfer.phase('Downloading', total=update['size'])
            transfer.fetch(request, target, size=update['size'], sha256=update['sha256'])
            transfer.phase('Verifying update')
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
    if os.name == 'nt' or not image or not Path(image).is_file():
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
    stage = download(update, target.parent)
    backup = target.with_name(target.name + '.previous')
    replaced = stopped = False
    env = environment()
    try:
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
        subprocess.Popen([str(target), '--settings', str(path), '--configure'], env=env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return backup
    except Exception as error:
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
