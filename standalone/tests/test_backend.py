import copy
import io
from pathlib import Path
import tempfile
import threading
import unittest
import wave
from unittest.mock import patch

from opensapi_app import settings
from opensapi_app.backend import Router, application


def audio(rate):
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setparams((1, 2, rate, 0, 'NONE', ''))
        wav.writeframes(b'\x10\x00' * 100)
    return output.getvalue()


class FakeSynth:
    instances = []
    def __init__(self, model, target):
        self.rate = 16000 if 'german' in str(model) else 22050
        self.requests = []
        self.closed = False
        self.instances.append(self)
    def start(self):
        pass
    def close(self):
        self.closed = True
    def synthesize(self, request):
        self.requests.append(request)
        return audio(self.rate)


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.path = root / 'settings.json'
        self.config = copy.deepcopy(settings.DEFAULTS)
        for identifier, language, rate in [('english', 'en_US', 22050), ('german', 'de_DE', 16000)]:
            model = root / (identifier + '.onnx')
            model.touch(); Path(str(model) + '.json').write_text('{}')
            self.config['voices'][identifier] = {'path': str(model), 'language': language, 'sample_rate': rate}
            self.config['language_voices'][language] = identifier
        self.config['voice'] = 'english'
        settings.save(self.path, self.config)
        self.patch = patch('opensapi_app.backend.Synthesizer', FakeSynth)
        self.patch.start(); self.addCleanup(self.patch.stop)
        FakeSynth.instances.clear()
        self.router = Router(self.path)
        self.addCleanup(self.router.close)

    def test_explicit_sapi_language_routes_and_resamples(self):
        result = self.router.synthesize({'text': 'Guten Tag', 'language': 0x407, 'sample_rate': 22050})
        self.assertEqual(self.router.voice, 'german')
        with wave.open(io.BytesIO(result), 'rb') as wav:
            self.assertEqual(wav.getframerate(), 22050)
            self.assertGreater(wav.getnframes(), 100)

    def test_manual_book_language_overrides_default(self):
        self.config['book_language'] = 'de_DE'
        settings.save(self.path, self.config)
        self.router.synthesize({'text': 'Text', 'voice': 'english'})
        self.assertEqual(self.router.voice, 'german')

    def test_changing_voice_releases_previous_worker(self):
        self.router.synthesize({'text': 'Hello'})
        old = self.router.synth
        self.router.synthesize({'text': 'Hallo', 'voice': 'german'})
        self.assertTrue(old.closed)
        self.assertEqual(len(FakeSynth.instances), 2)

    def test_preferences_apply_to_new_speech(self):
        self.config.update(speed=2.0, volume=.5)
        settings.save(self.path, self.config)
        self.router.synthesize({'text': 'Hello', 'length_scale': 1})
        self.assertEqual(self.router.synth.requests[-1]['length_scale'], .5)
        self.assertEqual(self.router.synth.requests[-1]['volume'], .5)

    def test_missing_model_fails_without_selecting_wrong_voice(self):
        Path(self.config['voices']['german']['path']).unlink()
        with self.assertRaisesRegex(RuntimeError, 'missing'):
            self.router.synthesize({'text': 'Hallo', 'voice': 'german'})

    def test_shutdown_requires_private_control_token(self):
        stopping = threading.Event()
        app = application(self.router, 'instance', 'private-token', stopping)
        env = {'PATH_INFO': '/shutdown', 'REQUEST_METHOD': 'POST'}
        status = []
        app(env, lambda *args: status.append(args[0]))
        self.assertTrue(status[0].startswith('403'))
        self.assertFalse(stopping.is_set())
        env['HTTP_X_OPENSAPI_CONTROL'] = 'private-token'
        app(env, lambda *args: status.append(args[0]))
        self.assertTrue(stopping.is_set())
