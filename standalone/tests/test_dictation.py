# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import queue
import tempfile
import threading
import time
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from akousousin_app import settings
from akousousin_app.dictation import Dictation
from akousousin_backend.audio_input import wav


class Recognition:
    instances = []
    def __init__(self, model):
        self.model = {'model': model}
        self.process = None
        self.status = {'model': model}
        self.closed = False
        Recognition.instances.append(self)
    def start(self, cancelled=None):
        self.process = Mock()
        self.process.is_alive.return_value = True
    def close(self):
        self.process = None
        self.closed = True
    def transcribe(self, audio, language=None, cancelled=None):
        return {'text': 'Guten Morgen', 'language': language or 'de'}


class Audio:
    instances = []
    def __init__(self, **kwargs):
        self.segments = queue.Queue()
        self.done = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.options = kwargs
        Audio.instances.append(self)
    def start(self):
        self.ready.set()
        self.options['changed']('Listening — speak now')
        self.segments.put(wav(b'\x01\0' * 3200))
        self.done.set()
    def finish(self):
        self.done.set()
    def cancel(self):
        self.done.set()
    def close(self):
        pass


class DictationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'settings.json'
        config = dict(settings.DEFAULTS, stt_beep=False)
        settings.save(self.path, config)
        self.installed = patch('akousousin_backend.models.installed', return_value=True)
        self.installed.start(); self.addCleanup(self.installed.stop)
        Recognition.instances.clear(); Audio.instances.clear()
        self.manager = Dictation(self.path, recognizer_factory=Recognition, capture_factory=Audio)
        self.addCleanup(self.manager.close)

    def wait(self):
        self.manager.thread.join(2)
        self.assertFalse(self.manager.thread.is_alive())

    def test_worker_is_shared_across_recordings(self):
        self.manager.start(); self.wait()
        self.manager.start(); self.wait()
        self.assertEqual(len(Recognition.instances), 1)
        status = self.manager.status()
        self.assertEqual(status['sequence'], 2)
        self.assertEqual(status['results'][-1]['language'], 'de')
        self.assertEqual(status['results'][-1]['output'], 'displayed')

    def test_transcript_records_audio_and_recognition_timing(self):
        self.manager.start(); self.wait()
        timings = self.manager.status()['results'][-1]['timings']
        self.assertEqual(timings['audio_seconds'], .2)
        self.assertGreaterEqual(timings['queue_seconds'], 0)
        self.assertGreaterEqual(timings['recognition_seconds'], 0)

    def test_focus_refusal_retains_text_and_stops(self):
        self.manager.insert = Mock(side_effect=RuntimeError('Active window changed'))
        self.manager.start(target=('editor', 1)); self.wait()
        status = self.manager.status()
        self.assertEqual(status['phase'], 'error')
        self.assertIn('retained', status['state'])
        self.assertEqual(status['results'][-1]['text'], 'Guten Morgen')
        self.assertEqual(status['results'][-1]['output'], 'retained')

    def test_idle_unload_and_explicit_unload_preserve_models(self):
        self.manager.prepare(); self.wait()
        self.manager.last_activity = time.monotonic() - 301
        self.manager.expire()
        self.assertIsNone(self.manager.recognizer)
        self.manager.prepare(); self.wait()
        self.manager.unload()
        self.assertEqual(self.manager.status()['phase'], 'unloaded')

    def test_tts_gate_is_passed_to_capture(self):
        self.manager.speaking = Mock(return_value=True)
        self.manager.start(); self.wait()
        self.assertTrue(Audio.instances[-1].options['paused']())

    def test_failed_first_download_does_not_start_microphone(self):
        def fail(cancelled=None):
            self.assertTrue(self.manager.recognizer.model['download_missing'])
            raise RuntimeError('Download failed')
        with patch('akousousin_backend.models.installed', return_value=False), patch.object(Recognition, 'start', side_effect=fail):
            self.manager.start(); self.wait()
        self.assertEqual(Audio.instances, [])
        self.assertEqual(self.manager.status()['phase'], 'error')
        self.assertIn('Download failed', self.manager.status()['state'])

    def test_recording_reenables_input_after_disabling_and_idle_unloads_keep_enabled(self):
        self.manager.prepare(); self.wait()
        self.manager.last_activity = time.monotonic() - 301
        self.manager.expire()
        self.assertTrue(self.manager.status()['enabled'])
        self.manager.unload()
        self.assertFalse(self.manager.status()['enabled'])
        self.manager.start(); self.wait()
        self.assertTrue(self.manager.status()['enabled'])
        self.assertTrue(self.manager.status()['loaded'])

    def test_push_to_talk_recognizes_but_does_not_insert_before_release(self):
        config = settings.load(self.path)
        config['stt_mode'] = 'push-to-talk'
        settings.save(self.path, config)
        class HeldAudio(Audio):
            def start(self):
                self.ready.set()
                self.segments.put(wav(b'\x01\0' * 3200))
                self.segments.put(wav(b'\x01\0' * 3200))
        self.manager.capture_factory = HeldAudio
        self.manager.insert = Mock()
        self.manager.start(target=('editor', 1))
        deadline = time.monotonic() + 2
        while self.manager.status()['sequence'] < 2 and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(self.manager.status()['results'][-1]['output'], 'pending')
        self.manager.insert.assert_not_called()
        self.manager.finish()
        self.wait()
        self.manager.insert.assert_called_once_with('Guten Morgen Guten Morgen', ('editor', 1), self.manager.cancelled)
        self.assertEqual(self.manager.status()['results'][-1]['output'], 'inserted')

    def test_cancelling_push_to_talk_discards_pending_insertion(self):
        config = settings.load(self.path)
        config['stt_mode'] = 'push-to-talk'
        settings.save(self.path, config)
        class HeldAudio(Audio):
            def start(self):
                self.ready.set()
                self.segments.put(wav(b'\x01\0' * 3200))
        self.manager.capture_factory = HeldAudio
        self.manager.insert = Mock()
        self.manager.start(target=('editor', 1))
        deadline = time.monotonic() + 2
        while self.manager.status()['sequence'] < 1 and time.monotonic() < deadline:
            time.sleep(.01)
        self.manager.cancel()
        self.wait()
        self.manager.insert.assert_not_called()
        self.assertEqual(self.manager.status()['results'][-1]['output'], 'cancelled')
