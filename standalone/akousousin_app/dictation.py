# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Controller-owned recognition. No GUI, keyboard or heavyweight inference on import."""
import queue
import threading
import time

from . import settings


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
            config = settings.load(self.path)
            self.enabled = True
            self.change('Loading model…', 'loading')
            self.thread = threading.Thread(target=self._run, args=(record, target, seconds, config), daemon=True)
            self.thread.start()

    def _ready(self, config):
        from akousousin_backend import models
        from akousousin_backend.recognition import Recognizer
        model = config['stt_model']
        missing = not models.installed(model) and not (model == 'turbo' and models.installed('small'))
        if self.recognizer and self.recognizer.model['model'] != model:
            self.recognizer.close()
            self.recognizer = None
        if self.recognizer is None:
            self.recognizer = (self.recognizer_factory or Recognizer)(model=model)
        if self.recognizer.process is None or not self.recognizer.process.is_alive():
            self.recognizer.model['download_missing'] = missing
            if missing:
                self.change('Downloading Small (about 485 MB), then loading…', 'loading')
                self.recognizer.startup_timeout = 900
            self.recognizer.start(self.cancelled)
        if self.cancelled.is_set():
            raise InterruptedError('Dictation cancelled')
        warning = self.recognizer.status.get('fallback')
        self.change('Ready — ' + self.recognizer.status['model'].title() + ' loaded' + (' · ' + warning if warning else ''), 'ready')

    def capture_changed(self, text):
        with self.lock:
            if self.phase != 'error' and not self.cancelled.is_set():
                self.change(text, 'listening')

    def store_result(self, result, outcome, error=None):
        with self.lock:
            self.sequence += 1
            record = dict(result, text=result['text'][:4000], sequence=self.sequence,
                          output=outcome, error=error)
            self.results.append(record)
            self.results = self.results[-5:]
            return record

    def update_result(self, record, **values):
        with self.lock:
            record.update(values)
            self.sequence += 1

    def _run(self, record, target, seconds, config):
        timer = None
        pending = None
        deferred = target is not None and config.get('stt_mode', 'toggle') == 'push-to-talk'
        try:
            from akousousin_backend.audio_input import Capture
            from akousousin_backend.recognition import ready_cue
            self._ready(config)
            if not record or self.finished.is_set():
                return
            self.change('Opening microphone…', 'opening')
            self.capture = (self.capture_factory or Capture)(
                source=config['stt_source'] or None, cue=ready_cue if config['stt_beep'] else None,
                paused=self.speaking, changed=self.capture_changed,
                threshold=config.get('stt_threshold', 250))
            self.capture.start()
            while True:
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
                result = self.recognizer.transcribe(audio, config['stt_language'] or None, self.cancelled)
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
                        self.update_result(pending, text=text, language=language)
                    self.last_activity = time.monotonic()
                    continue
                outcome = 'displayed'
                error = None
                if target is not None:
                    try:
                        if self.insert is None:
                            raise RuntimeError('Keyboard session is unavailable')
                        self.insert(result['text'], target, self.cancelled)
                        outcome = 'inserted'
                    except Exception as failure:
                        outcome, error = 'retained', str(failure)
                self.store_result(result, outcome, error)
                if error:
                    self.capture.cancel()
                    raise RuntimeError(error + ' — transcript retained in Voice Input')
                self.last_activity = time.monotonic()
            if self.cancelled.is_set():
                raise InterruptedError('Dictation cancelled')
            if pending is not None:
                if not self.finished.is_set():
                    raise RuntimeError('Push-to-talk capture ended before key release')
                if self.insert is None:
                    raise RuntimeError('Keyboard session is unavailable')
                self.change('Inserting transcript…', 'transcribing')
                self.insert(pending['text'], target, self.cancelled)
                self.update_result(pending, output='inserted')
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
            if self.capture:
                self.capture.close()
                self.capture = None
            self.last_activity = time.monotonic()

    def finish(self):
        if self.phase == 'loading':
            self.cancelled.set()
        self.finished.set()
        if self.capture:
            self.capture.finish()

    def cancel(self):
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
        timeout = config.get('stt_idle_timeout', 300)
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
