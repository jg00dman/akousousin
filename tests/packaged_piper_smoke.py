#!/usr/bin/env python3
"""Real neural synthesis through the separate frozen backend and packaged Wine.

Run under Xvfb with the AppImage path as the argument. No model enters AppDir.
This verifies WAV samples, not audible desktop playback or Logos behavior.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[1]
TAG = 'piper-backend-41388556427-1'
SHA256 = 'b88af610f3c3f0160a9a0792cac8d739ac07186fbcbbd03fb196a9a1b704402d'
work = ROOT / 'build/real-piper'
work.mkdir(parents=True, exist_ok=True)
archive = work / 'backend.tar.xz'
digest = hashlib.sha256()
print('Download checksum-pinned external Piper backend and voice', flush=True)
url = f'https://github.com/jg00dman/opensapi/releases/download/{TAG}/opensapi-piper-linux-x86_64.tar.xz'
with urllib.request.urlopen(url, timeout=30) as response, archive.open('wb') as output:
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        output.write(chunk)
if digest.hexdigest() != SHA256:
    raise RuntimeError('Backend checksum mismatch')
# The archive is authenticated against a pinned cryptographic digest before extraction.
subprocess.run(['tar', '-xJf', str(archive), '-C', str(work)], check=True, timeout=60)
backend = work / 'opensapi-piper'
model = backend / 'voices/en_US-ljspeech-medium.onnx'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
env = os.environ.copy()
env.update(APPIMAGE_EXTRACT_AND_RUN='1', WINEPREFIX=str(work / 'wine-prefix'))
image = str(Path(sys.argv[1]).resolve())
with (work / 'backend.log').open('w') as log:
    process = subprocess.Popen([str(backend / 'opensapi-piper'), '--model', str(model)],
                               stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    try:
        deadline = time.monotonic() + 65
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Backend exited; inspect build/real-piper/backend.log')
            try:
                with opener.open('http://127.0.0.1:5000/health', timeout=1) as response:
                    if json.load(response)['ready']:
                        break
            except OSError:
                time.sleep(0.2)
        else:
            raise TimeoutError('Backend startup')
        print('Register real bundled voice in a new disposable Wine prefix', flush=True)
        subprocess.run([image, '--opensapi-register', str(model) + '.json'], env=env, check=True, timeout=190)
        output = work / 'real-piper-sapi.wav'
        print('Request real neural speech through packaged Wine SAPI', flush=True)
        text = 'Open SAPI is speaking through the packaged Piper service.'
        subprocess.run([image, '--opensapi-wav', str(output), text],
                       env=env, check=True, timeout=75)
        with wave.open(str(output), 'rb') as wav:
            assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 22050)
            assert wav.getnframes() > 2205
            assert any(wav.readframes(wav.getnframes()))
        print('PASS: packaged Wine + frozen Piper + bundled voice produced non-silent 22050 Hz PCM WAV.', flush=True)
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
