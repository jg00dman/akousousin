# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Actions shared by more than one page: voice previews and dictation tests.

Home, Voices and Dictation all offer "try it" controls. They share these
objects so a preview started on one page can be stopped from another, and
the logic lives in one place.
"""
import importlib.util
import os
import threading

from PySide6.QtCore import QObject, Signal

from .. import voice_preview


class Preview(QObject):
    """Speak sample text with one voice; at most one preview plays at a time."""
    changed = Signal(bool)          # playing

    def __init__(self, state, tasks):
        super().__init__()
        self.state, self.tasks = state, tasks
        self.stop_event = threading.Event()
        self.playing = False

    def toggle(self, voice, text, sample=None, failed=None):
        if self.playing:
            self.stop()
            return
        if not text.strip() and not sample:
            self.state.notice.emit(self.tr('Type some text to hear first.'))
            return
        self.stop_event = threading.Event()
        stop = self.stop_event
        self.playing = True
        self.changed.emit(True)

        def done(played):
            self._finish()
            self.state.notice.emit(self.tr('Finished speaking.') if played else self.tr('Stopped.'))

        def problem(error):
            self._finish()
            (failed or self.tasks.failed.emit)(error)

        self.tasks.run(lambda: voice_preview.play(self.state.path, text, voice, sample, stop), done,
                       failed=problem, key='preview')

    def stop(self):
        self.stop_event.set()

    def _finish(self):
        self.playing = False
        self.changed.emit(False)


class DictationTest(QObject):
    """A short recording that shows its transcript instead of typing it."""
    changed = Signal(bool)          # recording
    transcript = Signal(str)

    def __init__(self, state, tasks):
        super().__init__()
        self.state, self.tasks = state, tasks
        self.since = None
        self.recording = False
        self.supported = os.name != 'nt' and importlib.util.find_spec('faster_whisper') is not None
        state.status_changed.connect(self._status)

    def toggle(self):
        if self.recording:
            self.state.command('stt-finish')
            return
        if not self.supported:
            self.state.notice.emit(self.tr('Dictation is not available on Windows yet.') if os.name == 'nt'
                                   else self.tr('Dictation needs a Linux build with recognition.'))
            return

        def start():
            current = self.state.call('stt-status')
            if current.get('busy'):
                raise RuntimeError(self.tr('Finish the current dictation before starting a test.'))
            self.state.call('stt-start', seconds=10)
            return current.get('sequence', 0)

        def started(sequence):
            self.since = sequence
            self._set(True)
            self.transcript.emit('')
            self.state.notice.emit(self.tr('Listening — speak now. Press Finish when you are done.'))

        self.tasks.run(start, started, key='dictation-test')

    def _set(self, recording):
        if recording != self.recording:
            self.recording = recording
            self.changed.emit(recording)

    def _status(self, status):
        dictation = status.dictation or {}
        if self.since is None:
            return
        words = ' '.join(item['text'] for item in dictation.get('results', [])
                         if item.get('sequence', 0) > self.since and item.get('output') == 'displayed').strip()
        if words:
            self.transcript.emit(words)
        if self.recording and not dictation.get('busy'):
            self._set(False)
            if dictation.get('phase') == 'error':
                self.state.notice.emit(dictation.get('state', ''))
            elif not words:
                self.state.notice.emit(self.tr('Nothing was heard. Check the microphone on the Dictation page.'))
