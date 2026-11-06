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
                valid = process.is_running() and process.create_time() <= value['started']
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


class DownloadView:
    def __init__(self, parent):
        from tkinter import ttk
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill='x', padx=22)
        self.rows = {}
        self.frame.after(100, self.poll)

    def poll(self):
        from tkinter import ttk
        values = current()
        ids = {value['id'] for value in values}
        for identifier in set(self.rows) - ids:
            frame, label, bar = self.rows.pop(identifier)
            bar.stop()
            frame.destroy()
        for value in values:
            identifier = value['id']
            if identifier not in self.rows:
                frame = ttk.Frame(self.frame); frame.pack(fill='x', pady=3)
                label = ttk.Label(frame, wraplength=760); label.pack(anchor='w')
                bar = ttk.Progressbar(frame, maximum=100); bar.pack(fill='x')
                self.rows[identifier] = frame, label, bar
            frame, label, bar = self.rows[identifier]
            label.configure(text=caption(value), foreground='#bd3838' if value['status'] == 'error' else '#193c43')
            known = bool(value['total']) or value['status'] != 'active'
            mode = 'determinate' if known else 'indeterminate'
            if str(bar.cget('mode')) != mode:
                bar.stop(); bar.configure(mode=mode)
                if not known:
                    bar.start(15)
            bar.configure(value=100 if value['status'] == 'done' else min(100, value['completed'] * 100 / value['total']) if value['total'] else 0)
        self.frame.after(150, self.poll)
