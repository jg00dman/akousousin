# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The panel's dictation test: shared controller recording, local transcript."""
import os
import unittest

if os.name != 'nt' and not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QObject, Signal

from akousousin_app.qt_locale import application
from akousousin_app.ui.actions import DictationTest
from akousousin_app.ui.state import Status


class SyncTasks:
    closing = False

    def __init__(self):
        self.failures = []

    def run(self, work, done=None, *, failed=None, key=None, background=False):
        try:
            value = work()
        except Exception as error:
            (failed or self.failures.append)(error)
            return True
        if done:
            done(value)
        return True


class FakeState(QObject):
    status_changed = Signal(object)
    notice = Signal(str)

    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)
        self.calls = []
        self.notices = []
        self.notice.connect(self.notices.append)

    def call(self, command, launch=True, **extra):
        self.calls.append(dict(command=command, **extra))
        return self.responses.pop(0) if self.responses else {}

    def command(self, command, **extra):
        self.calls.append({'command': command})


class DictationTestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def make(self, *responses):
        self.state, self.tasks = FakeState(responses), SyncTasks()
        test = DictationTest(self.state, self.tasks)
        test.supported = True
        return test

    def test_recording_uses_the_shared_controller_and_remembers_where_it_started(self):
        test = self.make({'sequence': 7, 'busy': False}, {})
        test.toggle()
        self.assertEqual(self.state.calls[1], {'command': 'stt-start', 'seconds': 10})
        self.assertEqual(test.since, 7)
        self.assertTrue(test.recording)

    def test_busy_controller_prevents_a_second_recording(self):
        test = self.make({'sequence': 5, 'busy': True})
        test.toggle()
        self.assertEqual([call['command'] for call in self.state.calls], ['stt-status'])
        self.assertTrue(self.tasks.failures)
        self.assertFalse(test.recording)

    def test_finish_while_recording_sends_finish(self):
        test = self.make({'sequence': 1, 'busy': False}, {})
        test.toggle()
        test.toggle()
        self.assertEqual(self.state.calls[-1], {'command': 'stt-finish'})

    def test_transcript_shows_only_this_tests_displayed_results(self):
        test = self.make({'sequence': 5, 'busy': False}, {})
        shown = []
        test.transcript.connect(shown.append)
        test.toggle()
        self.state.status_changed.emit(Status(dictation={'busy': True, 'phase': 'listening', 'results': [
            {'sequence': 5, 'text': 'earlier', 'output': 'displayed'},
            {'sequence': 6, 'text': 'desktop', 'output': 'retained'},
            {'sequence': 8, 'text': 'test', 'output': 'displayed'}]}))
        self.assertEqual(shown[-1], 'test')
        self.state.status_changed.emit(Status(dictation={'busy': False, 'phase': 'ready', 'results': []}))
        self.assertFalse(test.recording)

    def test_unsupported_build_explains_instead_of_recording(self):
        test = self.make()
        test.supported = False
        test.toggle()
        self.assertEqual(self.state.calls, [])
        self.assertTrue(self.state.notices)


class TasksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def test_results_return_on_the_gui_thread_and_stop_after_shutdown(self):
        import threading
        from akousousin_app.ui.tasks import Tasks
        tasks = Tasks()
        seen = []
        release = threading.Event()
        tasks.run(lambda: 1, lambda _: seen.append(threading.get_ident()), key='one')
        self.assertTrue(tasks.busy('one'))
        self.assertFalse(tasks.run(lambda: None, key='one'), 'a running key must not start twice')
        for _ in range(200):
            self.app.processEvents()
            if seen:
                break
            threading.Event().wait(.01)
        self.assertEqual(seen, [threading.get_ident()])
        self.assertFalse(tasks.busy())
        tasks.run(lambda: release.wait(1), lambda _: seen.append('late'), key='late')
        tasks.shutdown(timeout=.05)
        release.set()
        threading.Event().wait(.05)
        self.app.processEvents()
        self.assertEqual(len(seen), 1, 'nothing is delivered after shutdown')
        self.assertFalse(tasks.run(lambda: None))


if __name__ == '__main__':
    unittest.main()
