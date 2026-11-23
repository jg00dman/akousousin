# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Whisper's repetition safeguard must be able to act on dictated phrases.

A short phrase padded to Whisper's 30 s window can make greedy decoding
repeat itself ("Okay. Okay. …"). Whisper's defence is to notice the
repetition (the text compresses too well) and decode again with a little
randomness. These tests run faster-whisper's real fallback logic with a
stand-in model that loops on its greedy attempt.
"""
import importlib.util
import inspect
import logging
import unittest
from unittest.mock import Mock

from akousousin_backend.recognition import TEMPERATURES, decode_options, decoding_summary

LOOP = ['Okay.'] * 29


class LoopingModel:
    """Greedy decoding loops; any sampled attempt ends after one word."""
    def __init__(self):
        self.temperatures = []

    def generate(self, encoder_output, prompts, **options):
        temperature = options.get('sampling_temperature', 0.0)
        self.temperatures.append(temperature)
        tokens = LOOP if temperature == 0.0 else ['Okay.']
        return [Mock(sequences_ids=[tokens], scores=[-0.2 * len(tokens)], no_speech_prob=0.01)]


@unittest.skipUnless(importlib.util.find_spec('faster_whisper'), 'faster-whisper is not installed')
class FallbackTests(unittest.TestCase):
    def decode(self, settings):
        from faster_whisper.transcribe import TranscriptionOptions, WhisperModel
        defaults = inspect.signature(WhisperModel.transcribe).parameters
        fields = inspect.signature(TranscriptionOptions).parameters
        values = {name: defaults[name].default for name in fields if name in defaults}
        values.update({key: value for key, value in settings.items() if key in fields})
        temperature = settings['temperature']
        values['temperatures'] = list(temperature) if isinstance(temperature, tuple) else [temperature]
        whisper = WhisperModel.__new__(WhisperModel)
        whisper.model = LoopingModel()
        whisper.max_length = 448
        whisper.time_precision = 0.02
        whisper.logger = logging.getLogger('test')
        tokenizer = Mock(decode=lambda tokens: ' '.join(tokens))
        result, _logprob, temperature, ratio = whisper.generate_with_fallback(None, [], tokenizer, TranscriptionOptions(**values))
        return ' '.join(result.sequences_ids[0]), temperature, ratio, whisper.model.temperatures

    def test_one_attempt_keeps_the_loop(self):
        text, temperature, ratio, tried = self.decode(decode_options(fallback=False))
        self.assertEqual(text.count('Okay.'), 29)
        self.assertGreater(ratio, 2.4, 'Whisper detects the repetition but has nothing better to choose')
        self.assertEqual(tried, [0.0])

    def test_dictation_retries_and_recovers(self):
        text, temperature, ratio, tried = self.decode(decode_options())
        self.assertEqual(text, 'Okay.')
        self.assertEqual(temperature, 0.2)
        self.assertEqual(tried, [0.0, 0.2])


class SettingsTests(unittest.TestCase):
    def test_dictation_uses_whispers_safeguards_and_warm_up_does_not(self):
        live = decode_options()
        self.assertEqual(live['temperature'], TEMPERATURES)
        self.assertEqual(live['temperature'][0], 0.0)
        self.assertEqual((live['compression_ratio_threshold'], live['log_prob_threshold'], live['no_speech_threshold']),
                         (2.4, -1.0, 0.6))
        self.assertFalse(live['condition_on_previous_text'])
        self.assertEqual(decode_options(fallback=False)['temperature'], 0.0)

    def test_summary_keeps_the_worst_figures_for_diagnosis(self):
        segments = [Mock(temperature=0.0, compression_ratio=1.1, avg_logprob=-0.2, no_speech_prob=0.01),
                    Mock(temperature=0.2, compression_ratio=1.4, avg_logprob=-0.6, no_speech_prob=0.3)]
        self.assertEqual(decoding_summary(segments), {'segments': 2, 'temperature': 0.2, 'compression_ratio': 1.4,
                                                      'avg_logprob': -0.6, 'no_speech_prob': 0.3})
        self.assertEqual(decoding_summary([]), {'segments': 0})


if __name__ == '__main__':
    unittest.main()
