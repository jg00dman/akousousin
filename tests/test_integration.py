#!/usr/bin/env python3
"""Exercise the real Wine DLL against a deterministic local Piper HTTP substitute.

WINE points to a Wine loader; WINEPREFIX must be a disposable registered prefix.
The substitute tests transport and samples, not neural speech synthesis.
"""
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = [12000, -12000, 3000, -3000] * 4096
PCM = struct.pack("<" + "h" * len(SAMPLES), *SAMPLES)


def wav_bytes(rate=22050):
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        wav.writeframes(PCM)
    return out.getvalue()


class Handler(BaseHTTPRequestHandler):
    mode = "valid"
    requests = []

    def log_message(self, *_):
        pass

    def do_POST(self):
        if self.path != "/synthesize":
            self.send_error(404)
            return
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append(request)
        if self.mode == "error":
            self.send_error(500)
            return
        if self.mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "/redirected")
            self.end_headers()
            return
        data = wav_bytes(16000 if self.mode == "wrong-rate" else 22050)
        if self.mode == "invalid":
            data = b"this is not a WAV file"
        elif self.mode == "truncated":
            data = data[:-1]
        elif self.mode == "overflow":
            data = data[:40] + b"\xff\xff\xff\xff" + data[44:]
        elif self.mode == "odd-chunk":
            data = data[:12] + b"JUNK\x01\x00\x00\x00!\x00" + data[12:]
            data = data[:4] + struct.pack("<I", len(data) - 8) + data[8:]
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 5000), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.temp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def setUp(self):
        Handler.mode = "valid"
        Handler.requests.clear()

    def run_probe(self, *, direct=False, rate=0, volume=100, text='Hello "Piper" \\ café 世界\n', mode="", fail=False):
        output = Path(self.temp.name) / ("out.raw" if direct else "out.wav")
        exe = ROOT / "build" / ("engine-probe.exe" if direct else "sapi-probe.exe")
        native = os.environ.get('AKOUSOUSIN_NATIVE_WINDOWS') == '1'
        args = ([] if native else [os.environ['WINE']]) + [str(exe),
                str(output) if native else 'Z:' + str(output), str(rate), str(volume), text]
        if direct or mode:
            args.append(mode)
        result = subprocess.run(args, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, int(fail), result.stdout + result.stderr)
        return output

    def test_voice_enumeration_and_wav(self):
        output = self.run_probe()
        with wave.open(str(output), "rb") as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 22050))
            self.assertEqual(wav.readframes(wav.getnframes()), PCM)
        expected = {"text": 'Hello "Piper" \\ café 世界\n', "length_scale": 1.0}
        if os.environ.get('AKOUSOUSIN_STANDALONE'):
            expected.update(voice='en_US-ljspeech-medium', sample_rate=22050)
        self.assertEqual(Handler.requests[-1], expected)

    def test_long_fragment_is_split_without_losing_text(self):
        if not os.environ.get('AKOUSOUSIN_STANDALONE'):
            self.skipTest('Standalone bounded-fragment transport')
        text = 'A complete sentence with café and 世界. ' * 40
        output = self.run_probe(direct=True, text=text)
        self.assertGreater(len(Handler.requests), 1)
        self.assertEqual(''.join(item['text'] for item in Handler.requests), text)
        self.assertEqual(output.read_bytes(), PCM * len(Handler.requests))

    def test_async_and_rate(self):
        self.run_probe(mode="async", rate=10)
        self.assertEqual(Handler.requests[-1]["length_scale"], 0.5)
        self.run_probe(rate=-10)
        self.assertEqual(Handler.requests[-1]["length_scale"], 2.0)

    def test_volume_and_partial_writes(self):
        output = self.run_probe(direct=True, volume=50, mode="partial")
        expected = struct.pack("<" + "h" * len(SAMPLES), *(s // 2 for s in SAMPLES))
        self.assertEqual(output.read_bytes(), expected)
        # .NET accepts full buffers but does not update the output byte count.
        output = self.run_probe(direct=True, mode="no-count")
        self.assertEqual(output.read_bytes(), PCM)

    def test_silent_volume(self):
        output = self.run_probe(direct=True, volume=0)
        self.assertEqual(output.read_bytes(), bytes(len(PCM)))

    def test_abort_during_output(self):
        output = self.run_probe(direct=True, mode="abort")
        self.assertEqual(output.read_bytes(), PCM[:4096])

    def test_sink_failure(self):
        output = self.run_probe(direct=True, mode="fail-write", fail=True)
        self.assertEqual(output.stat().st_size, 0)
        # An explicit zero-progress report must still fail, not loop forever.
        output = self.run_probe(direct=True, mode="zero-write", fail=True)
        self.assertEqual(output.stat().st_size, 0)

    def test_reject_http_and_malformed_audio(self):
        for mode in ("error", "redirect", "invalid", "truncated", "overflow", "wrong-rate"):
            with self.subTest(mode=mode):
                Handler.mode = mode
                output = self.run_probe(direct=True, fail=True)
                self.assertEqual(output.stat().st_size, 0)

    def test_padded_unknown_chunk(self):
        Handler.mode = "odd-chunk"
        self.assertEqual(self.run_probe(direct=True).read_bytes(), PCM)

    def test_silence_fragments(self):
        output = self.run_probe(direct=True, mode="silence")
        self.assertEqual(output.read_bytes(), PCM + bytes(4410) + PCM)

    def test_ssml_prosody(self):
        text = '<speak version="1.0" xml:lang="en-US"><prosody volume="50">Hello</prosody></speak>'
        output = self.run_probe(text=text, mode="xml")
        expected = struct.pack("<" + "h" * len(SAMPLES), *(s // 2 for s in SAMPLES))
        with wave.open(str(output), "rb") as wav:
            self.assertEqual(wav.readframes(wav.getnframes()), expected)
        self.assertEqual(Handler.requests[-1]["text"], "Hello")

    def test_default_voice(self):
        self.run_probe(mode="default")

    def test_automation_voice(self):
        output = self.run_probe(mode="automation")
        with wave.open(str(output), "rb") as wav:
            self.assertEqual(wav.readframes(wav.getnframes()), PCM)

    def test_smoke_runner_with_substitute(self):
        config = Path(self.temp.name) / "voice.onnx.json"
        config.write_text(json.dumps({"audio": {"sample_rate": 22050}}))
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/smoke-piper.py"), "--config", str(config),
             "--output-dir", str(Path(self.temp.name) / "smoke")],
            capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Wine SAPI:", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
