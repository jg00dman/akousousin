# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Bounded microphone capture (PipeWire or PulseAudio) and silence endpointing for desktop dictation."""
import audioop
from collections import deque
import io
import logging
import os
import queue
import selectors
import subprocess
import tempfile
import threading
import time
import wave

from .host import host_environment

RATE = 16000
FRAME_BYTES = 640  # 20 ms, mono signed 16-bit PCM


def wav(pcm):
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, RATE, 0, 'NONE', ''))
        audio.writeframes(pcm)
    return output.getvalue()


class Loudness:
    """Fallback speech test by loudness, used only when Silero cannot load.

    It learns the room's noise level from quiet frames, so steady noise above
    the threshold can be mistaken for speech; Silero does not have that flaw.
    """
    name = 'loudness'

    def __init__(self, threshold=250):
        self.threshold = threshold
        self.noise_floor = threshold / 3

    def calibrate(self, pcm):
        levels = [audioop.rms(pcm[i:i + FRAME_BYTES], 2)
                  for i in range(0, len(pcm) - FRAME_BYTES + 1, FRAME_BYTES)]
        if levels:
            self.noise_floor = sorted(levels)[len(levels) // 2]

    def __call__(self, frame, in_phrase):
        level = audioop.rms(frame, 2)
        speech = level >= max(self.threshold, self.noise_floor * 2 + 40)
        if not speech:
            self.noise_floor = .98 * self.noise_floor + .02 * level
        return speech


class Silero:
    """Speech test by Silero VAD probability, with hysteresis inside a phrase."""
    name = 'silero'
    START, CONTINUE = .5, .35

    def __init__(self, detector):
        self.detector = detector
        self.probability = 0.0

    def calibrate(self, pcm):
        pass  # nothing to learn: the model already knows what speech is

    def __call__(self, frame, in_phrase):
        probabilities = self.detector.feed(frame)
        if probabilities:
            self.probability = probabilities[-1]
        return self.probability >= (self.CONTINUE if in_phrase else self.START)


class Endpoint:
    """Splits the microphone stream into phrases: speech, then 0.5 s of non-speech."""
    def __init__(self, threshold=250, silence_frames=25, max_frames=400, voice=None):
        self.voice = voice or Loudness(threshold)
        self.silence_frames = silence_frames
        self.max_frames = max_frames
        self.last_metadata = {}
        self.reset()

    def calibrate(self, pcm):
        self.voice.calibrate(pcm)

    def reset(self):
        self.preroll = deque(maxlen=12)
        self.frames = []
        self.quiet = self.voiced = 0
        self.last_speech_at = None

    def feed(self, frame, captured_at=None):
        if len(frame) != FRAME_BYTES:
            raise ValueError('Expected a complete 20 ms frame')
        speech = self.voice(frame, bool(self.frames))
        if speech:
            self.last_speech_at = time.monotonic() if captured_at is None else captured_at
        if not self.frames:
            self.preroll.append(frame)
            if not speech:
                return None
            self.frames = list(self.preroll)
        else:
            self.frames.append(frame)
        self.voiced += int(speech)
        self.quiet = 0 if speech else self.quiet + 1
        if self.quiet >= self.silence_frames or len(self.frames) >= self.max_frames:
            return self.finish()
        return None

    def finish(self):
        metadata = {'speech_detector': self.voice.name, 'speech_seconds': round(self.voiced * .02, 3),
                    'endpoint_wait_seconds': round(self.quiet * .02, 3),
                    'speech_ended_at': self.last_speech_at}
        trim = max(0, self.quiet - 5)
        frames = self.frames[:-trim] if trim else self.frames
        pcm = b''.join(frames) if self.voiced >= 10 else None
        self.reset()
        self.last_metadata = metadata
        return wav(pcm) if pcm else None


class Capture:
    def __init__(self, source=None, cue=None, paused=lambda: False, changed=lambda state: None,
                 threshold=250, ended=lambda: None):
        self.ended = ended
        self.source, self.cue = source, cue
        self.paused, self.changed = paused, changed
        self.threshold = threshold
        self.endpoint = Endpoint(threshold)
        self.segments = queue.Queue(maxsize=2)
        self.queued_at = {}
        self.segment_info = {}
        self.stop = threading.Event()
        self.cancelled = threading.Event()
        self.ready = threading.Event()
        self.done = threading.Event()
        self.error = None
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def finish(self):
        self.stop.set()

    def cancel(self):
        self.cancelled.set()
        self.stop.set()

    def put(self, segment):
        if segment is not None:
            try:
                self.queued_at[id(segment)] = time.monotonic()
                self.segment_info[id(segment)] = dict(self.endpoint.last_metadata)
                self.segments.put_nowait(segment)
            except queue.Full:
                self.queued_at.pop(id(segment), None)
                self.segment_info.pop(id(segment), None)
                raise RuntimeError('Recognition cannot keep up. Dictation stopped; previous results are retained.')

    def _pump(self):
        from .audio_system import PcmStream, record_command
        from .voice_activity import detector
        model, problem = detector()
        if model is not None:
            self.endpoint = Endpoint(self.threshold, voice=Silero(model))
        else:
            logging.warning('Silero speech detection unavailable (%s); using loudness', problem)
        stream = PcmStream()
        process = None
        selector = selectors.DefaultSelector()
        try:
            if os.name == 'nt':
                raise RuntimeError('Desktop microphone capture currently requires Linux')
            args = record_command(self.source)
            with tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors, bufsize=0, env=host_environment())
                os.set_blocking(process.stdout.fileno(), False)
                selector.register(process.stdout, selectors.EVENT_READ)
                startup = time.monotonic() + 5
                last_audio = time.monotonic()
                buffer = bytearray()
                was_paused = False
                first = True
                while not self.stop.is_set():
                    if process.poll() is not None:
                        errors.seek(0)
                        raise RuntimeError('Microphone disconnected: ' + errors.read(500).decode(errors='replace'))
                    if not selector.select(.05):
                        if time.monotonic() - last_audio > 5:
                            raise TimeoutError('Microphone stopped delivering audio')
                        if first and time.monotonic() >= startup:
                            raise TimeoutError('Microphone did not become ready')
                        continue
                    data = os.read(process.stdout.fileno(), 8192)
                    if not data:
                        raise RuntimeError('Microphone stream ended')
                    last_audio = time.monotonic()
                    data = stream.feed(data)
                    if not data:
                        continue
                    if first:
                        self.endpoint.calibrate(data)
                        if self.cue:
                            self.cue()
                        # Drain startup/cue audio before accepting speech.
                        until = time.monotonic() + .12
                        while time.monotonic() < until:
                            if selector.select(.02):
                                os.read(process.stdout.fileno(), 8192)
                        first = False
                        if self.stop.is_set():
                            break
                        self.ready.set()
                        self.changed('Listening — speak now')
                        continue
                    paused = self.paused()
                    if paused or paused != was_paused:
                        self.endpoint.reset()
                        buffer.clear()
                        if paused != was_paused:
                            self.changed('Paused while AKS speaks' if paused else 'Listening — speak now')
                        was_paused = paused
                        continue
                    buffer.extend(data)
                    while len(buffer) >= FRAME_BYTES:
                        frame = bytes(buffer[:FRAME_BYTES]); del buffer[:FRAME_BYTES]
                        # Estimate frame arrival from the read timestamp and remaining PCM.
                        captured_at = last_audio - len(buffer) / (RATE * 2)
                        self.put(self.endpoint.feed(frame, captured_at))
                if not self.cancelled.is_set() and not was_paused:
                    self.put(self.endpoint.finish())
        except Exception as error:
            self.error = str(error)
            self.changed('Recording stopped: ' + self.error)
        finally:
            selector.close()
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=2)
                process.stdout.close()
            try:
                self.ended()
            except Exception as error:
                self.error = self.error or str(error)
            self.done.set()

    def close(self):
        self.cancel()
        if self.thread:
            self.thread.join(9)
