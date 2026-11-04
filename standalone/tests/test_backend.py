import copy
import io
from pathlib import Path
import tempfile
import threading
import unittest
import wave
from unittest.mock import patch

from akousousin_app import settings
from akousousin_app.backend import Router, application


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
    def start(self, cancelled=None):
        pass
    def close(self):
        self.closed = True
    def synthesize(self, request, cancelled=None):
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
        self.patch = patch('akousousin_app.backend.Synthesizer', FakeSynth)
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
        env['HTTP_X_AKOUSOUSIN_CONTROL'] = 'private-token'
        app(env, lambda *args: status.append(args[0]))
        self.assertTrue(stopping.wait(1))

    def test_idle_unloads_and_next_request_reloads(self):
        self.router.synthesize({'text': 'Hello'})
        previous = self.router.synth
        self.assertFalse(self.router.expire(self.router.last_activity + 299))
        self.assertTrue(self.router.expire(self.router.last_activity + 300))
        self.assertTrue(previous.closed)
        self.assertIsNone(self.router.synth)
        self.router.synthesize({'text': 'Again'})
        self.assertIsNot(self.router.synth, previous)

    def test_idle_can_be_disabled_and_health_does_not_keep_model_alive(self):
        self.router.start()
        self.config['idle_timeout'] = 0
        settings.save(self.path, self.config)
        self.assertFalse(self.router.expire(self.router.last_activity + 100000))
        for invalid in (-1, True, 1.5, 86401):
            with self.assertRaises(ValueError):
                settings.validate(dict(self.config, idle_timeout=invalid))

    def test_cancel_only_matches_current_request(self):
        self.router.active_request = 'private-id'
        self.assertFalse(self.router.cancel('other-client'))
        self.assertFalse(self.router.cancel(''))
        self.assertFalse(self.router.cancel(None))
        self.assertFalse(self.router.cancelled.is_set())
        self.assertTrue(self.router.cancel('private-id'))
        self.assertTrue(self.router.cancelled.is_set())

    def test_idle_poll_does_not_take_speech_lock_before_expiry(self):
        self.router.start()
        # Real HTTP dispatch and event-loop maintenance are concurrent. Even an
        # uncontended maintenance lock can cause a false busy response there.
        from unittest.mock import Mock
        self.router.lock = Mock()
        self.assertFalse(self.router.expire(self.router.last_activity + 1))
        self.router.lock.acquire.assert_not_called()
        self.router.lock = threading.RLock()

    def test_http_cancel_interrupts_only_matching_request_and_recovers(self):
        entered = threading.Event()
        original = FakeSynth.synthesize
        def synthesize(synth, request, cancelled=None):
            if request['text'] == 'wait':
                entered.set()
                if not cancelled.wait(2):
                    raise AssertionError('Cancellation did not arrive')
                raise InterruptedError('Cancelled')
            return original(synth, request, cancelled)
        self.patch_synth = patch.object(FakeSynth, 'synthesize', synthesize)
        self.patch_synth.start()
        self.addCleanup(self.patch_synth.stop)
        app = application(self.router, 'instance')
        def call(path, identifier, text=''):
            import json
            raw = json.dumps({'text': text}).encode()
            status = []
            env = {'PATH_INFO': path, 'REQUEST_METHOD': 'POST', 'HTTP_X_AKOUSOUSIN_REQUEST': identifier,
                   'CONTENT_LENGTH': str(len(raw)), 'wsgi.input': io.BytesIO(raw)}
            app(env, lambda *args: status.append(args[0]))
            return status[0]
        responses = []
        task = threading.Thread(target=lambda: responses.append(call('/synthesize', 'owner', 'wait')))
        task.start()
        self.assertTrue(entered.wait(1))
        self.assertEqual(call('/cancel', 'someone-else'), '404 Not Found')
        self.assertEqual(call('/cancel', 'owner'), '200 OK')
        task.join(2)
        self.assertFalse(task.is_alive())
        self.assertEqual(responses, ['409 Conflict'])
        self.assertEqual(call('/synthesize', 'next-owner', 'again'), '200 OK')

    def test_waiting_caller_cancel_leaves_active_caller_running(self):
        import time
        entered, release = threading.Event(), threading.Event()
        original = FakeSynth.synthesize
        results = []
        def blocked(synth, request, cancelled=None):
            if request['text'] == 'active':
                entered.set()
                if not release.wait(3):
                    raise AssertionError('Active caller was not released')
                self.assertFalse(cancelled.is_set())
            return original(synth, request, cancelled)
        def call(text, identifier):
            try:
                self.router.synthesize({'text': text}, identifier)
                results.append((identifier, 'ok'))
            except InterruptedError:
                results.append((identifier, 'cancelled'))
        with patch.object(FakeSynth, 'synthesize', blocked):
            active = threading.Thread(target=call, args=('active', 'sapi'))
            waiting = threading.Thread(target=call, args=('waiting', 'dispatcher'))
            active.start()
            self.assertTrue(entered.wait(1))
            waiting.start()
            deadline = time.monotonic() + 1
            queued = False
            while time.monotonic() < deadline:
                with self.router.control_lock:
                    queued = 'dispatcher' in self.router.waiters
                if queued:
                    break
                time.sleep(.01)
            self.assertTrue(queued)
            self.assertTrue(self.router.cancel('dispatcher'))
            waiting.join(1)
            release.set()
            active.join(1)
        self.assertCountEqual(results, [('dispatcher', 'cancelled'), ('sapi', 'ok')])
        self.router.synthesize({'text': 'recovered'}, 'next')
