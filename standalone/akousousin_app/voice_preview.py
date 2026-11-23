# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Audition a voice without changing its assignment or the desktop clipboard."""
import json
import os
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

from . import catalogue, playback, runtime, settings, speech_gate


def play(path, text, voice, sample, stop):
    gate = speech_gate.snapshot(path)

    def cancelled():
        return stop.is_set() or speech_gate.suppressed(path, gate)

    if gate[0] or cancelled():
        return False
    with tempfile.TemporaryDirectory() as folder:
        audio = Path(folder) / 'preview.wav'
        if sample:
            from .network import require, samples_allowed
            require(path, 'online voice samples')
            if not samples_allowed(path):
                raise PermissionError('Samples of voices that are not downloaded are turned off in Privacy.')
            import miniaudio
            from akousousin_backend.tls import https_context
            with urllib.request.urlopen(catalogue.BASE + '/' + sample + '/samples/speaker_0.mp3',
                                        context=https_context(), timeout=20) as response:
                data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise ValueError('Voice recording exceeds the sample size limit.')
            if cancelled():
                return False
            decoded = miniaudio.decode(data, nchannels=1, sample_rate=22050)
            with wave.open(str(audio), 'wb') as output:
                output.setparams((1, 2, 22050, 0, 'NONE', ''))
                output.writeframes(decoded.samples.tobytes())
        else:
            runtime.call(path, {'command': 'start'})
            port = settings.load(path)['port']
            request = urllib.request.Request(f'http://127.0.0.1:{port}/synthesize',
                    json.dumps({'text': text, 'voice': voice, 'preview_voice': True}).encode(),
                    {'Content-Type': 'application/json'})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=65) as response:
                audio.write_bytes(response.read())
        if cancelled():
            return False
        if os.name != 'nt':
            return playback.play_wav(audio, cancelled)
        import winsound
        with wave.open(str(audio), 'rb') as sound:
            duration = sound.getnframes() / sound.getframerate()
        winsound.PlaySound(str(audio), winsound.SND_FILENAME | winsound.SND_ASYNC)
        try:
            until = time.monotonic() + duration
            while time.monotonic() < until:
                if cancelled():
                    return False
                time.sleep(.025)
            return True
        finally:
            winsound.PlaySound(None, 0)
