# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Dictation phrase detection with Silero, and the loudness fallback."""
import importlib.util
import unittest
from unittest.mock import patch

from akousousin_backend.audio_input import Capture, Endpoint, FRAME_BYTES, Loudness, Silero
from akousousin_backend.recognition import read_wav

HAVE_SILERO = all(importlib.util.find_spec(name) for name in ('numpy', 'onnxruntime', 'faster_whisper'))
RATE = 16000


def frames(pcm):
    return [pcm[i:i + FRAME_BYTES] for i in range(0, len(pcm) - FRAME_BYTES + 1, FRAME_BYTES)]


def run(endpoint, pcm):
    return [segment for segment in map(endpoint.feed, frames(pcm)) if segment]


class Scripted:
    """Stands in for SpeechDetector: one scripted probability per 512 samples."""
    def __init__(self, probabilities):
        self.probabilities = list(probabilities)
        self.samples = 0

    def feed(self, pcm):
        self.samples += len(pcm) // 2
        out = []
        while self.samples >= 512 and self.probabilities:
            self.samples -= 512
            out.append(self.probabilities.pop(0))
        return out


class HysteresisTests(unittest.TestCase):
    def test_phrase_starts_at_half_and_continues_down_to_lower_threshold(self):
        # 0.4 alone never starts a phrase, but keeps one going once started.
        script = [.4] * 20 + [.9] * 10 + [.4] * 20 + [.05] * 30
        endpoint = Endpoint(voice=Silero(Scripted(script)))
        segments = run(endpoint, b'\0' * 512 * 2 * len(script))
        self.assertEqual(len(segments), 1)
        self.assertEqual(endpoint.last_metadata['speech_detector'], 'silero')
        # The 10 confident chunks alone are 0.32 s; the 20 that continue it make 0.96 s.
        self.assertAlmostEqual(endpoint.last_metadata['speech_seconds'], .96, delta=.04)

    def test_moderate_probability_alone_never_starts_a_phrase(self):
        endpoint = Endpoint(voice=Silero(Scripted([.45] * 200)))
        self.assertEqual(run(endpoint, b'\0' * 512 * 2 * 200), [])

    def test_loudness_is_the_default_and_names_itself(self):
        endpoint = Endpoint()
        self.assertIsInstance(endpoint.voice, Loudness)
        run(endpoint, b'\xe8\x03' * 320 * 30 + b'\0' * 640 * 30)
        self.assertEqual(endpoint.last_metadata['speech_detector'], 'loudness')


@unittest.skipUnless(HAVE_SILERO, 'Silero needs the recognition extras')
class SileroTests(unittest.TestCase):
    """The real model on sounds that fool a loudness threshold, and on speech-like sound."""
    @classmethod
    def setUpClass(cls):
        import numpy
        from akousousin_backend.voice_activity import detector
        cls.np = numpy
        cls.detector = staticmethod(lambda: detector()[0])

    def pcm(self, samples):
        return (self.np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()

    def syllables(self, seconds, seed=0):
        """Voiced syllables: a glottal pulse train shaped by vowel formants, with short gaps."""
        np = self.np
        vowels = ((700, 1220, 2600), (300, 2300, 3000), (500, 900, 2500), (400, 1900, 2550), (350, 800, 2300))
        rng = np.random.default_rng(seed)
        parts, total = [], 0
        while total < seconds * RATE:
            n = int(RATE * rng.uniform(.14, .24))
            t = np.arange(n) / RATE
            pitch = rng.uniform(105, 140) * (1 + .08 * np.sin(np.pi * t / t[-1]))
            phase = np.cumsum(2 * np.pi * pitch / RATE)
            source = sum(np.sin(k * phase) / k for k in range(1, 30))
            voice = np.zeros(n)
            for f in vowels[rng.integers(len(vowels))]:
                r = np.exp(-np.pi * (90 + f / 20) / RATE)
                a1, a2 = 2 * r * np.cos(2 * np.pi * f / RATE), -r * r
                y = np.zeros(n)
                for i in range(2, n):
                    y[i] = source[i] + a1 * y[i - 1] + a2 * y[i - 2]
                voice += y
            voice *= np.minimum(1, np.minimum(t / .02, (t[-1] - t) / .03))
            gap = rng.normal(0, .0006, int(RATE * rng.uniform(.03, .07)))
            parts += [voice / np.abs(voice).max() * .25, gap]
            total += n + len(gap)
        return self.pcm(np.concatenate(parts)[:int(seconds * RATE)])

    def silence(self, seconds):
        return b'\0' * int(seconds * RATE) * 2

    def test_fan_noise_is_not_speech_though_loud_enough_for_the_threshold(self):
        noise = self.pcm(self.np.random.default_rng(1).normal(0, .1, 4 * RATE))
        loudness = Endpoint()
        run(loudness, noise)
        self.assertTrue(loudness.frames, 'precondition: loudness takes this noise for one long phrase')
        silero = Endpoint(voice=Silero(self.detector()))
        self.assertEqual(run(silero, noise), [])
        self.assertEqual(silero.frames, [])

    def test_mains_hum_is_not_speech(self):
        t = self.np.arange(4 * RATE) / RATE
        hum = self.pcm(.2 * self.np.sin(2 * self.np.pi * 120 * t) + .05 * self.np.sin(2 * self.np.pi * 240 * t))
        self.assertEqual(run(Endpoint(voice=Silero(self.detector())), hum), [])

    def test_syllables_make_one_phrase_ended_by_silence(self):
        endpoint = Endpoint(voice=Silero(self.detector()))
        segments = run(endpoint, self.silence(.5) + self.syllables(2) + self.silence(1))
        self.assertEqual(len(segments), 1)
        seconds = len(read_wav(segments[0])) / 2 / RATE
        self.assertGreater(seconds, 1.8)
        self.assertLess(seconds, 2.8)
        self.assertEqual(endpoint.last_metadata['speech_detector'], 'silero')

    def test_two_phrases_separated_by_a_pause(self):
        endpoint = Endpoint(voice=Silero(self.detector()))
        pcm = self.syllables(1.2, 2) + self.silence(.8) + self.syllables(1.2, 3) + self.silence(.8)
        self.assertEqual(len(run(endpoint, pcm)), 2)

    def test_detectors_share_one_model_session(self):
        first, second = self.detector(), self.detector()
        self.assertIs(first.session, second.session)
        self.assertIsNot(first.h, second.h)


class CaptureChoiceTests(unittest.TestCase):
    def test_capture_falls_back_to_loudness_when_silero_cannot_load(self):
        capture = Capture()
        with patch('akousousin_backend.voice_activity.detector', return_value=(None, 'no onnxruntime')), \
                patch('akousousin_backend.audio_input.os.name', 'nt'), self.assertLogs(level='WARNING') as logs:
            capture._pump()
        self.assertEqual(capture.endpoint.voice.name, 'loudness')
        self.assertIn('no onnxruntime', logs.output[0])

    def test_capture_uses_silero_when_available(self):
        capture = Capture()
        with patch('akousousin_backend.voice_activity.detector', return_value=(Scripted([]), '')), \
                patch('akousousin_backend.audio_input.os.name', 'nt'):
            capture._pump()
        self.assertEqual(capture.endpoint.voice.name, 'silero')


if __name__ == '__main__':
    unittest.main()
