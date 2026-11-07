# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import ast
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from akousousin_app.input_choices import LANGUAGES, discover_microphones, language_caption, language_choices, microphone_choices


class InputChoiceTests(unittest.TestCase):
    def test_search_uses_readable_names_and_codes(self):
        self.assertEqual(language_choices('German'), [('de', 'German (de)')])
        self.assertEqual(language_choices('de'), [('de', 'German (de)')])
        self.assertEqual(language_choices('Multilingual'), [('', 'Multilingual (auto) — detect once per session')])
        self.assertEqual(language_caption('en-GB'), 'English (en-GB)')
        self.assertGreater(len(language_choices()), 90)

    def test_language_codes_match_pinned_runtime_without_importing_inference(self):
        spec = importlib.util.find_spec('faster_whisper')
        if spec is None:
            self.skipTest('Recognition extra is not installed')
        source = Path(next(iter(spec.submodule_search_locations))) / 'tokenizer.py'
        parsed = ast.parse(source.read_text())
        codes = next(ast.literal_eval(item.value) for item in parsed.body if isinstance(item, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == '_LANGUAGE_CODES' for target in item.targets))
        self.assertEqual(set(LANGUAGES), set(codes))

    def test_microphones_have_default_and_readable_distinct_names_without_monitors(self):
        sources = [{'name': 'alsa-input', 'description': 'Built-in microphone'},
                   {'name': 'usb-input', 'description': 'USB microphone', 'monitor_of_sink': 4294967295},
                   {'name': 'other-usb', 'description': 'USB microphone'},
                   {'name': 'speaker.monitor', 'description': 'Speaker output'},
                   {'name': 'other-monitor', 'description': 'Another output', 'monitor_of_sink': 0}]
        choices = microphone_choices(sources, 'alsa-input')
        self.assertEqual(choices[0], ('', 'System default — Built-in microphone'))
        self.assertEqual(len(choices), 4)
        self.assertEqual(len({label for code, label in choices}), 4)
        self.assertNotIn('speaker.monitor', [code for code, label in choices])
        self.assertNotIn('other-monitor', [code for code, label in choices])

    def test_discovery_is_bounded_and_default_name_is_optional(self):
        with patch('akousousin_app.input_choices.subprocess.run') as run:
            run.side_effect = [Mock(stdout='[{"name":"mic","description":"Built-in microphone"}]'), Mock(stdout='mic\n')]
            self.assertEqual(discover_microphones()[0][1], 'System default — Built-in microphone')
            self.assertTrue(all(call.kwargs['timeout'] == 3 for call in run.call_args_list))
