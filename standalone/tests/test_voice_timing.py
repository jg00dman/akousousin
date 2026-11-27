# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from akousousin_app import voice_timing


def field(number, payload):
    return voice_timing._encode(number << 3 | 2) + voice_timing._encode(len(payload)) + payload


def model(durations=b'durations', exposed=False, extra_ceil=False):
    """A tiny protobuf shaped like a Piper voice: a Ceil node feeding the decoder, weights, an audio output."""
    nodes = field(1, field(1, b'logw') + field(2, durations) + field(4, b'Ceil'))
    if extra_ceil:
        nodes += field(1, field(2, b'other') + field(4, b'Ceil'))
    nodes += field(1, field(1, durations) + field(2, b'audio') + field(4, b'Decoder'))
    weights = field(5, b'\x00' * 300)  # an initializer, long enough to need a two-byte length
    outputs = field(12, field(1, b'audio')) + (field(12, field(1, durations)) if exposed else b'')
    return voice_timing._encode(1 << 3) + b'\x08' + field(7, nodes + weights + outputs) + field(8, b'opset')


class PatchTests(unittest.TestCase):
    def test_the_duration_tensor_is_found(self):
        self.assertEqual(voice_timing.duration_tensor(model()), ('durations', False))
        self.assertEqual(voice_timing.duration_tensor(model(exposed=True)), ('durations', True))

    def test_patching_exposes_it_once_and_keeps_everything_else(self):
        original = model()
        patched = voice_timing.with_durations(original)
        self.assertEqual(voice_timing.duration_tensor(patched), ('durations', True))
        self.assertEqual(voice_timing.with_durations(patched), patched)  # idempotent
        added = field(12, field(1, b'durations'))
        old = voice_timing._graph(original)
        grown = len(voice_timing._encode(old[4] - old[3] + len(added))) - len(voice_timing._encode(old[4] - old[3]))
        self.assertEqual(len(patched) - len(original), len(added) + grown)
        self.assertTrue(patched.endswith(field(8, b'opset')))

    def test_unusual_models_are_refused(self):
        with self.assertRaises(ValueError):
            voice_timing.duration_tensor(model(extra_ceil=True))
        with self.assertRaises(ValueError):
            voice_timing.duration_tensor(model()[:-20])


class OnDiskTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / 'Akousousin'
        self.voice = self.root / 'voices' / 'demo'
        self.voice.mkdir(parents=True)
        self.model = self.voice / 'demo.onnx'
        self.model.write_bytes(model())
        self.download = hashlib.sha256(self.model.read_bytes()).hexdigest()
        (self.voice / 'provenance.json').write_text(json.dumps({'model_sha256': self.download}))

    def test_a_voice_in_our_folder_is_patched_once_and_its_checksum_recorded(self):
        self.assertFalse(voice_timing.timed(self.model))
        self.assertTrue(voice_timing.ensure_timed(self.model, self.root))
        self.assertTrue(voice_timing.timed(self.model))
        record = json.loads((self.voice / 'provenance.json').read_text())
        patched = hashlib.sha256(self.model.read_bytes()).hexdigest()
        self.assertEqual(record, {'model_sha256': self.download, 'timed_sha256': patched})
        self.assertTrue(voice_timing.checksum_matches(patched, record))
        self.assertTrue(voice_timing.checksum_matches(self.download, record))
        self.assertFalse(voice_timing.checksum_matches('0' * 64, record))
        before = self.model.stat().st_mtime_ns
        self.assertTrue(voice_timing.ensure_timed(self.model, self.root))  # already done: not rewritten
        self.assertEqual(self.model.stat().st_mtime_ns, before)
        self.assertEqual([path.name for path in self.voice.iterdir() if path.name.startswith('.')], [])

    def test_voices_elsewhere_are_left_alone(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            other = Path(elsewhere) / 'mine.onnx'
            other.write_bytes(model())
            self.assertFalse(voice_timing.ensure_timed(other, self.root))
            self.assertEqual(other.read_bytes(), model())

    def test_a_model_that_cannot_be_patched_still_loads_untimed(self):
        self.model.write_bytes(model(extra_ceil=True))
        with self.assertLogs('akousousin_app.voice_timing', 'WARNING'):
            self.assertFalse(voice_timing.ensure_timed(self.model, self.root))
        self.assertEqual(self.model.read_bytes(), model(extra_ceil=True))


VOICE = os.environ.get('AKOUSOUSIN_TEST_VOICE', '')


@unittest.skipUnless(VOICE and Path(VOICE).is_file(), 'set AKOUSOUSIN_TEST_VOICE to a Piper .onnx voice')
class RealVoiceTests(unittest.TestCase):
    def test_a_patched_piper_voice_reports_durations_with_the_same_audio(self):
        import numpy as np
        import onnxruntime
        original = Path(VOICE).read_bytes()
        patched = voice_timing.with_durations(original)
        self.assertEqual(len(patched) - len(original), 18)
        ids = np.array([[1, 0, 20, 0, 59, 0, 40, 0, 2]], dtype=np.int64)
        args = {'input': ids, 'input_lengths': np.array([ids.shape[1]], dtype=np.int64),
                'scales': np.array([0, 1, 0], dtype=np.float32)}
        before = onnxruntime.InferenceSession(original).run(None, args)
        after = onnxruntime.InferenceSession(patched).run(None, args)
        self.assertEqual((len(before), len(after)), (1, 2))
        np.testing.assert_array_equal(before[0], after[0])
        frames = after[1].squeeze()
        self.assertEqual(frames.shape, (ids.shape[1],))


if __name__ == '__main__':
    unittest.main()
