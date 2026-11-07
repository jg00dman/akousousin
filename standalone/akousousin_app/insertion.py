# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Bounded ordered insertion, independent of the recognition worker."""
import queue
import threading
import time


class InsertionQueue:
    def __init__(self, insert, cancelled, completed, limit=3):
        self.insert, self.cancelled, self.completed = insert, cancelled, completed
        self.queue = queue.Queue(maxsize=limit)
        self.stopping = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def submit(self, record, text, target):
        item = (record, text, target, time.monotonic())
        deadline = time.monotonic() + 30
        while True:
            if self.cancelled.is_set():
                raise InterruptedError('Dictation cancelled')
            if self.error:
                raise RuntimeError(self.error)
            try:
                self.queue.put(item, timeout=.05)
                return
            except queue.Full:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Text insertion backlog exceeded 30 seconds; transcript retained')

    def _run(self):
        while not self.stopping.is_set() or not self.queue.empty():
            try:
                record, text, target, queued = self.queue.get(timeout=.05)
            except queue.Empty:
                continue
            began = time.monotonic()
            error = self.error
            outcome = 'retained' if error else 'inserted'
            try:
                if self.cancelled.is_set():
                    outcome = 'cancelled'
                elif not error:
                    self.insert(text, target, self.cancelled)
            except Exception as failure:
                error = self.error = str(failure)
                outcome = 'retained'
            finally:
                self.completed(record, outcome, error, {
                    'insertion_queue_seconds': round(began - queued, 3),
                    'insertion_seconds': round(time.monotonic() - began, 3)})
                self.queue.task_done()

    def finish(self):
        self.stopping.set()
        self.thread.join(35)
        if self.thread.is_alive():
            self.cancelled.set()
            self.thread.join(2)
            raise TimeoutError('Text insertion worker did not stop')
