# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Transient, profile-scoped dictation mute; never changes saved volume."""
import json
import os
from pathlib import Path
import uuid

import psutil
from . import runtime


def location(path):
    return runtime.directory() / (Path(runtime.name(path)).name + '.speech-gate.json')


def active_lease(path, value):
    if not value['active']:
        return False
    if os.environ.get('FLATPAK_ID'):
        import fcntl
        with location(path).with_suffix('.lock').open('rb') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
        return False
    return psutil.Process(value['pid']).create_time() == value['created']


def snapshot(path):
    try:
        value = json.loads(location(path).read_text())
        return active_lease(path, value), value['generation']
    except (OSError, ValueError, KeyError, psutil.Error):
        return False, None


def suppressed(path, before):
    current = snapshot(path)
    return before[0] or current[0] or before[1] != current[1]


class Lease:
    def __init__(self, path):
        self.path = path
        self.lock = None
        self.value = dict(active=True, generation=uuid.uuid4().hex,
                          pid=os.getpid(), created=psutil.Process().create_time())

    def write(self):
        target = location(self.path)
        temporary = target.with_name(target.name + '.' + uuid.uuid4().hex)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, 'w') as output:
                json.dump(self.value, output)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def acquire(self):
        if os.environ.get('FLATPAK_ID'):
            # A separately activated Spiel provider cannot inspect this process's PID.
            import fcntl
            self.lock = location(self.path).with_suffix('.lock').open('ab')
            try:
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.write()
            except BaseException:
                self.lock.close()
                self.lock = None
                raise
            return
        self.write()

    def close(self):
        try:
            if snapshot(self.path)[1] == self.value['generation']:
                self.value['active'] = False
                self.write()
        finally:
            if self.lock is not None:
                self.lock.close()
                self.lock = None
