# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from akousousin_app import settings


class PreferenceTests(unittest.TestCase):
    def test_legacy_default_moves_to_locale_and_compact_model(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            path.write_text(json.dumps({'stt_model':'small', 'stt_language':'', 'stt_idle_timeout':300}))
            with patch('akousousin_app.settings.system_language', return_value='en'):
                value = settings.load(path)
            self.assertEqual((value['stt_model'], value['stt_language']), ('base.en', 'en'))
            self.assertEqual(value['stt_idle_timeout'], 3600)
            self.assertTrue(value['stt_keep_loaded'])

    def test_explicit_quality_language_and_current_auto_survive(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            for stored in ({'stt_model':'small', 'stt_language':'de'},
                           {'stt_model':'base', 'stt_language':'', 'stt_config_version':2},
                           {'stt_model':'turbo', 'stt_language':'fr'}):
                path.write_text(json.dumps(stored))
                value = settings.load(path)
                self.assertEqual(value['stt_model'], stored['stt_model'])
                self.assertEqual(value['stt_language'], stored['stt_language'])

    def test_thread_count_and_warmth_are_validated(self):
        for fields in ({'stt_cpu_threads':0}, {'stt_cpu_threads':True}, {'stt_keep_loaded':'yes'}):
            with self.assertRaises(ValueError):
                settings.validate(dict(settings.DEFAULTS, **fields))
