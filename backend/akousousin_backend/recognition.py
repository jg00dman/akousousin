# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline recognition foundation shared by future SAPI and desktop adapters."""
import argparse
import io
import json
import math
import locale
import logging
import multiprocessing as mp
import os
from pathlib import Path
import re
import subprocess
import shutil
import struct
import sys
import tempfile
import time
import wave

from .server import Synthesizer

RATE = 16000
MAX_SECONDS = 30
MAX_PCM = RATE * 2 * MAX_SECONDS


def model_root():
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    return base / 'Akousousin/models/whisper'


def language_token(value):
    """Normalize locale tags or numeric Windows LCIDs; None means automatic."""
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ValueError('Invalid language')
    if isinstance(value, int):
        value = locale.windows_locale.get(value)
        if value is None:
            raise ValueError('Unknown Windows language ID')
    if not isinstance(value, str):
        raise ValueError('Invalid language')
    token = value.replace('_', '-').split('-')[0].lower()
    if not re.fullmatch('[a-z]{2,3}', token):
        raise ValueError('Expected a language tag or numeric Windows LCID')
    return {'iw': 'he', 'in': 'id', 'ji': 'yi'}.get(token, token)


def read_wav(data):
    if not isinstance(data, bytes) or len(data) > MAX_PCM + 4096:
        raise ValueError('Audio exceeds 30 seconds')
    with wave.open(io.BytesIO(data), 'rb') as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype()) != (1, 2, RATE, 'NONE'):
            raise ValueError('Expected mono 16 kHz signed 16-bit PCM WAV')
        frames = audio.getnframes()
        if not 0 < frames <= RATE * MAX_SECONDS:
            raise ValueError('Audio must contain between 1 sample and 30 seconds')
        pcm = audio.readframes(frames)
        if len(pcm) != frames * 2:
            raise ValueError('Truncated audio')
        return pcm


def load_model(root, selected, factory):
    """Never download during inference. Only model loading triggers fallback."""
    if selected not in ('small', 'turbo'):
        raise ValueError('Unknown model tier')
    try:
        model = factory(str(Path(root) / selected), device='cpu', compute_type='int8',
                        cpu_threads=2, num_workers=1, local_files_only=True)
        return model, selected, None
    except Exception:
        if selected == 'small':
            raise
        logging.exception('Turbo unavailable; falling back to Small')
        model = factory(str(Path(root) / 'small'), device='cpu', compute_type='int8',
                        cpu_threads=2, num_workers=1, local_files_only=True)
        return model, 'small', 'Selected Turbo model could not load; using Small'


def worker(pipe, config):
    try:
        import numpy as np
        from faster_whisper import WhisperModel
        model, active, fallback = load_model(config['root'], config['model'], WhisperModel)
        pipe.send((True, {'model': active, 'fallback': fallback}))
        while True:
            request = pipe.recv()
            if request is None:
                break
            language = request['language']
            if language is not None and language not in model.supported_languages:
                pipe.send((False, 'Unsupported language for selected model'))
                continue
            samples = np.frombuffer(request['pcm'], dtype='<i2').astype(np.float32) / 32768.0
            segments, info = model.transcribe(samples, language=language, task='transcribe',
                                               vad_filter=True, beam_size=1,
                                               condition_on_previous_text=False)
            text = ''.join(segment.text for segment in segments).strip()
            pipe.send((True, {'text': text, 'language': info.language if text else None,
                              'language_probability': info.language_probability if text and not language else None,
                              'language_source': 'explicit' if language else 'detected',
                              'model': active, 'fallback': fallback}))
    except (EOFError, BrokenPipeError):
        pass
    except Exception:
        logging.exception('Whisper worker failed')
        try:
            pipe.send((False, 'Whisper unavailable; check model assets and dependencies'))
        except (EOFError, BrokenPipeError):
            pass
    finally:
        pipe.close()


class Recognizer(Synthesizer):
    """One bounded inference at a time; timeout/death permits a fresh worker."""
    def __init__(self, root=None, model='small', timeout=120, startup_timeout=120, target=worker):
        super().__init__('', timeout, startup_timeout, target)
        self.model = {'root': str(root if root is not None else model_root()), 'model': model}

    def start(self):
        self.close()
        ctx = mp.get_context('spawn')
        self.pipe, child = ctx.Pipe()
        self.process = ctx.Process(target=self.target, args=(child, self.model), daemon=True)
        self.process.start()
        child.close()
        try:
            if not self.pipe.poll(self.startup_timeout):
                raise TimeoutError('Whisper model loading timed out')
            ok, self.rate = self.pipe.recv()
            if not ok:
                raise RuntimeError(self.rate)
        except BaseException:
            self.close()
            raise

    def close(self):
        # Let idle native runtimes release their multiprocessing resources. A
        # failed or hung request still uses the bounded terminate/kill path.
        if self.process is not None and self.pipe is not None and not self.lock.locked():
            try:
                if self.process.is_alive():
                    self.pipe.send(None)
                    self.process.join(2)
            except (EOFError, BrokenPipeError, OSError):
                pass
        super().close()

    @property
    def status(self):
        return self.rate

    def transcribe(self, wav, language=None):
        pcm = read_wav(wav)
        token = language_token(language)
        if not self.lock.acquire(blocking=False):
            raise BlockingIOError('Whisper is busy')
        try:
            if self.process is None or not self.process.is_alive():
                self.start()
            self.pipe.send({'pcm': pcm, 'language': token})
            if not self.pipe.poll(self.timeout):
                raise TimeoutError('Whisper recognition timed out')
            ok, result = self.pipe.recv()
            if not ok:
                raise RuntimeError(result)
            return result
        except BaseException:
            self.close()
            raise
        finally:
            self.lock.release()


def ready_cue():
    """Two short 250 Hz tones, synchronously, before accepted speech audio."""
    output = io.BytesIO()
    samples = []
    for duration, tone in ((.10, True), (.09, False), (.10, True)):
        count = int(RATE * duration)
        for index in range(count):
            envelope = min(1, index / 160, (count - index) / 160)
            sample = int(5000 * envelope * math.sin(2 * math.pi * 250 * index / RATE)) if tone else 0
            samples.append(struct.pack('<h', sample))
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, RATE, 0, 'NONE', ''))
        audio.writeframes(b''.join(samples))
    if os.name == 'nt':
        import winsound
        winsound.PlaySound(output.getvalue(), winsound.SND_MEMORY)
        return
    player = shutil.which('paplay') or shutil.which('pw-play')
    if player is None:
        raise RuntimeError('Ready sound needs paplay or pw-play; disable the sound to continue')
    with tempfile.NamedTemporaryFile(suffix='.wav') as file:
        file.write(output.getvalue())
        file.flush()
        subprocess.run([player, file.name], check=True, timeout=5)


def capture(seconds, source=None, on_ready=None, cue=None):
    """Open the microphone before readiness; exclude startup and cue audio."""
    if os.name == 'nt':
        raise RuntimeError('This capture adapter requires Linux; use a WAV input on Windows')
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= MAX_SECONDS:
        raise ValueError('Capture duration must be 1–30 seconds')
    args = ['parec', '--raw', '--format=s16le', '--rate=16000', '--channels=1',
            '--client-name=Akousousin', '--stream-name=Dictation']
    if source:
        args.append('--device=' + source)
    with tempfile.TemporaryFile() as recording, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdout=recording, stderr=errors)
        try:
            deadline = time.monotonic() + 5
            while os.fstat(recording.fileno()).st_size == 0:
                if process.poll() is not None:
                    errors.seek(0)
                    raise RuntimeError('Microphone capture stopped: ' + errors.read(500).decode(errors='replace'))
                if time.monotonic() >= deadline:
                    raise TimeoutError('Microphone did not become ready')
                time.sleep(.02)
            if cue:
                cue()
                time.sleep(.10)  # Discard buffered speaker output after the cue.
            offset = os.fstat(recording.fileno()).st_size
            offset -= offset % 2
            if on_ready:
                on_ready()
            try:
                process.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                pass
            else:
                raise RuntimeError('Microphone stopped during recording')
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        recording.seek(offset)
        pcm = recording.read(seconds * RATE * 2)
    pcm = pcm[:len(pcm) // 2 * 2]
    if not pcm:
        raise RuntimeError('No microphone audio captured')
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, RATE, 0, 'NONE', ''))
        audio.writeframes(pcm)
    return output.getvalue()


def main():
    mp.freeze_support()
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--wav', type=Path)
    inputs.add_argument('--capture-seconds', type=int)
    inputs.add_argument('--download-model', action='store_true')
    inputs.add_argument('--import-model', type=Path)
    parser.add_argument('--no-beep', action='store_true')
    parser.add_argument('--source', help='PulseAudio source name; omit to follow system default')
    parser.add_argument('--model', choices=['small', 'turbo'], default='small')
    parser.add_argument('--models', type=Path, default=model_root())
    parser.add_argument('--language', help='Fixed language tag; omit for automatic detection')
    args = parser.parse_args()
    def status(text):
        print(text, file=sys.stderr, flush=True)
    if args.download_model or args.import_model:
        from .models import install
        install(args.model, args.models, source=args.import_model, progress=status)
        status('Model installed in ' + str(args.models / args.model))
        return
    recognizer = Recognizer(args.models, args.model)
    try:
        if args.wav:
            with args.wav.open('rb') as audio:
                data = audio.read(MAX_PCM + 4097)
        else:
            status('Loading model…')
            recognizer.start()
            status('Opening microphone…')
            data = capture(args.capture_seconds, args.source,
                           on_ready=lambda: status('Listening — speak now'),
                           cue=None if args.no_beep else ready_cue)
            status('Transcribing…')
        print(json.dumps(recognizer.transcribe(data, args.language), ensure_ascii=False))
    finally:
        recognizer.close()


if __name__ == '__main__':
    main()
