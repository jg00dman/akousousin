import io
import json
import time
import unittest
import wave
from akousousin_backend.server import Synthesizer, application


def fake_worker(pipe, model):
    pipe.send((True, 22050))
    while True:
        request = pipe.recv()
        if request['text'] == 'hang':
            time.sleep(10)
        if request['text'] == 'die':
            return
        out = io.BytesIO()
        with wave.open(out, 'wb') as wav:
            wav.setparams((1, 2, 22050, 0, 'NONE', ''))
            wav.writeframes(b'\x01\x00' * 100)
        pipe.send((True, out.getvalue()))


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.synth = Synthesizer('test.onnx', timeout=0.1, target=fake_worker)
        self.synth.start()
        self.app = application(self.synth, 'test.onnx', 'test-instance')

    def tearDown(self):
        self.synth.close()

    def call(self, data=None, path='/synthesize', method='POST'):
        raw = json.dumps(data).encode()
        result = []
        env = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'CONTENT_LENGTH': str(len(raw)),
               'wsgi.input': io.BytesIO(raw)}
        body = b''.join(self.app(env, lambda *args: result.append(args)))
        return result[0][0], body

    def test_audio_and_health(self):
        status, body = self.call({'text': 'test', 'length_scale': 0.5})
        self.assertEqual(status, '200 OK')
        self.assertTrue(body.startswith(b'RIFF'))
        status, body = self.call(path='/health', method='GET')
        self.assertEqual(json.loads(body)['instance'], 'test-instance')

    def test_timeout_and_recovery(self):
        status, _ = self.call({'text': 'hang'})
        self.assertTrue(status.startswith('504'))
        self.assertIsNone(self.synth.process)
        self.assertEqual(self.call({'text': 'recovered'})[0], '200 OK')

    def test_worker_death_and_recovery(self):
        self.assertTrue(self.call({'text': 'die'})[0].startswith('503'))
        self.assertEqual(self.call({'text': 'recovered'})[0], '200 OK')

    def test_bad_requests(self):
        for data in ({}, {'text': ''}, {'text': ['bad']}, {'text': 'x', 'length_scale': 0},
                     {'text': 'x', 'length_scale': float('nan')}, {'text': 'x' * 16001}, []):
            self.assertTrue(self.call(data)[0].startswith('400'))

    def test_busy_is_bounded(self):
        self.synth.lock.acquire()
        try:
            self.assertTrue(self.call({'text': 'busy'})[0].startswith('503'))
        finally:
            self.synth.lock.release()

    def test_unavailable_health(self):
        self.synth.close()
        self.assertTrue(self.call(path='/health', method='GET')[0].startswith('503'))

    def test_cancel_during_inference_releases_worker_and_allows_retry(self):
        import threading
        cancelled = threading.Event()
        self.synth.timeout = 20
        timer = threading.Timer(.1, cancelled.set)
        timer.start()
        started = time.monotonic()
        with self.assertRaises(InterruptedError):
            self.synth.synthesize({'text': 'hang', 'length_scale': 1}, cancelled)
        timer.join()
        self.assertLess(time.monotonic() - started, 2)
        self.assertIsNone(self.synth.process)
        self.assertTrue(self.synth.synthesize({'text': 'again', 'length_scale': 1}).startswith(b'RIFF'))

    def test_cancel_during_cold_start_is_bounded(self):
        import threading
        cancelled = threading.Event()
        cancelled.set()
        self.synth.close()
        started = time.monotonic()
        with self.assertRaises(InterruptedError):
            self.synth.start(cancelled)
        self.assertLess(time.monotonic() - started, 2)
        self.assertIsNone(self.synth.process)
