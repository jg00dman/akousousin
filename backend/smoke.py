#!/usr/bin/env python3
"""Test actual synthesis from the redistributable binary, not a Python import."""
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
import wave

root = Path(sys.argv[1]).resolve()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with (root.parent / 'real-synthesis.log').open('w') as log:
    process = subprocess.Popen([str(root / 'akousousin-piper'), '--model',
                                str(root / 'voices/en_US-ljspeech-medium.onnx')],
                               stdout=log, stderr=log, start_new_session=True)
    try:
        deadline = time.monotonic() + 70
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Packaged backend exited during startup')
            try:
                with opener.open('http://127.0.0.1:5000/health', timeout=1) as response:
                    assert json.load(response)['ready']
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise TimeoutError('Backend startup')
        for scale in (1.0, 0.5, 2.0):
            request = urllib.request.Request('http://127.0.0.1:5000/synthesize',
                        json.dumps({'text': 'Open SAPI deployment test.', 'length_scale': scale}).encode(),
                        {'Content-Type': 'application/json'})
            with opener.open(request, timeout=65) as response:
                data = response.read()
            with wave.open(io.BytesIO(data), 'rb') as wav:
                assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 22050)
                assert wav.getnframes() > 2205
            print(f'Real frozen-binary synthesis passed at length_scale={scale}: {len(data)} bytes')
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
