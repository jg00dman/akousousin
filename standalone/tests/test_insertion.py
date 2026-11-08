# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import threading
import unittest
from akousousin_app.insertion import InsertionQueue


class InsertionTests(unittest.TestCase):
    def test_delivery_latency_uses_capture_origin_and_acknowledgements(self):
        results = []
        worker = InsertionQueue(lambda *args: {'first_key_at': 11.2, 'last_key_at': 12.4},
                                threading.Event(), lambda *args: results.append(args))
        worker.submit({}, 'hello', 'window', speech_ended_at=10.0)
        worker.finish()
        self.assertEqual(results[0][1], 'inserted')
        self.assertEqual(results[0][3]['speech_end_to_first_key_seconds'], 1.2)
        self.assertEqual(results[0][3]['speech_end_to_last_key_seconds'], 2.4)

    def test_slow_typing_does_not_block_next_recognition_submission(self):
        entered, release, cancelled = threading.Event(), threading.Event(), threading.Event()
        typed, results = [], []
        def insert(text, target, cancel):
            entered.set(); release.wait(2); typed.append(text)
        worker = InsertionQueue(insert, cancelled, lambda *args: results.append(args), limit=2)
        try:
            worker.submit({}, 'one', 'window')
            self.assertTrue(entered.wait(1))
            worker.submit({}, 'two', 'window')
            worker.submit({}, 'three', 'window')
            self.assertEqual(worker.queue.qsize(), 2)
            self.assertEqual(typed, [])
        finally:
            release.set(); worker.finish()
        self.assertEqual(typed, ['one', 'two', 'three'])
        self.assertEqual([r[1] for r in results], ['inserted'] * 3)

    def test_focus_failure_retains_pending_phrases_without_typing_them(self):
        calls, results = [], []
        def insert(*args):
            calls.append(args)
            raise RuntimeError('Active window changed')
        worker = InsertionQueue(insert, threading.Event(), lambda *args: results.append(args))
        # Enqueue together so both are accepted before the first error.
        worker.queue.put(({}, 'one', 'window', 0, None))
        worker.queue.put(({}, 'two', 'window', 0, None))
        worker.finish()
        self.assertEqual(len(calls), 1)
        self.assertEqual([r[1] for r in results], ['retained', 'retained'])
        self.assertIn('changed', worker.error)

    def test_cancelled_queue_never_types(self):
        cancelled = threading.Event(); cancelled.set()
        calls, results = [], []
        worker = InsertionQueue(lambda *args: calls.append(args), cancelled, lambda *args: results.append(args))
        worker.queue.put(({}, 'one', 'window', 0, None))
        worker.finish()
        self.assertEqual(calls, [])
        self.assertEqual(results[0][1], 'retained')
