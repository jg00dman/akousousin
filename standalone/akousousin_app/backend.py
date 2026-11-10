# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Multi-voice routing around the existing bounded Piper worker."""
import io
import json
import logging
import math
import hmac
from collections import deque
from pathlib import Path
import threading
import time
import wave

from akousousin_backend.server import Synthesizer, MAX_AUDIO, MAX_BODY
from . import settings, speech_gate


def worker(pipe, model):
    from piper import PiperVoice, SynthesisConfig
    try:
        voice = PiperVoice.load(model)
        pipe.send((True, voice.config.sample_rate))
        while True:
            request = pipe.recv()
            output = io.BytesIO()
            config = SynthesisConfig(length_scale=request['length_scale'], volume=request.get('volume', 1),
                                     noise_scale=request.get('noise_scale', .667),
                                     noise_w_scale=request.get('noise_w_scale', .8))
            with wave.open(output, 'wb') as wav:
                voice.synthesize_wav(request['text'], wav, syn_config=config)
            data = output.getvalue()
            if len(data) > MAX_AUDIO:
                raise ValueError('Audio exceeds limit')
            pipe.send((True, data))
    except (EOFError, BrokenPipeError):
        pass
    except Exception:
        logging.exception('Inference failed')
        try:
            pipe.send((False, 'Inference failed'))
        except (EOFError, BrokenPipeError):
            pass
    finally:
        pipe.close()


def resample(audio, target):
    import audioop  # Embedded Python 3.12; no external resampler or executable.
    with wave.open(io.BytesIO(audio), 'rb') as wav:
        rate = wav.getframerate()
        if rate == target:
            return audio
        pcm, _ = audioop.ratecv(wav.readframes(wav.getnframes()), 2, 1, rate, target, None)
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setparams((1, 2, target, 0, 'NONE', ''))
        wav.writeframes(pcm)
    return output.getvalue()


class Router:
    def __init__(self, path, target=worker):
        self.path = Path(path).resolve()
        self.target = target
        self.synth = None
        self.voice = None
        self.lock = threading.RLock()
        self.last_activity = time.monotonic()
        self.active_request = None
        self.cancelled = threading.Event()
        self.control_lock = threading.Lock()
        self.waiters = {}
        self.slots = threading.BoundedSemaphore(3)
        self.speaking_until = 0
        self.playback = deque()
        self.processing = False

    def speaking(self):
        if speech_gate.snapshot(self.path)[0]:
            return False
        with self.control_lock:
            return self.processing or time.monotonic() < self.speaking_until

    def expire(self, now=None):
        # Do not take the synthesis lock on every event-loop tick: dispatching
        # a new HTTP request and idle maintenance happen together, and that can
        # otherwise report a ready backend as busy. Recheck after taking it.
        timeout = settings.load(self.path)['idle_timeout']
        current = time.monotonic() if now is None else now
        if not self.synth or not timeout or current - self.last_activity < timeout:
            return False
        if not self.lock.acquire(False):
            return False
        try:
            timeout = settings.load(self.path)['idle_timeout']
            if self.synth and timeout and current - self.last_activity >= timeout:
                self.close()
                return True
            return False
        finally:
            self.lock.release()

    def choose(self, request, config):
        language = config['book_language'] or settings.language_for_lcid(request.get('language', 0))
        selected = config['language_voices'].get(language) if language else None
        return selected or request.get('voice') or config['voice']

    def start(self):
        config = settings.load(self.path)
        self.select(config['voice'], config)
        self.last_activity = time.monotonic()

    def select(self, selected, config, cancelled=None):
        if selected not in config['voices']:
            raise RuntimeError('Selected voice is not installed')
        model = Path(config['voices'][selected]['path'])
        if not model.is_file() or not Path(str(model) + '.json').is_file():
            raise RuntimeError('Voice model/configuration is missing')
        if self.synth is None or self.voice != selected:
            self.close()
            self.synth = Synthesizer(model, target=self.target)
            self.synth.start(cancelled)
            self.voice = selected

    def close(self):
        acquired = self.lock.acquire(timeout=.5)
        if not acquired:
            process = self.synth.process if self.synth else None
            try:
                if process:
                    process.terminate()
            except (ValueError, OSError):
                pass
            acquired = self.lock.acquire(timeout=4)
        if not acquired:
            return
        try:
            if self.synth:
                self.synth.close()
            self.synth = None
            self.voice = None
        finally:
            self.lock.release()

    def cancel(self, identifier):
        # Cancel both inference and audio already handed to a playback client.
        # Losing the latter leaves dictation paused for speech which was stopped.
        with self.control_lock:
            if not identifier:
                return False
            found = False
            if identifier in self.waiters:
                self.waiters[identifier].set()
                found = True
            if identifier == self.active_request:
                self.cancelled.set()
                found = True
            now, shift, remaining = time.monotonic(), 0, deque()
            for key, start, end in self.playback:
                if end <= now:
                    continue
                if key == identifier:
                    shift += max(0, end - max(start, now))
                    found = True
                else:
                    remaining.append((key, max(now, start - shift), max(now, end - shift)))
            self.playback = remaining
            if shift:
                # Keep a small drain margin for the host audio buffer, retaining
                # the full remaining duration of every other playback request.
                self.speaking_until = max(now + .1, remaining[-1][2] if remaining else 0)
            return found

    def stop_speaking(self):
        """Cancel current requests/playback without explicitly unloading the voice."""
        with self.control_lock:
            self.cancelled.set()
            for event in self.waiters.values():
                event.set()
            self.playback.clear()
            self.speaking_until = 0
            self.processing = False

    def record_playback(self, identifier, duration):
        # Called with control_lock held. Preserve conservative serial playback
        # timing but retain request ownership so STOP can remove cancelled audio.
        now = time.monotonic()
        while self.playback and self.playback[0][2] <= now:
            self.playback.popleft()
        start = max(self.speaking_until, now)
        self.speaking_until = start + duration + .5
        self.playback.append((identifier, start, self.speaking_until))
        if len(self.playback) > 128:
            first, second = self.playback.popleft(), self.playback.popleft()
            self.playback.appendleft((None, first[1], second[2]))

    def synthesize(self, request, identifier=None):
        gate = speech_gate.snapshot(self.path)
        def silence():
            output = io.BytesIO()
            with wave.open(output, 'wb') as sound:
                sound.setparams((1, 2, request.get('sample_rate', 22050), 0, 'NONE', ''))
                sound.writeframes(b'\0\0' * 220)
            return output.getvalue()
        if gate[0]:
            return silence()
        # Three synthesis callers maximum leave a WSGI thread for cancellation
        # and health. One worker/model is shared; waiting is bounded and cancellable.
        if not self.slots.acquire(False):
            raise BlockingIOError('Piper queue is full')
        cancelled = threading.Event()
        acquired = False
        audio_duration = 0
        try:
            with self.control_lock:
                if identifier and (identifier in self.waiters or identifier == self.active_request):
                    raise ValueError('Duplicate active request id')
                if identifier:
                    self.waiters[identifier] = cancelled
            deadline = time.monotonic() + 10
            while not acquired:
                if cancelled.is_set():
                    raise InterruptedError('Queued speech cancelled')
                acquired = self.lock.acquire(timeout=.05)
                if not acquired and time.monotonic() >= deadline:
                    raise BlockingIOError('Piper queue timed out')
            with self.control_lock:
                if identifier:
                    self.waiters.pop(identifier, None)
                self.active_request = identifier
                self.cancelled = cancelled
                self.processing = True
            if cancelled.is_set():
                raise InterruptedError('Speech cancelled')
            if speech_gate.suppressed(self.path, gate):
                return silence()
            config = settings.load(self.path)
            self.select(self.choose(request, config), config, self.cancelled)
            options = {'text': request['text'], 'length_scale': request.get('length_scale', 1) / config['speed'],
                       'volume': config['volume'] * request.get('volume', 1), 'noise_scale': config['noise_scale'],
                       'noise_w_scale': config['noise_w_scale']}
            audio = self.synth.synthesize(options, self.cancelled)
            rate = request.get('sample_rate', self.synth.rate)
            audio = resample(audio, rate)
            if speech_gate.suppressed(self.path, gate):
                return silence()
            with wave.open(io.BytesIO(audio), 'rb') as wav:
                audio_duration = wav.getnframes() / wav.getframerate()
            return audio
        finally:
            with self.control_lock:
                if identifier and self.waiters.get(identifier) is cancelled:
                    self.waiters.pop(identifier)
                if acquired:
                    self.active_request = None
                    self.processing = False
                    if audio_duration and not cancelled.is_set():
                        self.record_playback(identifier, audio_duration)
            if acquired:
                self.last_activity = time.monotonic()
                self.lock.release()
            self.slots.release()


def application(router, instance, control="", stopping=None):
    def app(env, respond):
        status, kind = '200 OK', 'application/json'
        try:
            if env['PATH_INFO'] == '/health' and env['REQUEST_METHOD'] == 'GET':
                ready = router.synth is not None and router.synth.process is not None and router.synth.process.is_alive()
                body = json.dumps({'service': 'akousousin-piper', 'instance': instance, 'ready': True, 'model_loaded': ready,
                                   'settings': str(router.path), 'voice': router.voice, 'speaking': router.speaking()}).encode()
            elif env['PATH_INFO'] == '/shutdown' and env['REQUEST_METHOD'] == 'POST':
                if not control or not hmac.compare_digest(env.get('HTTP_X_AKOUSOUSIN_CONTROL', ''), control):
                    status, body = '403 Forbidden', b'{"error":"Not owned by this panel"}'
                else:
                    timer = threading.Timer(.5, stopping.set)
                    timer.daemon = True
                    timer.start()
                    body = b'{"stopping":true}'
            elif env['PATH_INFO'] == '/stop-speaking' and env['REQUEST_METHOD'] == 'POST':
                if not control or not hmac.compare_digest(env.get('HTTP_X_AKOUSOUSIN_CONTROL', ''), control):
                    status, body = '403 Forbidden', b'{"error":"Not owned by this panel"}'
                else:
                    router.stop_speaking()
                    body = b'{"stopped":true}'
            elif env['PATH_INFO'] == '/cancel' and env['REQUEST_METHOD'] == 'POST':
                cancelled = router.cancel(env.get('HTTP_X_AKOUSOUSIN_REQUEST', ''))
                status = '200 OK' if cancelled else '404 Not Found'
                body = json.dumps({'cancelled': cancelled}).encode()
            elif env['PATH_INFO'] == '/synthesize'  and env['REQUEST_METHOD'] == 'POST':
                size = int(env.get('CONTENT_LENGTH', '0'))
                if not 0 < size <= MAX_BODY:
                    raise ValueError('Request too large')
                request = json.loads(env['wsgi.input'].read(size))
                text, scale = request.get('text'), request.get('length_scale', 1)
                if not isinstance(text, str) or not text.strip() or len(text) > 16000:
                    raise ValueError('Invalid text')
                if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale):
                    raise ValueError('Invalid speed')
                if not .5 <= scale <= 2:
                    raise ValueError('Invalid speed')
                volume = request.get('volume', 1)
                if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not 0 <= volume <= 2:
                    raise ValueError('Invalid volume')
                rate = request.get('sample_rate', 22050)
                if not isinstance(rate, int) or not 8000 <= rate <= 192000:
                    raise ValueError('Invalid sample rate')
                if 'language' in request and not isinstance(request['language'], int):
                    raise ValueError('Invalid language')
                body, kind = router.synthesize(request, env.get('HTTP_X_AKOUSOUSIN_REQUEST')), 'audio/wav'
            else:
                status, body = '404 Not Found', b'{"error":"Not found"}'
        except (ValueError, TypeError, AttributeError) as error:
            logging.getLogger(__name__).warning('Rejected synthesis request: %s', error)
            status, body = '400 Bad Request', b'{"error":"Invalid request"}'
        except BlockingIOError:
            status, body = '503 Service Unavailable', b'{"error":"Piper is busy"}'
        except InterruptedError:
            status, body = '409 Conflict', b'{"error":"Speech cancelled"}'
        except TimeoutError:
            status, body = '504 Gateway Timeout', b'{"error":"Synthesis timed out"}'
        except Exception:
            logging.exception('Speech request failed')
            status, body = '503 Service Unavailable', b'{"error":"Voice unavailable"}'
        if not status.startswith('200') and env['PATH_INFO'] == '/synthesize':
            logging.getLogger(__name__).warning('Synthesis HTTP status: %s', status)
        respond(status, [('Content-Type', kind), ('Content-Length', str(len(body)))])
        return [body]
    return app


def serve(path, instance, control_file):
    from waitress import create_server, wasyncore
    router = Router(path)
    config = settings.load(path)
    stopping = threading.Event()
    control = Path(control_file).read_text() if control_file else ''
    server = None
    try:
        router.start()
        server = create_server(application(router, instance, control, stopping), host='127.0.0.1',
                               port=config['port'], threads=4, connection_limit=16, backlog=8,
                               channel_timeout=70, max_request_body_size=MAX_BODY)
        while not stopping.is_set():
            wasyncore.loop(timeout=.1, count=1, map=server._map)
            router.expire()
    finally:
        router.close()
        if server:
            for channel in list(server._map.values()):
                channel.close()
            server.task_dispatcher.shutdown(timeout=5)
