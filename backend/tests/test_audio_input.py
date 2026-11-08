# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import queue
import subprocess
import sys
import time
from unittest.mock import patch, Mock
import unittest

from akousousin_backend.audio_input import Capture, Endpoint, FRAME_BYTES
from akousousin_backend.recognition import read_wav

VOICE = b'\xe8\x03' * (FRAME_BYTES // 2)
QUIET = b'\0' * FRAME_BYTES


class AudioInputTests(unittest.TestCase):
    def test_silence_is_bounded_and_emits_nothing(self):
        endpoint = Endpoint()
        for _ in range(5000):
            self.assertIsNone(endpoint.feed(QUIET))
        self.assertEqual(len(endpoint.preroll), 12)
        self.assertEqual(endpoint.frames, [])
        self.assertIsNone(endpoint.finish())

    def test_phrase_ends_after_silence_and_retains_preroll(self):
        endpoint = Endpoint()
        for _ in range(20):
            endpoint.feed(QUIET)
        for _ in range(25):
            self.assertIsNone(endpoint.feed(VOICE))
        for _ in range(24):
            self.assertIsNone(endpoint.feed(QUIET))
        result = endpoint.feed(QUIET)
        self.assertIsNotNone(result)
        self.assertTrue(read_wav(result).startswith(QUIET * 11))
        self.assertEqual(endpoint.frames, [])

    def test_long_speech_is_cut_to_a_bounded_chunk(self):
        endpoint = Endpoint(max_frames=50)
        results = [endpoint.feed(VOICE) for _ in range(50)]
        self.assertEqual(len(read_wav(results[-1])), 50 * FRAME_BYTES)
        self.assertEqual(endpoint.frames, [])

    def test_pause_reset_discards_partial_audio(self):
        endpoint = Endpoint()
        for _ in range(20):
            endpoint.feed(VOICE)
        endpoint.reset()
        for _ in range(50):
            self.assertIsNone(endpoint.feed(QUIET))
        self.assertIsNone(endpoint.finish())

    def test_short_noise_burst_is_not_submitted(self):
        endpoint = Endpoint()
        endpoint.feed(VOICE)
        for _ in range(50):
            self.assertIsNone(endpoint.feed(QUIET))

    def test_calibrated_room_noise_is_not_continuous_speech(self):
        endpoint = Endpoint()
        noise = b'\x90\x01' * (FRAME_BYTES // 2)
        endpoint.calibrate(noise * 10)
        for _ in range(200):
            self.assertIsNone(endpoint.feed(noise))
        for _ in range(25):
            endpoint.feed(VOICE)
        result = None
        for _ in range(25):
            result = endpoint.feed(noise)
        self.assertIsNotNone(result)
        self.assertEqual(endpoint.last_metadata['endpoint_wait_seconds'], .5)
        self.assertEqual(endpoint.last_metadata['speech_seconds'], .5)
        self.assertLess(len(read_wav(result)), 2 * 16000)

    def test_default_cap_is_eight_seconds(self):
        endpoint = Endpoint()
        for _ in range(399):
            self.assertIsNone(endpoint.feed(VOICE))
        self.assertIsNotNone(endpoint.feed(VOICE))

    def test_backlog_is_bounded_and_reported(self):
        capture = Capture()
        capture.put(b'first'); capture.put(b'second')
        with self.assertRaisesRegex(RuntimeError, 'cannot keep up'):
            capture.put(b'third')
        self.assertEqual(capture.segments.qsize(), 2)


class StreamingProcessTests(unittest.TestCase):
    def test_stream_endpointing_and_shutdown_with_real_pipe(self):
        original = subprocess.Popen
        emitter = "import sys,time\nfor i in range(150):\n sys.stdout.buffer.write((b'\\xe8\\x03' if i%75 < 30 else b'\\0\\0')*320); sys.stdout.buffer.flush(); time.sleep(.02)\ntime.sleep(5)"
        def launch(args, **kwargs):
            return original([sys.executable, '-c', emitter], **kwargs)
        capture = Capture()
        with patch('akousousin_backend.audio_input.subprocess.Popen', side_effect=launch):
            try:
                capture.start()
                segment = capture.segments.get(timeout=5)
                self.assertTrue(capture.ready.is_set())
                self.assertTrue(read_wav(segment))
                capture.finish()
            finally:
                capture.close()
        self.assertTrue(capture.done.is_set())
        self.assertFalse(capture.thread.is_alive())
        self.assertIsNone(capture.error)

    def test_cancel_before_first_frame_stops_subprocess(self):
        original = subprocess.Popen
        def launch(args, **kwargs):
            return original([sys.executable, '-c', 'import time; time.sleep(10)'], **kwargs)
        ended = Mock()
        capture = Capture(ended=ended)
        with patch('akousousin_backend.audio_input.subprocess.Popen', side_effect=launch):
            capture.start()
            time.sleep(.05)
            start = time.monotonic()
            capture.close()
        self.assertLess(time.monotonic() - start, 1)
        self.assertFalse(capture.ready.is_set())
        ended.assert_called_once()
        self.assertTrue(capture.done.is_set())
