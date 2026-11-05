import io
from pathlib import Path
import tempfile
import time
import subprocess
import unittest
import wave
from unittest.mock import patch, Mock

from akousousin_backend.recognition import Recognizer, language_token, load_model, read_wav, model_root, capture


def wav(rate=16000, seconds=.1):
    out = io.BytesIO()
    with wave.open(out, 'wb') as audio:
        audio.setparams((1, 2, rate, 0, 'NONE', ''))
        audio.writeframes(b'\0\0' * int(rate * seconds))
    return out.getvalue()


def fake_worker(pipe, config):
    pipe.send((True, {'model': config['model'], 'fallback': None}))
    try:
        while True:
            request = pipe.recv()
            if request is None:
                return
            if request['language'] == 'de':
                time.sleep(10)
            if request['language'] == 'fr':
                return
            pipe.send((True, {'text': 'hello', 'language': request['language'] or 'en'}))
    except EOFError:
        pass
    finally:
        pipe.close()


class RecognitionTests(unittest.TestCase):
    def test_language_mapping(self):
        for value in ('de-DE', 'de_DE', 1031):
            self.assertEqual(language_token(value), 'de')
        self.assertIsNone(language_token(None))
        for value in (True, {}, 999999, 'English', '../en'):
            with self.assertRaises(ValueError):
                language_token(value)

    def test_wav_boundary(self):
        self.assertEqual(len(read_wav(wav())), 3200)
        for value in (wav(rate=8000), wav(seconds=0), wav(seconds=31), wav()[:-2]):
            with self.assertRaises(ValueError):
                read_wav(value)

    def test_offline_fallback(self):
        calls = []
        def factory(path, **options):
            calls.append((Path(path).name, options))
            if Path(path).name == 'turbo':
                raise OSError('corrupted')
            return object()
        with self.assertLogs(level='ERROR'):
            _, selected, warning = load_model('/models', 'turbo', factory)
        self.assertEqual(selected, 'small')
        self.assertTrue(warning)
        self.assertEqual([name for name, _ in calls], ['turbo', 'small'])
        self.assertTrue(all(options['local_files_only'] for _, options in calls))
        self.assertTrue(all(options['compute_type'] == 'int8' for _, options in calls))
        with self.assertRaises(OSError):
            load_model('/models', 'small', lambda *a, **k: (_ for _ in ()).throw(OSError()))

    def test_xdg(self):
        with patch.dict('os.environ', {'XDG_DATA_HOME': '/example'}):
            import os
            if os.name != 'nt':
                self.assertEqual(model_root(), Path('/example/Akousousin/models/whisper'))

    @unittest.skipIf(__import__('os').name == 'nt', 'Linux capture adapter')
    def test_capture_ready_discards_startup_and_cue(self):
        events = []
        process = Mock()
        process.poll.return_value = None
        def launch(args, stdout, stderr):
            stdout.write(b'\x02\x00' * 100)
            stdout.flush()
            def wait(timeout):
                if timeout == 1:
                    stdout.write(b'\x01\x00' * 16000)
                    stdout.flush()
                    raise subprocess.TimeoutExpired('parec', 1)
                return 0
            process.wait.side_effect = wait
            return process
        with patch('akousousin_backend.recognition.subprocess.Popen', side_effect=launch) as command:
            data = capture(1, 'test microphone', cue=lambda: events.append('cue'),
                           on_ready=lambda: events.append('ready'))
        self.assertEqual(events, ['cue', 'ready'])
        self.assertEqual(read_wav(data), b'\x01\x00' * 16000)
        self.assertIn('--device=test microphone', command.call_args.args[0])
        process.terminate.assert_called_once()

    @unittest.skipIf(__import__('os').name == 'nt', 'Linux capture adapter')
    def test_capture_failure_does_not_signal_ready(self):
        process = Mock()
        process.poll.return_value = 1
        def launch(args, stdout, stderr):
            stderr.write(b'connection refused'); stderr.flush()
            return process
        ready = Mock()
        with patch('akousousin_backend.recognition.subprocess.Popen', side_effect=launch):
            with self.assertRaisesRegex(RuntimeError, 'connection refused'):
                capture(1, on_ready=ready)
        ready.assert_not_called()

    def test_timeout_death_and_recovery(self):
        recognizer = Recognizer(timeout=.1, target=fake_worker)
        try:
            self.assertEqual(recognizer.transcribe(wav())['language'], 'en')
            with self.assertRaises(TimeoutError):
                recognizer.transcribe(wav(), 'de')
            self.assertIsNone(recognizer.process)
            self.assertEqual(recognizer.transcribe(wav(), 'en')['text'], 'hello')
            with self.assertRaises(EOFError):
                recognizer.transcribe(wav(), 'fr')
            self.assertEqual(recognizer.transcribe(wav())['text'], 'hello')
            recognizer.lock.acquire()
            try:
                with self.assertRaises(BlockingIOError):
                    recognizer.transcribe(wav())
            finally:
                recognizer.lock.release()
        finally:
            recognizer.close()
