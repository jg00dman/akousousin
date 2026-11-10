# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import io
from pathlib import Path
import tempfile
import threading
import unittest
import wave
from unittest.mock import patch

from akousousin_app import speech_gate
from akousousin_app.speech_dispatcher import Module
from test_backend import audio


class GateTests(unittest.TestCase):
    def test_stop_invalidates_existing_playback_without_muting_new_speech(self):
        before = speech_gate.snapshot(self.path)
        speech_gate.stop_speaking(self.path)
        self.assertTrue(speech_gate.suppressed(self.path, before))
        self.assertFalse(speech_gate.snapshot(self.path)[0])
        fresh = speech_gate.snapshot(self.path)
        self.assertFalse(speech_gate.suppressed(self.path, fresh))

    def test_stop_during_dictation_preserves_the_microphone_mute_lease(self):
        self.lease.acquire()
        before = speech_gate.snapshot(self.path)
        speech_gate.stop_speaking(self.path)
        self.assertEqual(speech_gate.snapshot(self.path), before)
        self.lease.close()
        self.assertFalse(speech_gate.snapshot(self.path)[0])
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'settings.json'
        from akousousin_app import settings
        settings.save(self.path, dict(settings.DEFAULTS, voice='english', voices={
            'english': {'language':'en_US', 'sample_rate':22050}}))
        self.lease = speech_gate.Lease(self.path)
        self.addCleanup(self.lease.close)

    def test_profile_isolation_release_and_crossing_epoch(self):
        before = speech_gate.snapshot(self.path)
        self.lease.acquire()
        self.assertTrue(speech_gate.snapshot(self.path)[0])
        self.assertFalse(speech_gate.snapshot(self.path.with_name('other.json'))[0])
        during = speech_gate.snapshot(self.path)
        self.lease.close()
        self.assertFalse(speech_gate.snapshot(self.path)[0])
        self.assertTrue(speech_gate.suppressed(self.path, before))
        self.assertTrue(speech_gate.suppressed(self.path, during))
        self.assertFalse(speech_gate.suppressed(self.path, speech_gate.snapshot(self.path)))

    def test_dead_owner_cannot_leave_mute_active(self):
        self.lease.acquire()
        with patch('akousousin_app.speech_gate.psutil.Process') as process:
            process.return_value.create_time.return_value = -1
            self.assertFalse(speech_gate.snapshot(self.path)[0])

    @patch('akousousin_app.speech_dispatcher.runtime.call')
    @patch('akousousin_app.speech_dispatcher.fetch')
    def test_muted_dispatcher_acknowledges_without_audio_or_inference(self, fetch, wake):
        self.lease.acquire()
        module = Module(self.path, output=io.BytesIO()); module.audio_server = True
        module.speak('Muted character')
        module.task.join(2)
        fetch.assert_not_called()
        self.assertIn(b'702 END', module.output.getvalue())
        self.assertNotIn(b'705-AUDIO', module.output.getvalue())

    @patch('akousousin_app.speech_dispatcher.runtime.call')
    @patch('akousousin_app.speech_dispatcher.fetch')
    def test_crossing_request_cannot_resume_after_unmute(self, fetch, wake):
        entered, release = threading.Event(), threading.Event()
        def blocked(*args):
            entered.set(); release.wait(2)
            return audio(22050)
        fetch.side_effect = blocked
        module = Module(self.path, output=io.BytesIO()); module.audio_server = True
        module.speak('Old speech')
        self.assertTrue(entered.wait(1))
        self.lease.acquire(); self.lease.close(); release.set()
        module.task.join(2)
        self.assertNotIn(b'705-AUDIO', module.output.getvalue())
        self.assertIn(b'703 STOP', module.output.getvalue())

    @patch('akousousin_app.speech_dispatcher.runtime.call')
    @patch('akousousin_app.speech_dispatcher.fetch')
    def test_delayed_watcher_does_not_cancel_new_unmuted_request(self, fetch, wake):
        fetch.return_value = audio(22050)
        module = Module(self.path, output=io.BytesIO()); module.audio_server = True
        stopped = threading.Event()
        watcher = threading.Thread(target=module.watch_gate, args=(stopped,))
        watcher.start()
        try:
            self.lease.acquire(); self.lease.close()
            module.speak('New speech after unmuting')
            module.task.join(2)
            stopped.wait(.08)
            self.assertIn(b'705-AUDIO', module.output.getvalue())
            self.assertNotIn(b'703 STOP', module.output.getvalue())
        finally:
            stopped.set(); watcher.join(1)
