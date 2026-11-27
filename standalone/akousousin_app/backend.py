# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The voice service: speaks text, SSML or SAPI fragments as a stream of audio with word, sentence and mark events.

One request speaks at a time and the newest takes precedence: a new request
stops the one in progress, whose stream ends "interrupted". The main voice
follows the "keep loaded" setting; a voice for another language, loaded when
some text needs it, stays while it is in use and unloads after five minutes
unused. See design/speech-timeline.md in the project.
"""
import io
import json
import logging
import math
import os
import hmac
from collections import deque
from pathlib import Path
import threading
import time
import wave

from akousousin_backend.server import MAX_AUDIO, MAX_BODY
from . import settings, speech_gate, speech_input, speech_stream
from .voice_process import VoiceProcess
from .waiting import Interrupt as _Interrupt


def Interrupt():
    """A cancel signal a thread can sleep on; a plain event on Windows, whose waits can't use POSIX pipes."""
    return threading.Event() if os.name == 'nt' else _Interrupt()

SECOND_VOICE_IDLE = 300     # seconds a second-language voice stays loaded unused
QUEUE_WAIT = 10             # seconds a request waits for the one it interrupted to stop
EVENT_NAMES = ('word', 'sentence', 'mark')


class Resampler:
    """Converts a stream of 16-bit mono audio between rates, block by block, with no click at block joins."""
    def __init__(self, source, target):
        self.source, self.target = source, target
        self.ratio = source / target
        self.phase = 0.0   # where the next output sample falls, in source samples from the start of the pending data
        self.tail = None   # the last source sample of the previous block

    def __call__(self, pcm):
        if self.source == self.target or not pcm:
            return pcm
        import numpy as np
        data = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        if self.tail is not None:
            data = np.concatenate([self.tail, data])
        last = len(data) - 1
        positions = np.arange(self.phase, last, self.ratio) if last > self.phase else np.zeros(0)
        out = np.interp(positions, np.arange(len(data)), data) if len(positions) else np.zeros(0)
        self.phase = (positions[-1] + self.ratio - last) if len(positions) else self.phase - last
        self.tail = data[-1:]
        return np.clip(np.round(out), -32768, 32767).astype(np.int16).tobytes()


def resample(audio, target):
    """A whole WAV file at another rate."""
    with wave.open(io.BytesIO(audio), 'rb') as wav:
        rate = wav.getframerate()
        if rate == target:
            return audio
        pcm = Resampler(rate, target)(wav.readframes(wav.getnframes()))
    return wav_bytes(pcm, target)


def wav_bytes(pcm, rate):
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setparams((1, 2, rate, 0, 'NONE', ''))
        wav.writeframes(pcm)
    return output.getvalue()


class Router:
    def __init__(self, path, target=None):
        self.path = Path(path).resolve()
        self.target = target
        self.voices = {}            # voice key -> VoiceProcess, at most two
        self.voice = None           # the main voice's key
        self.second = None          # a second-language voice's key
        self.second_used = 0
        self.lock = threading.RLock()
        self.last_activity = time.monotonic()
        self.active_request = None
        self.cancelled = Interrupt()
        self.control_lock = threading.Lock()
        self.waiters = {}
        self.slots = threading.BoundedSemaphore(3)
        self.speaking_until = 0
        self.playback = deque()
        self.processing = False
        self.settings_stamp = None
        self.cached_timeout = 0

    @property
    def synth(self):
        """The main voice's process, if loaded."""
        return self.voices.get(self.voice)

    def announce(self):
        """Tell the controller speech has begun, so its tray shows it without asking repeatedly.

        Not on Windows, where calling the controller needs Qt, which this
        service does not run; the Windows tray still checks on a timer.
        """
        if os.name == 'nt':
            return
        def tell():
            from . import runtime
            try:
                runtime.call(self.path, {'command': 'activity'}, launch=False, timeout=2)
            except (OSError, RuntimeError, ValueError):
                pass
        threading.Thread(target=tell, daemon=True).start()

    def speaking(self):
        if speech_gate.snapshot(self.path)[0]:
            return False
        with self.control_lock:
            return self.processing or time.monotonic() < self.speaking_until

    def idle_timeout(self):
        """The unload delay, reread only when the settings file has changed."""
        stamp = settings.stamp(self.path)
        if stamp != self.settings_stamp:
            self.settings_stamp = stamp
            self.cached_timeout = settings.load(self.path)['idle_timeout']
        return self.cached_timeout

    def until_expiry(self, now=None):
        """Seconds until a loaded voice should unload, or None if they all stay loaded."""
        current = time.monotonic() if now is None else now
        due = []
        timeout = self.idle_timeout()
        if self.voices and timeout:
            due.append(self.last_activity + timeout - current)
        if self.second in self.voices:
            due.append(self.second_used + SECOND_VOICE_IDLE - current)
        return max(0, min(due)) if due else None

    def expire(self, now=None):
        # Do not take the synthesis lock on every event-loop tick: dispatching
        # a new HTTP request and idle maintenance happen together, and that can
        # otherwise report a ready backend as busy. Recheck after taking it.
        current = time.monotonic() if now is None else now
        timeout = self.idle_timeout()
        idle = bool(self.voices) and timeout and current - self.last_activity >= timeout
        second = self.second in self.voices and current - self.second_used >= SECOND_VOICE_IDLE
        if not idle and not second:
            return False
        if not self.lock.acquire(False):
            return False
        try:
            if self.voices and timeout and current - self.last_activity >= timeout:
                self.close()
                return True
            if self.second in self.voices and current - self.second_used >= SECOND_VOICE_IDLE:
                self.unload(self.second)
                self.second = None
                return True
            return False
        finally:
            self.lock.release()

    def choose(self, request, config):
        if request.get('preview_voice') is True and request.get('voice') in config['voices']:
            return request['voice']
        language = config['book_language'] or settings.language_for_lcid(request.get('language', 0))
        selected = config['language_voices'].get(language) if language else None
        return settings.usable_voice(config, selected, request.get('voice'), language=language or '') or config['voice']

    def for_language(self, language, fallback, config):
        """The voice for a run marked as another language; the request's voice if none suits it."""
        if not language:
            return fallback
        return settings.usable_voice(config, config['language_voices'].get(language), language=language) or fallback

    def start(self):
        config = settings.load(self.path)
        self.load(config['voice'], config)
        self.last_activity = time.monotonic()

    def load(self, key, config, cancelled=None):
        """The process for a voice, loading it if needed: the main voice or, for any other, the second slot."""
        if key not in config['voices']:
            raise RuntimeError('Selected voice is not installed')
        model = Path(config['voices'][key]['path'])
        if not model.is_file() or not Path(str(model) + '.json').is_file():
            raise RuntimeError('Voice model/configuration is missing')
        main = config['voice']
        if self.second == main:
            self.second = None   # the second voice became the main one
        if self.voice != main:
            # The user chose another main voice: it takes the main slot.
            if self.voice is not None and self.voice != self.second:
                self.unload(self.voice)
            self.voice = main
        if key != main and key != self.second:
            if self.second is not None:
                self.unload(self.second)   # a third language replaces the second
            self.second = key
        if key == self.second:
            self.second_used = time.monotonic()
        process = self.voices.get(key)
        if process is None or not process.alive():
            from .voice_timing import ensure_timed
            ensure_timed(model, settings.data_path())   # once per voice; voices elsewhere stay untimed
            process = VoiceProcess(model, **({'target': self.target} if self.target else {}))
            process.start(cancelled)
            self.voices[key] = process
        return process

    # Kept for callers that preload the main voice.
    def select(self, selected, config, cancelled=None):
        return self.load(selected, config, cancelled)

    def unload(self, key):
        process = self.voices.pop(key, None)
        if process is not None:
            process.close()

    def close(self):
        acquired = self.lock.acquire(timeout=.5)
        if not acquired:
            for process in list(self.voices.values()):
                try:
                    if process.process:
                        process.process.terminate()
                except (ValueError, OSError):
                    pass
            acquired = self.lock.acquire(timeout=4)
        if not acquired:
            return
        try:
            for key in list(self.voices):
                self.unload(key)
            self.voice = self.second = None
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

    def speech(self, request, identifier=None):
        """Speak a request: yields ('info', dict), ('audio', pcm) and ('event', kind, start, end, name) in order.

        Ends normally when complete; raises InterruptedError when stopped by a
        cancel, a newer request or dictation. Audio is at the requested rate.
        """
        gate = speech_gate.snapshot(self.path)
        rate = request.get('sample_rate', 22050)
        wanted = {speech_stream.KINDS[name] for name in request.get('events', ()) if name in speech_stream.KINDS}
        items = speech_input.parse(request.get('input', request.get('text', '')), request.get('format', 'text'),
                                   request.get('input_language', ''))
        if gate[0]:
            yield ('info', {'rate': rate, 'events': []})
            yield ('audio', b'\0\0' * (rate // 100))   # dictation is listening: a moment of silence, not speech
            return
        # Three synthesis callers maximum leave a WSGI thread for cancellation
        # and health. A new request stops the one in progress and takes over.
        if not self.slots.acquire(False):
            raise BlockingIOError('Speech queue is full')
        cancelled = Interrupt()
        acquired = False
        heard, first_audio = 0.0, None   # seconds of audio sent, and when the first of it went
        try:
            with self.control_lock:
                if identifier and (identifier in self.waiters or identifier == self.active_request):
                    raise ValueError('Duplicate active request id')
                if identifier:
                    self.waiters[identifier] = cancelled
                self.cancelled.set()   # the newest request takes precedence
                for waiting in self.waiters.values():
                    if waiting is not cancelled:
                        waiting.set()
            deadline = time.monotonic() + QUEUE_WAIT
            while not acquired:
                if cancelled.is_set():
                    raise InterruptedError('Queued speech cancelled')
                acquired = self.lock.acquire(timeout=.05)
                if not acquired and time.monotonic() >= deadline:
                    raise BlockingIOError('The previous speech did not stop')
            with self.control_lock:
                if identifier:
                    self.waiters.pop(identifier, None)
                self.active_request = identifier
                self.cancelled = cancelled
                quiet = not self.processing and time.monotonic() >= self.speaking_until
                self.processing = True
            if quiet:
                self.announce()
            if cancelled.is_set():
                raise InterruptedError('Speech cancelled')
            config = settings.load(self.path)
            chosen = self.choose(request, config)
            main = self.load(chosen, config, cancelled)
            yield ('info', {'rate': rate, 'voice': chosen,
                            'events': sorted(name for name in EVENT_NAMES if speech_stream.KINDS[name] in wanted
                                             and (name != 'word' or main.timed))})
            for item in items:
                if isinstance(item, speech_input.Pause):
                    pieces = [('audio', b'\0\0' * (rate * item.milliseconds // 1000))]
                else:
                    key = self.for_language(item.language, chosen, config)
                    pieces = self.run(item, key, config, request, rate, wanted, cancelled, gate)
                for piece in pieces:
                    if piece[0] == 'audio':
                        heard += len(piece[1]) / 2 / rate
                        first_audio = first_audio or time.monotonic()
                    yield piece
        finally:
            with self.control_lock:
                if identifier and self.waiters.get(identifier) is cancelled:
                    self.waiters.pop(identifier)
                if acquired:
                    self.active_request = None
                    self.processing = False
                    if heard and not cancelled.is_set():
                        # A streaming reader has played what arrived early; only the rest is still to come.
                        unplayed = heard - (time.monotonic() - first_audio)
                        if unplayed > 0:
                            self.record_playback(identifier, unplayed)
            if acquired:
                self.last_activity = time.monotonic()
                self.lock.release()
            self.slots.release()

    def run(self, item, key, config, request, rate, wanted, cancelled, gate):
        """One run of text: its audio, split where its events fall, and the events."""
        marks = list(item.marks)
        def due_marks(before):
            while marks and (before is None or marks[0][0] <= before):
                index, name = marks.pop(0)
                if speech_stream.MARK in wanted:
                    start, _ = item.source(index, index + 1) if index < len(item.text) else (item.ends[-1] if item.ends else 0, 0)
                    yield ('event', speech_stream.MARK, start, start, name)
        if not item.text.strip():
            yield from due_marks(None)
            return
        voice = self.load(key, config, cancelled)
        resampler = Resampler(voice.rate, rate)
        options = {'text': item.text, 'events': bool(wanted),
                   'length_scale': max(.1, min(10, request.get('length_scale', 1) / config['speed'] / item.rate)),
                   'volume': config['volume'] * request.get('volume', 1) * item.volume,
                   'noise_scale': config['noise_scale'], 'noise_w_scale': config['noise_w_scale']}
        for pcm, described in voice.speak(options, cancelled):
            if speech_gate.suppressed(self.path, gate):
                cancelled.set()   # dictation started: stop speaking
                raise InterruptedError('Dictation started')
            if key == self.second:
                self.second_used = time.monotonic()
            cuts = []   # (sample, events) in order
            if described.get('sentence') and speech_stream.SENTENCE in wanted and described.get('sentence_range'):
                start, end = item.source(*described['sentence_range'])
                cuts.append((0, ('event', speech_stream.SENTENCE, start, end, '')))
            words = described.get('words') or []
            if words:
                for first, last, sample, _ in words:
                    for mark in due_marks(first):
                        cuts.append((sample, mark))
                    if speech_stream.WORD in wanted:
                        start, end = item.source(first, last)
                        cuts.append((sample, ('event', speech_stream.WORD, start, end, '')))
            elif described.get('covers'):
                for mark in due_marks(described['covers'][0]):   # untimed voice: marks at the chunk's start
                    cuts.append((0, mark))
            position = 0
            for sample, event in cuts:
                sample = max(position, min(sample, len(pcm) // 2))
                if sample > position:
                    yield ('audio', resampler(pcm[position * 2:sample * 2]))
                    position = sample
                yield event
            if position * 2 < len(pcm):
                yield ('audio', resampler(pcm[position * 2:]))
            if not words and described.get('covers'):
                for mark in due_marks(described['covers'][1] - 1):
                    yield mark
        yield from due_marks(None)

    def synthesize(self, request, identifier=None):
        """A whole request as one WAV file: the earlier interface, made from the same speech."""
        rate = request.get('sample_rate', 22050)
        audio = bytearray()
        for piece in self.speech(dict(request, events=()), identifier):
            if piece[0] == 'info':
                rate = piece[1]['rate']
            elif piece[0] == 'audio':
                audio += piece[1]
                if len(audio) > MAX_AUDIO:
                    raise ValueError('Audio exceeds limit')
        return wav_bytes(bytes(audio or b'\0\0' * 220), rate)


def validate(request, streaming):
    """Check a synthesis request's fields, raising ValueError for anything out of range."""
    if streaming:
        kind = request.get('format', 'text')
        if kind not in ('text', 'ssml', 'fragments'):
            raise ValueError('Invalid format')
        content = request.get('input')
        if kind == 'fragments' and not isinstance(content, list) or kind != 'fragments' and not isinstance(content, str):
            raise ValueError('Invalid input')
        events = request.get('events', [])
        if not isinstance(events, list) or any(name not in EVENT_NAMES for name in events):
            raise ValueError('Invalid events')
    else:
        text = request.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > 16000:
            raise ValueError('Invalid text')
    scale = request.get('length_scale', 1)
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale):
        raise ValueError('Invalid speed')
    if not .5 <= scale <= 2:
        raise ValueError('Invalid speed')
    volume = request.get('volume', 1)
    if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not 0 <= volume <= 2:
        raise ValueError('Invalid volume')
    rate = request.get('sample_rate', 22050)
    if isinstance(rate, bool) or not isinstance(rate, int) or not 8000 <= rate <= 192000:
        raise ValueError('Invalid sample rate')
    if 'language' in request and (isinstance(request['language'], bool) or not isinstance(request['language'], int)):
        raise ValueError('Invalid language')


def stream_frames(router, request, identifier):
    """The /speak response body: the speech as frames, ending with an end frame whatever happens."""
    yield speech_stream.HEADER
    try:
        for piece in router.speech(request, identifier):
            if piece[0] == 'audio':
                if piece[1]:
                    yield speech_stream.audio(piece[1])
            elif piece[0] == 'event':
                yield speech_stream.event(*piece[1:])
            else:
                yield speech_stream.info(piece[1])
        yield speech_stream.end(speech_stream.COMPLETE)
    except InterruptedError:
        yield speech_stream.end(speech_stream.INTERRUPTED)
    except (ValueError, TypeError) as error:
        logging.getLogger(__name__).warning('Rejected speech: %s', error)
        yield speech_stream.end(speech_stream.FAILED, 'Invalid request')
    except BlockingIOError:
        yield speech_stream.end(speech_stream.FAILED, 'Busy')
    except Exception:
        logging.exception('Speech failed')
        yield speech_stream.end(speech_stream.FAILED, 'Voice unavailable')


def application(router, instance, control="", stopping=None):
    def app(env, respond):
        status, kind = '200 OK', 'application/json'
        try:
            if env['PATH_INFO'] == '/health' and env['REQUEST_METHOD'] == 'GET':
                process = router.synth
                ready = process is not None and process.alive()
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
            elif env['PATH_INFO'] == '/cancel' and env['REQUEST_METHOD'] == 'POST':
                cancelled = router.cancel(env.get('HTTP_X_AKOUSOUSIN_REQUEST', ''))
                status = '200 OK' if cancelled else '404 Not Found'
                body = json.dumps({'cancelled': cancelled}).encode()
            elif env['PATH_INFO'] in ('/synthesize', '/speak') and env['REQUEST_METHOD'] == 'POST':
                size = int(env.get('CONTENT_LENGTH', '0'))
                limit = MAX_BODY if env['PATH_INFO'] == '/synthesize' else 4 * MAX_BODY + speech_input.LONGEST_INPUT * 4
                if not 0 < size <= limit:
                    raise ValueError('Request too large')
                request = json.loads(env['wsgi.input'].read(size))
                if not isinstance(request, dict):
                    raise ValueError('Invalid request')
                streaming = env['PATH_INFO'] == '/speak'
                validate(request, streaming)
                if streaming:
                    # The body streams as speech is made; the connection's end closes it.
                    respond('200 OK', [('Content-Type', 'application/x-akousousin-speech')])
                    return stream_frames(router, request, env.get('HTTP_X_AKOUSOUSIN_REQUEST'))
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


class Stopping(threading.Event):
    """Stop request that also wakes the server loop, which otherwise sleeps until it has work."""
    wake = None

    def set(self):
        super().set()
        if self.wake:
            self.wake()


# The loop sleeps until a request arrives, the voice is due to unload, or the
# owner exits; this only bounds a missed wake-up.
LONGEST_SLEEP = 300


def watch_owner(stopping, wasyncore, server_map):
    """Wake the loop when the Akousousin that started this service exits.

    Returns False where the kernel cannot report it, so the caller checks instead."""
    from .runtime import owner_gone
    owner = os.environ.get('AKOUSOUSIN_OWNER_PID', '')
    if not owner.isdigit() or not hasattr(os, 'pidfd_open'):
        return not owner.isdigit()
    if owner_gone():
        stopping.set()
        return True
    try:
        descriptor = os.pidfd_open(int(owner))
    except OSError:
        return False

    class Owner(wasyncore.file_dispatcher):
        def writable(self):
            return False

        def handle_read(self):
            logging.getLogger(__name__).warning('Akousousin exited; stopping the voice service')
            self.close()
            stopping.set()

    Owner(descriptor, map=server_map)
    os.close(descriptor)  # file_dispatcher keeps its own duplicate
    return True


def serve(path, instance, control_file):
    from waitress import create_server, wasyncore
    router = Router(path)
    config = settings.load(path)
    stopping = Stopping()
    control = Path(control_file).read_text() if control_file else ''
    server = None
    try:
        router.start()
        server = create_server(application(router, instance, control, stopping), host='127.0.0.1',
                               port=config['port'], threads=4, connection_limit=16, backlog=8,
                               channel_timeout=70, max_request_body_size=4 * MAX_BODY + speech_input.LONGEST_INPUT * 4,
                               # A streaming response waits for its reader instead of buffering
                               # audio, so synthesis keeps just ahead of playback.
                               outbuf_high_watermark=256 * 1024)
        from .runtime import owner_gone
        stopping.wake = server.trigger.pull_trigger
        watched = watch_owner(stopping, wasyncore, server._map)
        while not stopping.is_set():
            due = router.until_expiry()
            # Windows keeps the earlier short wait until its idle behaviour has been tested there.
            longest = .1 if os.name == 'nt' else LONGEST_SLEEP if watched else 1
            wasyncore.loop(timeout=longest if due is None else min(longest, due + .05), count=1, map=server._map)
            router.expire()
            if not watched and owner_gone():
                logging.getLogger(__name__).warning('Akousousin exited; stopping the voice service')
                break
    finally:
        router.close()
        if server:
            for channel in list(server._map.values()):
                channel.close()
            server.task_dispatcher.shutdown(timeout=5)
