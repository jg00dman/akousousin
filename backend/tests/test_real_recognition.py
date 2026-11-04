"""Opt-in actual CPU inference. No model downloads occur during these tests."""
import io
import os
from pathlib import Path
import tempfile
import unittest
import wave

from akousousin_backend.recognition import Recognizer

MODELS = os.environ.get('AKS_TEST_WHISPER_MODELS')
SPEECH = os.environ.get('AKS_TEST_WHISPER_JFK_WAV')


@unittest.skipUnless(MODELS and SPEECH, 'Set AKS_TEST_WHISPER_MODELS and AKS_TEST_WHISPER_JFK_WAV')
class RealRecognitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audio = Path(SPEECH).read_bytes()
        cls.recognizer = Recognizer(MODELS)

    @classmethod
    def tearDownClass(cls):
        cls.recognizer.close()

    def assert_speech(self, result):
        text = result['text'].lower()
        self.assertIn('ask not what your country can do for you', text)
        self.assertIn('what you can do for your country', text)
        self.assertEqual(result['language'], 'en')
        self.assertEqual(result['model'], 'small')

    def test_automatic_language_and_speech(self):
        result = self.recognizer.transcribe(self.audio)
        self.assert_speech(result)
        self.assertEqual(result['language_source'], 'detected')
        self.assertGreater(result['language_probability'], .8)

    def test_application_lcid_lock(self):
        result = self.recognizer.transcribe(self.audio, 1033)
        self.assert_speech(result)
        self.assertEqual(result['language_source'], 'explicit')
        self.assertIsNone(result['language_probability'])

    def test_silence_has_no_text_or_detected_language(self):
        out = io.BytesIO()
        with wave.open(out, 'wb') as audio:
            audio.setparams((1, 2, 16000, 0, 'NONE', ''))
            audio.writeframes(b'\0\0' * 16000 * 5)
        result = self.recognizer.transcribe(out.getvalue())
        self.assertEqual(result['text'], '')
        self.assertIsNone(result['language'])
        self.assertIsNone(result['language_probability'])

    @unittest.skipUnless(os.environ.get('AKS_TEST_WHISPER_GERMAN_WAV'), 'Optional German speech fixture')
    def test_german_detection_and_speech(self):
        audio = Path(os.environ['AKS_TEST_WHISPER_GERMAN_WAV']).read_bytes()
        result = self.recognizer.transcribe(audio)
        self.assertEqual(result['language'], 'de')
        self.assertEqual(result['language_source'], 'detected')
        self.assertIn('guten morgen', result['text'].lower())
        self.assertIn('deutschen text', result['text'].lower())

    def test_missing_turbo_falls_back_to_real_small(self):
        recognizer = Recognizer(MODELS, model='turbo')
        try:
            result = recognizer.transcribe(self.audio, 'en')
            self.assert_speech(result)
            self.assertTrue(result['fallback'])
        finally:
            recognizer.close()

    def test_missing_models_fail_without_download(self):
        with tempfile.TemporaryDirectory() as root:
            recognizer = Recognizer(root)
            try:
                with self.assertRaises(RuntimeError):
                    recognizer.transcribe(self.audio)
                self.assertIsNone(recognizer.process)
                self.assertEqual(list(Path(root).iterdir()), [])
            finally:
                recognizer.close()
