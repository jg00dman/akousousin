"""Panel actions use the shared controller; closing the panel leaves it running."""
import queue
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from akousousin_app.voice_input import VoiceInput


class VoiceInputTests(unittest.TestCase):
    def page(self):
        page = VoiceInput.__new__(VoiceInput)
        page.closed = False
        page.events = queue.Queue()
        page.panel = Mock(path=Path('/test/settings.json'))
        page.save = lambda: ('small', None, None, False)
        page.run = lambda task: task()
        page.ensure_model = Mock()
        return page

    def test_recording_uses_shared_controller_after_model_install(self):
        page = self.page()
        order = []
        page.ensure_model.side_effect = lambda model: order.append('model installed')
        with patch('akousousin_app.voice_input.runtime.call') as call:
            call.side_effect = lambda *a, **k: self.assertEqual(order, ['model installed'])
            page.record()
            self.assertEqual(call.call_args.args[1], {'command': 'stt-start', 'seconds': 10})

    def test_closing_panel_does_not_stop_shared_recognition(self):
        page = self.page()
        with patch('akousousin_app.voice_input.runtime.call') as call:
            page.destroy(Mock(widget=page.panel.root))
            self.assertTrue(page.closed)
            call.assert_not_called()
