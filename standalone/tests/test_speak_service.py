# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The voice service end to end, with a real voice: /speak's stream, its events, interruption and read-ahead."""
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from akousousin_app import backend, settings, speech_stream, transport
from akousousin_app.waiting import Interrupt

VOICE = os.environ.get('AKOUSOUSIN_TEST_VOICE', '')
LONG = ' '.join(f'This is sentence number {i}, which is long enough to take a moment to say.' for i in range(1, 16))


@unittest.skipUnless(VOICE and Path(VOICE).is_file(), 'set AKOUSOUSIN_TEST_VOICE to a Piper .onnx voice')
class SpeakServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        root = Path(cls.folder.name)
        environment = {f'XDG_{name.upper()}_HOME': str(root / name) for name in ('data', 'config', 'state')}
        environment['XDG_RUNTIME_DIR'] = str(root / 'run')
        cls.environment = patch.dict(os.environ, environment)
        cls.environment.start()
        (root / 'run').mkdir(mode=0o700)
        voice = settings.data_path() / 'voices' / 'test'
        voice.mkdir(parents=True)
        model = voice / Path(VOICE).name
        shutil.copy(VOICE, model)
        shutil.copy(VOICE + '.json', str(model) + '.json')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            cls.port = probe.getsockname()[1]
        cls.path = settings.config_path()
        settings.save(cls.path, dict(settings.DEFAULTS, port=cls.port, voice='test', noise_scale=0, noise_w_scale=0,
                                     voices={'test': {'path': str(model), 'language': 'en_US', 'sample_rate': 22050}}))
        cls.server = threading.Thread(target=backend.serve, args=(cls.path, 'test', None), daemon=True)
        cls.server.start()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                health = json.loads(transport_health(cls.port))
                if health.get('model_loaded'):
                    break
            except OSError:
                pass
            time.sleep(.1)

    @classmethod
    def tearDownClass(cls):
        try:
            import urllib.request
            urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{cls.port}/shutdown', method='POST'), timeout=2)
        except OSError:
            pass
        cls.environment.stop()
        cls.folder.cleanup()

    def speak(self, request, identifier, cancelled=None):
        frames, speech = [], transport.speak(self.port, request, cancelled or Interrupt(), identifier)
        while True:
            try:
                frames.append(next(speech))
            except StopIteration as finished:
                return frames, finished.value

    def test_ssml_is_spoken_with_its_words_sentences_and_marks_in_place(self):
        ssml = '<speak>Read <mark name="m1"/>this &amp; that, then <mark name="m2"/>stop.<break time="300ms"/>Done.</speak>'
        frames, end = self.speak({'input': ssml, 'format': 'ssml', 'events': ['word', 'sentence', 'mark']}, 'ssml')
        self.assertEqual(end, {'status': 'complete'})
        self.assertEqual(frames[0][0], 'info')
        self.assertIn('word', frames[0][1]['events'])
        events, position, previous = [], 0, -1
        for frame in frames[1:]:
            if frame[0] == 'audio':
                position += len(frame[1])
                continue
            _, kind, start, finish, name = frame
            self.assertGreaterEqual(position, previous)
            previous = position
            events.append((kind, ssml[start:finish] if kind != speech_stream.MARK else name))
        self.assertEqual([text for kind, text in events if kind == speech_stream.WORD],
                         ['Read', 'this', '&amp;', 'that', 'then', 'stop', 'Done'])
        self.assertEqual([text for kind, text in events if kind == speech_stream.MARK], ['m1', 'm2'])
        order = [text for _, text in events]
        self.assertLess(order.index('m1'), order.index('this'))
        self.assertLess(order.index('then'), order.index('m2'))
        self.assertLess(order.index('m2'), order.index('stop'))
        self.assertEqual(sum(1 for kind, _ in events if kind == speech_stream.SENTENCE), 2)

    def test_a_newer_request_interrupts_without_reloading_the_voice(self):
        process = None
        results = {}
        def older():
            results['older'] = self.speak({'input': LONG, 'format': 'text'}, 'older')[1]
        task = threading.Thread(target=older)
        task.start()
        time.sleep(1)
        frames, end = self.speak({'input': 'Interrupting.', 'format': 'text'}, 'newer')
        task.join(15)
        self.assertEqual(results['older'], {'status': 'interrupted'})
        self.assertEqual(end, {'status': 'complete'})
        self.assertTrue(any(frame[0] == 'audio' for frame in frames))

    def test_first_audio_arrives_long_before_the_whole_text_is_spoken(self):
        started = time.monotonic()
        first = None
        for frame in transport.speak(self.port, {'input': LONG, 'format': 'text'}, Interrupt(), 'first'):
            if frame[0] == 'audio' and first is None:
                first = time.monotonic() - started
        whole = time.monotonic() - started
        self.assertLess(first, whole / 4)

    def test_synthesis_stays_just_ahead_of_a_reader_playing_in_real_time(self):
        started, played, ahead = time.monotonic(), 0.0, 0.0
        for frame in transport.speak(self.port, {'input': LONG, 'format': 'text'}, Interrupt(), 'slow'):
            if frame[0] == 'audio':
                played += len(frame[1]) / 2 / 22050
                lead = played - (time.monotonic() - started)
                ahead = max(ahead, lead)
                if lead > 0:
                    time.sleep(lead)
        self.assertLess(ahead, 10)
        self.assertGreater(played, 30)

    def test_the_whole_wav_interface_still_works(self):
        audio = transport.fetch(self.port, json.dumps({'text': 'Hello there.'}).encode(), Interrupt(), 'wav')
        self.assertTrue(audio.startswith(b'RIFF'))
        self.assertGreater(len(audio), 22050)

    def test_invalid_ssml_ends_the_stream_as_failed(self):
        frames, end = self.speak({'input': '<speak>broken', 'format': 'ssml'}, 'bad')
        self.assertEqual(end['status'], 'failed')


def transport_health(port):
    import urllib.request
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=1) as response:
        return response.read()


if __name__ == '__main__':
    unittest.main()
