# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest

from akousousin_app import voice_process, voice_timing
from akousousin_app.waiting import Interrupt


def chatty(pipe, model, stop):
    """A stand-in voice: ten chunks, 0.1 s each, honouring stop between chunks."""
    pipe.send(('ready', 16000, True))
    while True:
        request = pipe.recv()
        for index in range(10):
            if stop.is_set():
                pipe.send(('stopped',))
                break
            time.sleep(.1)
            pipe.send(('chunk', bytes([index]) * 4, {'sentence': index == 0, 'words': [], 'covers': None}))
        else:
            pipe.send(('done',))


def stuck(pipe, model, stop):
    pipe.send(('ready', 16000, False))
    pipe.recv()
    pipe.send(('chunk', b'\0\0', {'sentence': True, 'words': [], 'covers': None}))
    time.sleep(60)  # ignores stop: a hung voice


class ProcessTests(unittest.TestCase):
    def test_a_run_is_streamed_chunk_by_chunk(self):
        voice = voice_process.VoiceProcess('model', target=chatty)
        self.addCleanup(voice.close)
        chunks = list(voice.speak({'text': 'x', 'length_scale': 1}, Interrupt()))
        self.assertEqual([pcm[0] for pcm, _ in chunks], list(range(10)))

    def test_stopping_keeps_the_voice_loaded(self):
        voice = voice_process.VoiceProcess('model', target=chatty)
        self.addCleanup(voice.close)
        cancelled = Interrupt()
        received = []
        with self.assertRaises(InterruptedError):
            for pcm, _ in voice.speak({'text': 'x', 'length_scale': 1}, cancelled):
                received.append(pcm)
                if len(received) == 2:
                    cancelled.set()
        process = voice.process
        self.assertLess(len(received), 10)
        self.assertTrue(voice.alive())
        list(voice.speak({'text': 'again', 'length_scale': 1}, Interrupt()))  # same process, not reloaded
        self.assertIs(voice.process, process)

    def test_a_reader_that_stops_reading_also_stops_the_run(self):
        voice = voice_process.VoiceProcess('model', target=chatty)
        self.addCleanup(voice.close)
        speech = voice.speak({'text': 'x', 'length_scale': 1}, Interrupt())
        next(speech)
        speech.close()
        self.assertTrue(voice.alive())
        self.assertEqual(len(list(voice.speak({'text': 'y', 'length_scale': 1}, Interrupt()))), 10)

    def test_cancelling_wakes_a_waiting_request_at_once(self):
        voice = voice_process.VoiceProcess('model', target=chatty)
        self.addCleanup(voice.close)
        cancelled = Interrupt()
        speech = voice.speak({'text': 'x', 'length_scale': 1}, cancelled)
        next(speech)
        threading.Timer(.02, cancelled.set).start()
        started = time.monotonic()
        with self.assertRaises(InterruptedError):
            next(speech)
        self.assertLess(time.monotonic() - started, .5)

    def test_a_hung_voice_is_killed(self):
        voice = voice_process.VoiceProcess('model', target=stuck)
        self.addCleanup(voice.close)
        cancelled = Interrupt()
        original = voice_process.STOP_GRACE
        voice_process.STOP_GRACE = .3
        self.addCleanup(setattr, voice_process, 'STOP_GRACE', original)
        speech = voice.speak({'text': 'x', 'length_scale': 1}, cancelled)
        next(speech)
        cancelled.set()
        with self.assertRaises(InterruptedError):
            next(speech)
        self.assertFalse(voice.alive())


VOICE = os.environ.get('AKOUSOUSIN_TEST_VOICE', '')


@unittest.skipUnless(VOICE and Path(VOICE).is_file(), 'set AKOUSOUSIN_TEST_VOICE to a Piper .onnx voice')
class RealVoiceTests(unittest.TestCase):
    """The streamed audio is Piper's own, and word timing adds up."""
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.model = Path(cls.folder.name) / Path(VOICE).name
        shutil.copy(VOICE, cls.model)
        shutil.copy(VOICE + '.json', str(cls.model) + '.json')
        assert voice_timing.ensure_timed(cls.model, cls.folder.name)
        cls.voice = voice_process.VoiceProcess(cls.model)
        cls.voice.start()

    @classmethod
    def tearDownClass(cls):
        cls.voice.close()
        cls.folder.cleanup()

    def speak(self, text, events=True):
        return list(self.voice.speak({'text': text, 'length_scale': 1, 'events': events, 'noise_scale': 0,
                                      'noise_w_scale': 0}, Interrupt()))

    def test_plain_text_sounds_exactly_as_piper_makes_it(self):
        from piper import PiperVoice, SynthesisConfig
        text = 'The quick brown fox jumps over the lazy dog. It was not amused.'
        piper = PiperVoice.load(VOICE)
        expected = b''.join(chunk.audio_int16_bytes for chunk in
                            piper.synthesize(text, SynthesisConfig(noise_scale=0, noise_w_scale=0)))
        self.assertEqual(b''.join(pcm for pcm, _ in self.speak(text, events=False)), expected)

    def test_words_are_where_they_are_heard(self):
        text = 'In 1984, Dr. Smith paid $3.50 for "two" books – quietly.'
        chunks = self.speak(text)
        self.assertTrue(self.voice.timed)
        offset, previous = 0, -1
        heard = []
        for pcm, described in chunks:
            for start, end, first, last in described['words']:
                self.assertLessEqual(0, first)
                self.assertLess(first, last)
                self.assertLessEqual(last, len(pcm) // 2)
                self.assertGreater(offset + first, previous)
                previous = offset + first
                heard.append(text[start:end])
            offset += len(pcm) // 2
        self.assertEqual(heard, ['In', '1984', 'Dr', 'Smith', 'paid', '$3.50', 'for', 'two', 'books', 'quietly'])
        self.assertTrue(chunks[0][1]['sentence'])

    def test_a_long_sentence_comes_in_clause_sized_chunks(self):
        text = ', '.join(['one two three four five six seven'] * 6) + '.'
        chunks = self.speak(text)
        self.assertGreater(len(chunks), 1)
        self.assertEqual([described['sentence'] for _, described in chunks], [True] + [False] * (len(chunks) - 1))


if __name__ == '__main__':
    unittest.main()
