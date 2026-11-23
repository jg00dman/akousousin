# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Shared download status for the control panel and desktop tray."""
import json
import time

import psutil

from akousousin_backend.downloads import directory


def discard(file):
    try:
        file.unlink(missing_ok=True)
    except OSError:
        pass


def current():
    result = []
    for file in directory().glob('*.json'):
        try:
            if file.stat().st_size > 16384:
                continue
            value = json.loads(file.read_text(encoding='utf-8'))
            if value['status'] == 'active':
                process = psutil.Process(value['pid'])
                valid = (process.is_running() and process.status() != psutil.STATUS_ZOMBIE
                         and process.create_time() <= value['started'])
            else:
                valid = time.time() - value['updated'] < (15 if value['status'] == 'error' else 3)
            if not valid:
                discard(file)
                continue
            value['id'] = file.stem
            result.append(value)
        except (OSError, ValueError, KeyError, TypeError, psutil.Error):
            # A killed recognition/download process must not leave a stuck indicator.
            discard(file)
    return sorted(result, key=lambda value: value['started'])


def caption(value):
    text = value['label'] + ' · ' + value['phase']
    done, total = value['completed'], value['total']
    if value['status'] == 'active' and total:
        text += f' · {min(100, done * 100 // total)}% ({done / 1e6:.1f} / {total / 1e6:.1f} MB)'
    elif value['status'] == 'active' and done:
        text += f' · {done / 1e6:.1f} MB received'
    return text
