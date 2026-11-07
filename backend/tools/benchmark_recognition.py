#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Offline real-fixture benchmark. Install models explicitly before running."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import time
import wave
import importlib.metadata

from akousousin_backend.recognition import Recognizer
from akousousin_backend.recognition_config import cpu_threads
from akousousin_backend.models import installed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--fixture', action='append', required=True, help='language=path.wav; repeat for another language')
    parser.add_argument('--tiers', nargs='+', default=['base', 'base.en', 'small', 'small.en'])
    parser.add_argument('--threads', nargs='+', type=int, default=sorted({1, 2, cpu_threads()}))
    parser.add_argument('--modes', nargs='+', choices=['auto-each-phrase', 'locked-vad', 'locked', 'auto-session'],
                        default=['auto-each-phrase', 'locked-vad', 'locked', 'auto-session'])
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be at least 1')
    os.environ['HF_HUB_OFFLINE'] = '1'
    fixtures = []
    for value in args.fixture:
        language, path = value.split('=', 1)
        data = Path(path).read_bytes()
        with wave.open(str(path), 'rb') as sound:
            duration = sound.getnframes() / sound.getframerate()
        fixtures.append((language, path, data, duration))
    report = {'hardware': {'platform':platform.platform(), 'processor':platform.processor(),
                          'physical_cores':cpu_threads(), 'logical_cores':os.cpu_count(),
                          'cpuinfo': next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                                           if line.startswith('model name')), '') if Path('/proc/cpuinfo').exists() else '',
                          'cpu_quota':Path('/sys/fs/cgroup/cpu.max').read_text().strip() if Path('/sys/fs/cgroup/cpu.max').exists() else None},
              'versions':{name:importlib.metadata.version(name) for name in ('faster-whisper','ctranslate2','onnxruntime')},
              'measurements':[], 'unavailable':[]}
    for tier in args.tiers:
        if not installed(tier, args.models):
            report['unavailable'].append(tier)
            continue
        for language, path, data, duration in fixtures:
            if tier.endswith('.en') and language != 'en':
                continue
            for threads in args.threads:
                for mode in ([item for item in args.modes if item in ('locked', 'locked-vad')] if tier.endswith('.en') else args.modes):
                    # auto-each-phrase + VAD retains the former behaviour as a baseline.
                    endpointed = mode in ('locked', 'auto-session')
                    token = language if mode in ('locked', 'locked-vad') else None
                    recognizer = Recognizer(args.models, tier, threads=threads)
                    began = time.perf_counter()
                    try:
                        recognizer.start()
                        loaded = time.perf_counter() - began
                        first = recognizer.transcribe(data, token, endpointed=endpointed)
                        if mode == 'auto-session' and first['text']:
                            token = first['language']
                        cold = time.perf_counter() - began
                        warm = []
                        for _ in range(args.runs):
                            start = time.perf_counter()
                            result = recognizer.transcribe(data, token, endpointed=endpointed)
                            warm.append(time.perf_counter() - start)
                        row = dict(model=tier, language=language, fixture=str(path), audio_seconds=duration,
                                   threads=threads, mode=mode, endpointed=endpointed, load_seconds=loaded,
                                   cold_seconds=cold, warm_seconds=warm, warm_median_seconds=statistics.median(warm),
                                   text=result['text'], detected_language=result['language'])
                        report['measurements'].append(row)
                        print(json.dumps(row, ensure_ascii=False), flush=True)
                    finally:
                        recognizer.close()
                    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
