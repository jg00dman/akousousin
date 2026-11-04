#!/usr/bin/env python3
"""Check a real Piper server and the registered Wine voice independently."""
import argparse
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import urllib.request
import wave


def inspect_wav(data, expected_rate):
    with wave.open(io.BytesIO(data), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, expected_rate):
            raise RuntimeError("Unexpected PCM format")
        frames = wav.getnframes()
        pcm = wav.readframes(frames)
    if not frames or len(pcm) != frames * 2:
        raise RuntimeError("Empty or truncated audio")
    if not any(struct.unpack("<" + "h" * frames, pcm)):
        raise RuntimeError("Audio is entirely silent")
    return frames / expected_rate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--output-dir", type=Path, default=Path("build/real-piper"))
    parser.add_argument("--text", default="Hello from Akousousin. This is a real Piper speech test.")
    args = parser.parse_args()
    rate = json.loads(args.config.read_text())["audio"]["sample_rate"]
    native = os.environ.get("AKOUSOUSIN_NATIVE_WINDOWS") == "1"
    wine = os.environ.get("WINE", "")
    if not native and "WINEPREFIX" not in os.environ:
        parser.error("Set WINEPREFIX to the prefix with your registered Piper voice")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        f"http://127.0.0.1:{args.port}/synthesize",
        data=json.dumps({"text": args.text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    # This request is explicitly local, matching the engine's no-proxy policy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=60) as response:
        direct = response.read(64 * 1024 * 1024 + 1)
    duration = inspect_wav(direct, rate)
    (output / "direct.wav").write_bytes(direct)
    print(f"Piper HTTP: {duration:.2f} seconds of non-silent PCM", flush=True)
    probe = Path(__file__).resolve().parents[1] / "build/sapi-probe.exe"
    subprocess.run(([] if native else [wine]) + [str(probe),
                    str(output / "sapi.wav") if native else "Z:" + str(output / "sapi.wav"), "0", "100", args.text],
                   check=True, timeout=90)
    duration = inspect_wav((output / "sapi.wav").read_bytes(), rate)
    print(f"Wine SAPI: {duration:.2f} seconds of non-silent PCM")


if __name__ == "__main__":
    main()
