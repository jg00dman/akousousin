# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Host WAV preview with cancellation and copyable player diagnostics."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time

from . import runtime


class PlaybackError(RuntimeError):
    title = 'Preview playback failed'

    def __init__(self, player, path, reason, diagnostic='', command=None):
        self.command = shlex.join(command or [player, str(path)])
        self.message = f'Audio was generated, but {Path(player).name} {reason}.'
        if diagnostic:
            self.message += '\n' + diagnostic
        self.details = 'Saved WAV: ' + str(path) + '\nPlayer: ' + player + '\n' + reason
        if diagnostic:
            self.details += '\n' + diagnostic
        super().__init__(self.message)


def play_wav(path, cancelled=lambda: False, timeout=120):
    # PipeWire natively when it is the audio server, otherwise PulseAudio.
    from akousousin_backend.audio_system import AudioUnavailable, play_command
    try:
        command = play_command(path, 'Voice preview', 'Accessibility')
    except AudioUnavailable as error:
        raise RuntimeError(f'Preview audio was generated at {path}, but {error}') from error
    player = command[0]
    if cancelled():
        return False
    # A temporary file cannot deadlock on a full stderr pipe, even for a noisy
    # driver. Only the final 4 KiB is included in the user-visible diagnostic.
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.Popen(command, env=runtime.host_environment(),
                                       stdout=output, stderr=subprocess.STDOUT)
        except OSError as error:
            raise PlaybackError(player, path, 'could not start', str(error), command) from error
        try:
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if cancelled():
                    return False
                if time.monotonic() >= deadline:
                    raise PlaybackError(player, path, f'timed out after {timeout} seconds', command=command)
                time.sleep(.025)
            if process.returncode:
                output.seek(0, os.SEEK_END)
                output.seek(max(0, output.tell() - 4096))
                detail = output.read().decode(errors='replace').strip()
                raise PlaybackError(player, path, f'exited with status {process.returncode}', detail, command)
            return True
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)


DRAIN_SECONDS = .35  # longer than the device buffer, so the last word is heard


def _stream(pcm, frame_bytes, rate, finished):
    """miniaudio generator: the audio, then silence until the device has played it all."""
    required = yield b''
    offset = 0
    while offset < len(pcm):
        chunk = pcm[offset:offset + required * frame_bytes]
        offset += len(chunk)
        required = yield chunk
    remaining = int(rate * DRAIN_SECONDS)
    while remaining > 0:
        count = min(required, remaining)
        remaining -= count
        required = yield bytes(count * frame_bytes)
    finished.set()
    while True:
        required = yield bytes(required * frame_bytes)


def play_native(path, cancelled=lambda: False, timeout=120, backends=None):
    """Play a WAV through the system's default output (Windows), to the very end.

    Timing a fire-and-forget sound and stopping it when its length has passed
    cut off the end of the last word, because the device starts a little late.
    Here playback ends only after the audio and a buffer's worth of silence
    have been consumed by the device.
    """
    import threading
    import wave
    import miniaudio
    with wave.open(str(path), 'rb') as sound:
        channels, width, rate = sound.getnchannels(), sound.getsampwidth(), sound.getframerate()
        pcm = sound.readframes(sound.getnframes())
    if width != 2:
        raise RuntimeError('Expected 16-bit audio')
    if cancelled():
        return False
    finished = threading.Event()
    device = miniaudio.PlaybackDevice(output_format=miniaudio.SampleFormat.SIGNED16, nchannels=channels,
                                      sample_rate=rate, buffersize_msec=200, backends=backends,
                                      app_name='Akousousin')
    try:
        stream = _stream(pcm, channels * width, rate, finished)
        next(stream)
        device.start(stream)
        deadline = time.monotonic() + timeout
        while not finished.wait(.025):
            if cancelled():
                return False
            if time.monotonic() >= deadline:
                raise RuntimeError(f'Playback timed out after {timeout} seconds')
        return True
    finally:
        device.close()
