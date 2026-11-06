# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Bounded PulseAudio capture and silence endpointing for desktop dictation."""
import audioop
from collections import deque
import io
import os
import queue
import selectors
import subprocess
import tempfile
import threading
import time
import wave

RATE = 16000
FRAME_BYTES = 640  # 20 ms, mono signed 16-bit PCM


def wav(pcm):
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, RATE, 0, 'NONE', ''))
        audio.writeframes(pcm)
    return output.getvalue()


class Endpoint:
    """Energy endpointing only. Whisper's neural VAD still filters each result."""
    def __init__(self, threshold=250, silence_frames=40, max_frames=750):
        self.threshold = threshold
        self.silence_frames = silence_frames
        self.max_frames = max_frames
        self.reset()

    def reset(self):
        self.preroll = deque(maxlen=12)
        self.frames = []
        self.quiet = self.voiced = 0

    def feed(self, frame):
        if len(frame) != FRAME_BYTES:
            raise ValueError('Expected a complete 20 ms frame')
        speech = audioop.rms(frame, 2) >= self.threshold
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
        pcm = b''.join(self.frames) if self.voiced >= 10 else None
        self.reset()
        return wav(pcm) if pcm else None


class Capture:
    def __init__(self, source=None, cue=None, paused=lambda: False, changed=lambda state: None,
                 threshold=250):
        self.source, self.cue = source, cue
        self.paused, self.changed = paused, changed
        self.endpoint = Endpoint(threshold)
        self.segments = queue.Queue(maxsize=2)
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
                self.segments.put_nowait(segment)
            except queue.Full:
                raise RuntimeError('Recognition cannot keep up. Dictation stopped; previous results are retained.')

    def _pump(self):
        args = ['parec', '--raw', '--format=s16le', '--rate=16000', '--channels=1',
                '--latency-msec=50', '--client-name=Akousousin', '--stream-name=Dictation']
        if self.source:
            args.append('--device=' + self.source)
        process = None
        selector = selectors.DefaultSelector()
        try:
            if os.name == 'nt':
                raise RuntimeError('Desktop microphone capture currently requires Linux')
            with tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors, bufsize=0)
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
                    if first:
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
                        self.put(self.endpoint.feed(frame))
                if not self.cancelled.is_set() and not was_paused:
                    self.put(self.endpoint.finish())
        except Exception as error:
            self.error = str(error)
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
            self.done.set()

    def close(self):
        self.cancel()
        if self.thread:
            self.thread.join(9)
