# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Private desktop-session preferences, separate from stale panel settings copies."""
import json
import os
from pathlib import Path
import threading
import uuid

_LOCK = threading.RLock()
DEFAULTS = {'dictation_enabled': False, 'reading_enabled': False, 'restore_token': ''}


class DesktopPreferences:
    def __init__(self, settings):
        settings = Path(settings)
        self.path = settings.with_name(settings.stem + '.desktop.json')

    def load(self):
        with _LOCK:
            try:
                stored = json.loads(self.path.read_text())
            except FileNotFoundError:
                stored = {}
            result = dict(DEFAULTS, **stored)
            if any(not isinstance(result[key], bool) for key in ('dictation_enabled', 'reading_enabled')):
                raise ValueError('Invalid saved shortcut preference')
            if not isinstance(result['restore_token'], str) or len(result['restore_token']) > 4096:
                raise ValueError('Invalid saved desktop permission')
            return result

    def update(self, condition=lambda: True, **values):
        with _LOCK:
            if not condition():
                return
            result = self.load()
            result.update(values)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, 'w') as output:
                    json.dump(result, output)
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
