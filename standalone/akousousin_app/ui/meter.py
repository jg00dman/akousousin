# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""A live microphone level for the Dictation page.

The microphone is open only while the Dictation page is on screen. Reading
runs on Qt's event loop through QProcess, so no thread is involved, and the
recorder is the same PipeWire or PulseAudio tool dictation uses.
"""
from array import array
import math
import os
import time

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import runtime
from . import theme


def loudness(pcm):
    """RMS of signed 16-bit PCM mapped from -60 dBFS..-10 dBFS onto 0..1."""
    samples = array('h', pcm[:len(pcm) - len(pcm) % 2])
    if not samples:
        return 0.0
    rms = math.sqrt(sum(value * value for value in samples) / len(samples))
    decibels = 20 * math.log10(max(rms, 1) / 32768)
    return min(1.0, max(0.0, (decibels + 60) / 50))


class LevelMonitor(QObject):
    level = Signal(float)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.source = None
        self.last_emit = 0.0

    @property
    def running(self):
        return self.process is not None

    def start(self, source=None):
        self.stop()
        from akousousin_backend.audio_system import AudioUnavailable, PcmStream, record_command
        try:
            command = record_command(source or None, 'Microphone level')
        except AudioUnavailable as error:
            self.failed.emit(str(error))
            return
        self.source = source
        self.stream = PcmStream()
        process = QProcess(self)
        environment = QProcessEnvironment()
        for name, value in runtime.host_environment().items():
            environment.insert(name, value)
        process.setProcessEnvironment(environment)
        process.setProcessChannelMode(QProcess.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read)
        process.errorOccurred.connect(lambda _error: self._ended())
        process.finished.connect(lambda *_: self._ended())
        self.process = process
        process.start(command[0], command[1:])

    def stop(self):
        process, self.process = self.process, None
        if process is None:
            return
        for signal in (process.readyReadStandardOutput, process.errorOccurred, process.finished):
            signal.disconnect()
        if os.name == 'nt':
            process.kill()  # the Windows recorder has no window to receive a close request
        else:
            process.terminate()
        if not process.waitForFinished(500):
            process.kill()
            process.waitForFinished(500)
        process.deleteLater()
        self.level.emit(0.0)

    def _read(self):
        if self.process is None:
            return
        pcm = self.stream.feed(self.process.readAllStandardOutput().data())
        now = time.monotonic()
        if pcm and now - self.last_emit >= .04:
            self.last_emit = now
            self.level.emit(loudness(pcm[-1600:]))  # the latest 50 ms

    def _ended(self):
        if self.process is not None:
            error = bytes(self.process.readAllStandardError().data()).decode(errors='replace').strip()
            self.process.deleteLater()
            self.process = None
            self.level.emit(0.0)
            self.failed.emit(error.splitlines()[-1] if error else 'The microphone stopped.')


class LevelMeter(QWidget):
    """Sixteen bars that rise with the microphone; screen readers get Quiet / Hearing sound."""
    BARS = 16

    def __init__(self, quiet, hearing, unavailable):
        super().__init__()
        self.words = {'quiet': quiet, 'hearing': hearing, 'off': unavailable}
        self.value = 0.0
        self.heard_at = 0.0
        self.state = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(140)
        self.decay = QTimer(self)
        self.decay.timeout.connect(self._fall)
        self.decay.start(50)
        self._describe('off')

    def sizeHint(self):
        return QSize(220, 24)

    def set_level(self, level):
        # Rise at once, fall gently, so short sounds stay visible.
        self.value = max(level, self.value)
        if level > .35:
            self.heard_at = time.monotonic()
        self._describe('hearing' if time.monotonic() - self.heard_at < .8 else 'quiet')
        self.update()

    def set_unavailable(self):
        self.value = 0.0
        self._describe('off')
        self.update()

    def _fall(self):
        if self.value > 0:
            self.value = max(0.0, self.value - .05)
            self.update()
        if self.state == 'hearing' and time.monotonic() - self.heard_at >= .8:
            self._describe('quiet')

    def _describe(self, state):
        if state != self.state:
            self.state = state
            self.setAccessibleDescription(self.words[state])
            self.setToolTip(self.words[state])

    def paintEvent(self, event):
        palette = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        gap = 3
        width = (self.width() - gap * (self.BARS - 1)) / self.BARS
        lit = round(self.value * self.BARS)
        for index in range(self.BARS):
            height = self.height() * (.35 + .65 * (index + 1) / self.BARS)
            if index < lit:
                colour = palette.ok if index < self.BARS * .8 else palette.caution
            else:
                colour = palette.border
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(colour))
            painter.drawRoundedRect(QRectF(index * (width + gap), self.height() - height, width, height), 2, 2)
        painter.end()
