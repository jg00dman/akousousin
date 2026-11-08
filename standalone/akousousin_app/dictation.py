# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Controller-owned recognition. No GUI, keyboard or heavyweight inference on import."""
import queue
import threading
import io
import wave
import time
import logging
import json

from . import settings, speech_gate

_TIMINGS = logging.getLogger('akousousin.dictation.timings')
if not _TIMINGS.handlers:
    _TIMINGS.addHandler(logging.StreamHandler())
_TIMINGS.setLevel(logging.INFO)
_TIMINGS.propagate = False


def log_timings(record):
    # Numbers and outcome only; dictated text is never written to the log.
    _TIMINGS.info('Dictation phrase=%s output=%s timings=%s', record['sequence'],
                  record['output'], json.dumps(record.get('timings', {}), sort_keys=True))


class Dictation:
    def __init__(self, path, speaking=lambda: False, recognizer_factory=None, capture_factory=None):
        self.path = path
        self.speaking = speaking
        self.recognizer_factory = recognizer_factory
        self.capture_factory = capture_factory
        self.recognizer = None
        self.capture = None
        self.thread = None
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.finished = threading.Event()
        self.insertion_cancelled = threading.Event()
        self.state = 'Not loaded'
        self.phase = 'unloaded'
        self.sequence = 0
        self.results = []
        self.last_activity = time.monotonic()
        self.insert = None
        self.enabled = False
        self.closed = False
        self.unloading = False

    def status(self):
        with self.lock:
            return {'enabled': self.enabled, 'state': self.state, 'phase': self.phase,
                    'busy': self.thread is not None and self.thread.is_alive(),
                    'loaded': self.recognizer is not None and self.recognizer.process is not None and self.recognizer.process.is_alive(),
                    'sequence': self.sequence, 'results': [dict(item) for item in self.results]}

    def change(self, state, phase=None):
        with self.lock:
            self.state = state
            if phase:
                self.phase = phase

    def prepare(self):
        self._launch(False, None)
        return self.status()

    def start(self, target=None, seconds=None):
        self._launch(True, target, seconds)
        return self.status()

    def _launch(self, record, target, seconds=None):
        with self.lock:
            if self.closed or self.unloading:
                raise RuntimeError('Dictation is closed')
            if self.thread is not None and self.thread.is_alive():
                raise BlockingIOError('Dictation is already active')
            self.cancelled = threading.Event()
            self.finished = threading.Event()
            self.insertion_cancelled = threading.Event()
            config = settings.load(self.path)
            self.enabled = True
            self.change('Loading model…', 'loading')
            self.thread = threading.Thread(target=self._run, args=(record, target, seconds, config), daemon=True)
            self.thread.start()

    def _ready(self, config):
        from akousousin_backend import models
        from akousousin_backend.recognition import Recognizer
        model = config['stt_model']
        if model.endswith('.en') and config['stt_language'] != 'en':
            raise ValueError('English-only models require English; select Base or Small for other languages or auto detection')
        missing = not models.installed(model) and not (model == 'turbo' and models.installed('small'))
        if self.recognizer and self.recognizer.model['model'] != model:
            self.recognizer.close()
            self.recognizer = None
        if self.recognizer is None:
            self.recognizer = (self.recognizer_factory or Recognizer)(model=model)
        threads = config.get('stt_cpu_threads')
        if threads is not None and self.recognizer.model.get('cpu_threads') != threads:
            self.recognizer.close()
            self.recognizer.model['cpu_threads'] = threads
        if self.recognizer.process is None or not self.recognizer.process.is_alive():
            self.recognizer.model['download_missing'] = missing
            if missing:
                self.change('Downloading ' + model + ', then loading…', 'loading')
                self.recognizer.startup_timeout = 900
            if not missing:
                self.change('Preparing recognition — please wait for Ready', 'loading')
            self.recognizer.start(self.cancelled)
            self.recognizer.model['download_missing'] = False
        if self.cancelled.is_set():
            raise InterruptedError('Dictation cancelled')
        warning = self.recognizer.status.get('fallback')
        self.change('Ready — ' + self.recognizer.status['model'].title() + ' loaded' + (' · ' + warning if warning else ''), 'ready')

    def capture_changed(self, text):
        with self.lock:
            if self.phase != 'error' and not self.cancelled.is_set():
                if self.finished.is_set() and self.insertion_cancelled.is_set():
                    return
                self.change(text, 'transcribing' if text.startswith('Recording stopped:') else 'listening')

    def store_result(self, result, outcome, error=None):
        with self.lock:
            self.sequence += 1
            record = dict(result, text=result['text'][:4000], sequence=self.sequence,
                          output=outcome, error=error)
            self.results.append(record)
            self.results = self.results[-200:]
            self.trim_history()
            if outcome in ('displayed', 'retained'):
                log_timings(record)
            return record

    def trim_history(self):
        # Leave room for status metadata inside the existing 1 MiB IPC limit.
        while len(json.dumps(self.results).encode('utf-8')) > 512 * 1024:
            self.results.pop(0)

    def update_result(self, record, **values):
        with self.lock:
            record.update(values)
            self.trim_history()
            self.sequence += 1
            if values.get('output') in ('inserted', 'retained', 'cancelled'):
                log_timings(record)

    def _run(self, record, target, seconds, config):
        timer = None
        pending = None
        mute = None
        insertion = None
        insertion_cancelled = self.insertion_cancelled
        session_language = config['stt_language'] or None
        deferred = target is not None and config.get('stt_mode', 'toggle') == 'push-to-talk'
        try:
            from akousousin_backend.audio_input import Capture
            from akousousin_backend.recognition import ready_cue
            self._ready(config)
            if not record or self.finished.is_set():
                return
            if target is not None and not deferred:
                from .insertion import InsertionQueue
                def completed(item, outcome, error, timings):
                    self.update_result(item, output=outcome, error=error,
                                       timings={**item.get('timings', {}), **timings})
                    if error and not insertion_cancelled.is_set() and insertion_cancelled is self.insertion_cancelled and self.capture:
                        self.capture.cancel()
                def insert(text, destination, cancelled):
                    if self.insert is None:
                        raise RuntimeError('Keyboard session is unavailable')
                    return self.insert(text, destination, cancelled)
                insertion = InsertionQueue(insert, insertion_cancelled, completed)
            mute = speech_gate.Lease(self.path)
            mute.acquire()
            self.change('Opening microphone…', 'opening')
            self.capture = (self.capture_factory or Capture)(
                source=config['stt_source'] or None, cue=ready_cue if config['stt_beep'] else None,
                paused=lambda: False, changed=self.capture_changed,
                threshold=config.get('stt_threshold', 250), ended=mute.close)
            self.capture.start()
            while True:
                if insertion and insertion.error:
                    raise RuntimeError(insertion.error + ' — transcript retained in Voice Input')
                if seconds and timer is None and self.capture.ready.is_set():
                    timer = threading.Timer(seconds, self.finish)
                    timer.daemon = True
                    timer.start()
                if self.cancelled.is_set():
                    raise InterruptedError('Dictation cancelled')
                if self.finished.is_set():
                    self.capture.finish()
                try:
                    audio = self.capture.segments.get(timeout=.05)
                except queue.Empty:
                    if self.capture.done.is_set():
                        if self.capture.error:
                            raise RuntimeError(self.capture.error)
                        break
                    continue
                self.change('Listening — transcribing previous phrase' if not self.capture.done.is_set()
                            else 'Transcribing…', 'listening' if not self.capture.done.is_set() else 'transcribing')
                began = time.monotonic()
                queued = getattr(self.capture, 'queued_at', {}).pop(id(audio), began)
                with wave.open(io.BytesIO(audio), 'rb') as sound:
                    audio_seconds = sound.getnframes() / sound.getframerate()
                result = self.recognizer.transcribe(audio, session_language, self.cancelled, endpointed=True)
                if not config['stt_language'] and result.get('text') and result.get('language'):
                    if session_language:
                        result['language_source'] = 'session'
                    else:
                        session_language = result['language']
                endpoint = getattr(self.capture, 'segment_info', {}).pop(id(audio), {})
                speech_ended_at = endpoint.pop('speech_ended_at', None)
                result['timings'] = {**endpoint, 'audio_seconds': round(audio_seconds, 3),
                                     'queue_seconds': round(max(0, began - queued), 3),
                                     'recognition_seconds': round(time.monotonic() - began, 3)}
                if speech_ended_at is not None:
                    result['timings']['speech_end_to_recognition_seconds'] = round(max(0, time.monotonic() - speech_ended_at), 3)
                if self.cancelled.is_set():
                    raise InterruptedError('Dictation cancelled')
                if not result['text']:
                    continue
                if deferred:
                    text = (pending['text'] + ' ' if pending else '') + result['text']
                    if len(text) > 4000:
                        self.capture.cancel()
                        raise RuntimeError('Push-to-talk text limit reached; transcript retained. Use shorter recordings.')
                    if pending is None:
                        pending = self.store_result(result, 'pending')
                    else:
                        language = pending['language'] if pending['language'] == result['language'] else None
                        self.update_result(pending, text=text, language=language, timings={
                            key: round(pending.get('timings', {}).get(key, 0) + value, 3)
                            for key, value in result['timings'].items()})
                    self.last_activity = time.monotonic()
                    continue
                if insertion and insertion_cancelled.is_set():
                    self.store_result(result, 'retained', 'Dictation stopped before insertion')
                elif insertion:
                    item = self.store_result(result, 'queued')
                    try:
                        insertion.submit(item, result['text'], target, speech_ended_at=speech_ended_at)
                    except InterruptedError:
                        self.update_result(item, output='retained', error='Dictation stopped before insertion')
                    except Exception as failure:
                        self.update_result(item, output='retained', error=str(failure))
                        raise
                else:
                    self.store_result(result, 'displayed')
                self.last_activity = time.monotonic()
            if self.cancelled.is_set():
                raise InterruptedError('Dictation cancelled')
            if pending is not None:
                if not self.finished.is_set():
                    raise RuntimeError('Push-to-talk capture ended before key release')
                if self.insert is None:
                    raise RuntimeError('Keyboard session is unavailable')
                self.change('Inserting transcript…', 'transcribing')
                insertion_started = time.monotonic()
                self.insert(pending['text'], target, self.cancelled)
                timings = dict(pending.get('timings', {}))
                timings['insertion_seconds'] = round(time.monotonic() - insertion_started, 3)
                self.update_result(pending, timings=timings)
                self.update_result(pending, output='inserted')
            if insertion:
                insertion.finish()
                if insertion.error:
                    raise RuntimeError(insertion.error + ' — transcript retained in Voice Input')
            self.change('Ready — recording stopped', 'ready')
        except InterruptedError:
            if pending is not None:
                self.update_result(pending, output='cancelled')
            self.change('Cancelled', 'ready' if self.recognizer and self.recognizer.process else 'unloaded')
        except Exception as error:
            message = str(error)
            if pending is not None:
                self.update_result(pending, output='retained', error=message)
                if 'retained' not in message:
                    message += ' — transcript retained in Voice Input'
            self.change(message, 'error')
        finally:
            if timer:
                timer.cancel()
            insertion_cancelled.set()
            try:
                if self.capture:
                    self.capture.close()
                    self.capture = None
            finally:
                try:
                    if insertion:
                        insertion.finish()
                finally:
                    if mute:
                        mute.close()
            self.last_activity = time.monotonic()

    def finish(self, cancel_insertion=False):
        if cancel_insertion:
            self.insertion_cancelled.set()
            self.change('Recording stopped — remaining speech will only appear in the transcript', 'transcribing')
        if self.phase == 'loading':
            self.cancelled.set()
        self.finished.set()
        if self.capture:
            self.capture.finish()

    def cancel(self):
        self.insertion_cancelled.set()
        self.cancelled.set()
        self.finished.set()
        if self.capture:
            self.capture.cancel()

    def unload(self, only_if_idle=False):
        with self.lock:
            if self.unloading or (only_if_idle and self.status()['busy']):
                return
            if not only_if_idle:
                self.enabled = False
            self.unloading = True
            self.cancel()
            thread = self.thread
        try:
            if thread:
                thread.join(10)
                if thread.is_alive():
                    raise TimeoutError('Dictation is still stopping')
            if self.recognizer:
                self.recognizer.close()
                self.recognizer = None
            self.change('Model unloaded; downloaded files retained', 'unloaded')
        finally:
            with self.lock:
                self.unloading = False

    def expire(self):
        config = settings.load(self.path)
        if self.enabled and config.get('stt_keep_loaded', True):
            return
        timeout = config.get('stt_idle_timeout', 3600)
        if timeout and self.recognizer and not self.status()['busy'] and time.monotonic() - self.last_activity >= timeout:
            self.unload(only_if_idle=True)

    def close(self):
        self.closed = True
        try:
            self.unload()
        finally:
            if self.capture:
                self.capture.close()
            if self.recognizer:
                self.recognizer.close()
