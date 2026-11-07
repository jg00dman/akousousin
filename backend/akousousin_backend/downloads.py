# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Verified byte transfers with process-shared, atomic progress reports."""
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
import uuid

from .tls import https_context


def directory():
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) if os.name == 'nt' else Path(
        os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
    return base / 'Akousousin/downloads'


class Transfer:
    def __init__(self, label, publish=True):
        self.path = directory() / (uuid.uuid4().hex + '.json') if publish else None
        self.value = {'label': label, 'pid': os.getpid(), 'started': time.time(),
                      'phase': 'Connecting', 'completed': 0, 'total': None, 'status': 'active'}
        self.last_report = 0

    def report(self, force=False):
        now = time.monotonic()
        if self.path is None or (not force and now - self.last_report < .1):
            return
        self.last_report = now
        self.value['updated'] = time.time()
        # Progress reporting must not break a valid download if state storage fails.
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            stage = self.path.with_suffix('.tmp')
            stage.write_text(json.dumps(self.value), encoding='utf-8')
            stage.replace(self.path)
        except OSError:
            pass

    def phase(self, text, total=None):
        self.value.update(phase=text, total=total, completed=0)
        self.report(force=True)

    def fetch(self, url, destination, size=None, sha256=None, git_sha1=None):
        digest = hashlib.sha256()
        git = hashlib.sha1(b'blob ' + str(size).encode() + b'\0') if git_sha1 else None
        received = 0
        with urllib.request.urlopen(url, timeout=30, context=https_context()) as response, Path(destination).open('wb') as output:
            header = getattr(response, 'headers', {}).get('Content-Length')
            expected = size if size is not None else int(header) if header else None
            if self.value['total'] is None and expected is not None:
                self.value['total'] = self.value['completed'] + expected
            self.report(force=True)
            while block := response.read(256 * 1024):
                received += len(block)
                if expected is not None and received > expected:
                    raise ValueError('Download exceeds its expected size')
                output.write(block)
                digest.update(block)
                if git:
                    git.update(block)
                self.value['completed'] += len(block)
                self.report()
        if expected is not None and received != expected:
            raise ValueError('Download is truncated')
        if sha256 and digest.hexdigest() != sha256:
            raise ValueError('Downloaded file checksum does not match the pinned source')
        if git and git.hexdigest() != git_sha1:
            raise ValueError('Downloaded file checksum does not match the pinned source')
        self.report(force=True)
        return digest.hexdigest()

    def __enter__(self):
        self.report(force=True)
        return self

    def __exit__(self, kind, error, traceback):
        self.value.update(status='error' if kind else 'done', phase='Download failed' if kind else 'Download complete')
        self.report(force=True)
