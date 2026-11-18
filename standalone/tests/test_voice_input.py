# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Shared recognition operations from the Qt panel."""
import threading
import unittest
from unittest.mock import Mock, patch

from akousousin_app.panel import Panel
from akousousin_app.qt_dictation import Dictation


class VoiceInputTests(unittest.TestCase):
    def panel(self):
        panel = Mock(busy=False, input_cancel=threading.Event())
        panel.run = lambda task, done: done(task())
        return panel

    def test_recording_delegates_to_shared_controller_and_keeps_test_local(self):
        panel = self.panel()
        with patch('akousousin_app.runtime.call', side_effect=[{'sequence': 7, 'busy': False}, {}]) as call:
            Panel.start_test(panel)
        self.assertEqual(call.call_args.args[1], {'command': 'stt-start', 'seconds': 10})
        self.assertEqual(panel.dictation.test_since, 7)

    def test_cancel_during_status_check_prevents_late_recording(self):
        panel = self.panel()
        def status(*args):
            panel.input_cancel.set()
            return {'sequence': 5, 'busy': False}
        with patch('akousousin_app.runtime.call', side_effect=status) as call:
            Panel.start_test(panel)
        call.assert_called_once()

    def test_ready_sound_during_recording_leaves_input_alone(self):
        page = Mock(recording=True)
        Dictation.sound(page)
        page.panel.run.assert_not_called()

    def test_test_transcript_excludes_other_desktop_and_earlier_results(self):
        page = Mock(sequence=5, test_since=5, supported=True)
        result = {'sequence': 8, 'state':'Ready', 'results': [
            {'sequence': 5, 'text':'earlier', 'output':'displayed'},
            {'sequence': 6, 'text':'desktop', 'output':'retained'},
            {'sequence': 8, 'text':'test', 'output':'displayed'}]}
        Dictation.update(page, result)
        page.panel.test_result.setPlainText.assert_called_once_with('test')
        page.history.setPlainText.assert_called_once_with('earlier\n\ndesktop\n\ntest')
