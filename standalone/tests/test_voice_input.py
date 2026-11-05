"""Test recording orchestration without requiring a desktop display."""
import queue
import unittest
from unittest.mock import Mock, patch

from akousousin_app.voice_input import VoiceInput


class VoiceInputTests(unittest.TestCase):
    def test_model_is_loaded_before_microphone_and_text_is_preserved(self):
        page = VoiceInput.__new__(VoiceInput)
        page.closed = False
        page.events = queue.Queue()
        page.save = lambda: ('small', None, None, False)
        page.run = lambda task: task()
        order = []
        page.ensure_ready = lambda model: order.append('model ready')
        result = {'text': 'Guten Morgen', 'language': 'de'}
        page.recognizer = Mock()
        page.recognizer.transcribe.return_value = result
        def capture(seconds, source, cue, on_ready):
            self.assertEqual(order, ['model ready'])
            self.assertIsNone(cue)
            order.append('microphone ready')
            on_ready()
            return b'audio'
        with patch('akousousin_backend.recognition.capture', side_effect=capture):
            page.record()
        page.recognizer.transcribe.assert_called_once_with(b'audio', None)
        events = list(page.events.queue)
        self.assertIn(('status', 'Listening — speak now (10 seconds)'), events)
        self.assertIn(('result', result), events)
        self.assertLess(events.index(('status', 'Listening — speak now (10 seconds)')),
                        events.index(('status', 'Transcribing…')))
