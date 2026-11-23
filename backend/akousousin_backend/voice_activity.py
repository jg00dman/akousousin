# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Streaming speech detection with Silero VAD.

Dictation decides where phrases start and end with Silero, a small neural
voice-activity model that faster-whisper already ships. Unlike a loudness
threshold it tells speech from fans, music, keyboards and breaths, so those
sounds never reach Whisper as phrases. The model's state carries across
chunks, so it runs on the live microphone stream at 32 ms steps.
"""
from pathlib import Path
import threading

CHUNK = 512      # samples per Silero step at 16 kHz (32 ms)
CONTEXT = 64     # samples of the previous chunk each step also sees


def model_path():
    from faster_whisper.utils import get_assets_path
    return Path(get_assets_path()) / 'silero_vad_v6.onnx'


_sessions = {}
_lock = threading.Lock()


def session(path=None):
    """One ONNX session per model file, shared by every capture in this process.

    Loading takes about 0.2 s; reusing it keeps that off every dictation start.
    Each SpeechDetector keeps its own recurrent state, so sharing is safe.
    """
    path = str(path or model_path())
    with _lock:
        if path not in _sessions:
            import onnxruntime
            options = onnxruntime.SessionOptions()
            options.inter_op_num_threads = options.intra_op_num_threads = 1
            options.enable_cpu_mem_arena = False
            options.log_severity_level = 4
            _sessions[path] = onnxruntime.InferenceSession(path, providers=['CPUExecutionProvider'],
                                                           sess_options=options)
        return _sessions[path]


class SpeechDetector:
    """Feed signed 16-bit mono PCM at 16 kHz; get one speech probability per 32 ms."""
    def __init__(self, path=None):
        import numpy
        self.np = numpy
        self.session = session(path)
        self.reset()

    def reset(self):
        np = self.np
        self.h = np.zeros((1, 1, 128), dtype='float32')
        self.c = np.zeros((1, 1, 128), dtype='float32')
        self.context = np.zeros(CONTEXT, dtype='float32')
        self.pending = np.zeros(0, dtype='float32')

    def feed(self, pcm):
        np = self.np
        samples = np.frombuffer(pcm, dtype='<i2').astype('float32') / 32768.0
        self.pending = np.concatenate((self.pending, samples))
        probabilities = []
        while len(self.pending) >= CHUNK:
            chunk, self.pending = self.pending[:CHUNK], self.pending[CHUNK:]
            window = np.concatenate((self.context, chunk))[None, :]
            output, self.h, self.c = self.session.run(None, {'input': window, 'h': self.h, 'c': self.c})
            self.context = chunk[-CONTEXT:]
            probabilities.append(float(np.asarray(output).reshape(-1)[0]))
        return probabilities


def detector():
    """A SpeechDetector, or None with the reason when recognition extras are missing."""
    try:
        return SpeechDetector(), ''
    except Exception as error:  # missing onnxruntime/faster-whisper or a damaged model file
        return None, str(error) or type(error).__name__
