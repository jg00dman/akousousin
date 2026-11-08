# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import io
import os
import struct
from pathlib import Path
import tempfile
import time
import threading
import subprocess
import unittest
import wave
from unittest.mock import patch, Mock

from akousousin_backend.recognition import Recognizer, language_token, load_model, read_wav, model_root, capture, ready_cue


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


def slow_start_worker(pipe, config):
    time.sleep(10)


class RecognitionTests(unittest.TestCase):
    def test_cancel_loading_and_inference_recover(self):
        recognizer = Recognizer(target=slow_start_worker)
        event = threading.Event()
        timer = threading.Timer(.1, event.set); timer.start()
        try:
            with self.assertRaises(InterruptedError):
                recognizer.start(event)
            self.assertIsNone(recognizer.process)
            recognizer.target = fake_worker
            recognizer.start()
            event.clear()
            timer = threading.Timer(.1, event.set); timer.start()
            with self.assertRaises(InterruptedError):
                recognizer.transcribe(wav(), 'de', event)
            self.assertIsNone(recognizer.process)
            self.assertEqual(recognizer.transcribe(wav())['text'], 'hello')
        finally:
            timer.cancel()
            recognizer.close()

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
        def launch(args, stdout, stderr, **kwargs):
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
        def launch(args, stdout, stderr, **kwargs):
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


@unittest.skipIf(os.name == 'nt', 'Linux system audio player')
class ReadyCueTests(unittest.TestCase):
    def test_two_tones_use_host_libraries_and_identifiable_stream(self):
        def play(arguments, **options):
            with wave.open(arguments[-1], 'rb') as sound:
                self.assertEqual((sound.getframerate(), sound.getnchannels()), (16000, 1))
                pcm = sound.readframes(sound.getnframes())
            samples = struct.unpack('<' + 'h' * (len(pcm) // 2), pcm)
            self.assertEqual(set(samples[:3200]), {0})
            samples = samples[3200:]
            self.assertGreater(max(samples[:1600]), 32000)
            self.assertLessEqual(max(samples), 32767)
            crossings = sum(samples[i] <= 0 < samples[i + 1] for i in range(1599))
            self.assertIn(crossings, (29, 30, 31))
            self.assertEqual(set(samples[1600:3040]), {0})
            self.assertGreater(max(samples[3040:]), 32000)
            self.assertNotIn('LD_LIBRARY_PATH', options['env'])
            self.assertNotIn('LD_LIBRARY_PATH_ORIG', options['env'])
            self.assertIn('--client-name=Akousousin', arguments)
            self.assertTrue(options['check'])
        with patch.dict(os.environ, {'LD_LIBRARY_PATH': '/private/appimage', 'LD_LIBRARY_PATH_ORIG': '/tmp/.mount_parent/lib'}), patch('shutil.which', return_value='/usr/bin/paplay'), patch('subprocess.run', side_effect=play):
            ready_cue()

    def test_playback_error_retains_player_diagnostic(self):
        error = subprocess.CalledProcessError(1, ['paplay'], stderr='Connection refused')
        with patch('shutil.which', return_value='/usr/bin/paplay'), patch('subprocess.run', side_effect=error):
            with self.assertRaisesRegex(RuntimeError, 'Ready sound playback failed: Connection refused'):
                ready_cue()

    def test_no_player_has_clear_error(self):
        with patch('shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'paplay or pw-play'):
                ready_cue()


class WarmupTests(unittest.TestCase):
    def test_ready_warmup_consumes_lazy_inference_without_network_or_user_text(self):
        from akousousin_backend.recognition import warm_model
        model = Mock()
        consumed = []
        def segments():
            consumed.append(True)
            yield Mock(text='discard this warm-up output')
        model.transcribe.return_value = (segments(), Mock())
        elapsed = warm_model(model)
        self.assertTrue(consumed)
        self.assertGreaterEqual(elapsed, 0)
        self.assertFalse(model.transcribe.call_args.kwargs['vad_filter'])
        self.assertEqual(model.transcribe.call_args.kwargs['temperature'], 0.0)
        self.assertEqual(model.transcribe.call_args.kwargs['language'], 'en')
        self.assertEqual(float(model.transcribe.call_args.args[0].max()), 0)


class AssetActivationTests(unittest.TestCase):
    def test_inference_does_not_download_but_explicit_activation_downloads_once(self):
        from akousousin_backend.recognition import prepare_model_assets
        cached = set()
        config = {'root': '/model-cache', 'model': 'turbo'}
        with patch('akousousin_backend.models.installed', side_effect=lambda model, root: model in cached), patch('akousousin_backend.models.install', side_effect=lambda model, **kwargs: cached.add(model)) as install:
            prepare_model_assets(config)
            install.assert_not_called()
            config['download_missing'] = True
            prepare_model_assets(config)
            prepare_model_assets(config)
            install.assert_called_once_with('small', root='/model-cache')
