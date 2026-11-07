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


def snapshot(path):
    try:
        value = json.loads(location(path).read_text())
        active = value['active'] and psutil.Process(value['pid']).create_time() == value['created']
        return bool(active), value['generation']
    except (OSError, ValueError, KeyError, psutil.Error):
        return False, None


def suppressed(path, before):
    current = snapshot(path)
    return before[0] or current[0] or before[1] != current[1]


class Lease:
    def __init__(self, path):
        self.path = path
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
        self.write()

    def close(self):
        if snapshot(self.path)[1] == self.value['generation']:
            self.value['active'] = False
            self.write()
