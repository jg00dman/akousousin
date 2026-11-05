"""Panel actions use the shared controller; closing the panel leaves it running."""
import queue
import threading
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from akousousin_app.voice_input import VoiceInput


class VoiceInputTests(unittest.TestCase):
    def page(self):
        page = VoiceInput.__new__(VoiceInput)
        page.closed = False
        page.events = queue.Queue()
        page.operation_lock = threading.Lock()
        page.action_cancelled = threading.Event()
        page.panel = Mock(path=Path('/test/settings.json'))
        page.save = lambda: ('small', None, None, False)
        page.run = lambda task: task()
        page.ensure_model = Mock()
        return page

    def test_recording_delegates_model_lifecycle_to_shared_controller(self):
        page = self.page()
        with patch('akousousin_app.voice_input.runtime.call') as call:
            page.record()
            self.assertEqual(call.call_args.args[1], {'command': 'stt-start', 'seconds': 10})
        page.ensure_model.assert_not_called()

    def test_closing_panel_does_not_stop_shared_recognition(self):
        page = self.page()
        with patch('akousousin_app.voice_input.runtime.call') as call:
            page.destroy(Mock(widget=page.panel.root))
            self.assertTrue(page.closed)
            call.assert_not_called()

    def test_shared_poll_does_not_hide_model_download_progress(self):
        page = self.page()
        page.busy = True
        page.local_error = False
        page.state = Mock()
        page.desktop_state = Mock()
        page.last_sequence = 0
        page.shared({'busy': False, 'state': 'Not loaded', 'desktop': {'state': 'Disabled'}, 'sequence': 0})
        page.state.set.assert_not_called()

    def test_cancel_during_model_import_prevents_late_recording(self):
        page = self.page()
        page.action_cancelled.set()
        with patch('akousousin_app.voice_input.runtime.call') as call:
            page.record()
            call.assert_not_called()

    def test_unplugged_microphone_preference_is_preserved(self):
        page = self.page()
        page.source = Mock(); page.source.get.return_value = 'missing-source'
        page.source_caption = Mock(); page.source_caption.get.return_value = 'USB microphone'
        page.source_combo = Mock(); page.device_status = Mock()
        page.apply_sources([('', 'System default'), ('built-in', 'Built-in microphone')])
        page.source.set.assert_not_called()
        self.assertEqual(page.source_options['Unavailable — USB microphone'], 'missing-source')
        page.source_caption.set.assert_called_with('Unavailable — USB microphone')


    def test_ready_sound_test_needs_no_model_and_reports_failure(self):
        page = self.page()
        page.shared_busy = page.sound_testing = False
        page.sound_button = Mock(); page.sound_status = Mock()
        with patch('akousousin_backend.recognition.ready_cue', side_effect=RuntimeError('Playback failed')) as cue:
            page.test_ready_sound()
            kind, message = page.events.get(timeout=2)
        self.assertEqual((kind, message), ('sound', 'Playback failed'))
        cue.assert_called_once_with()
        page.ensure_model.assert_not_called()


    def test_single_toggle_prepares_or_disables_input(self):
        page = self.page()
        page.busy = False
        page.prepare = Mock(); page.unload = Mock()
        page.input_enabled = False; page.toggle_input()
        page.prepare.assert_called_once()
        page.input_enabled = True; page.toggle_input()
        page.unload.assert_called_once()
