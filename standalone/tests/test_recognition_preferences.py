# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from akousousin_app import settings


class PreferenceTests(unittest.TestCase):
    def test_global_voice_can_change_without_replacing_language_preference(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            settings.save(path, dict(settings.DEFAULTS, voice='one', voices={
                'one':{'language':'en_US'}, 'two':{'language':'en_US'}}, language_voices={'en_US':'one'}))
            settings.select_voice(path, 'two', set_language=False)
            saved = settings.load(path)
            self.assertEqual(saved['voice'], 'two')
            self.assertEqual(saved['language_voices']['en_US'], 'one')

    def test_model_lifetime_defaults_and_migration_preserve_custom_timeouts(self):
        self.assertEqual(settings.DEFAULTS['idle_timeout'], 0)
        self.assertEqual(settings.DEFAULTS['stt_idle_timeout'], 0)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            path.write_text(json.dumps({'idle_timeout':300, 'stt_idle_timeout':3600}))
            value = settings.load(path)
            self.assertEqual((value['idle_timeout'], value['stt_idle_timeout']), (0, 0))
            path.write_text(json.dumps({'idle_timeout':120, 'stt_idle_timeout':600}))
            value = settings.load(path)
            self.assertEqual((value['idle_timeout'], value['stt_idle_timeout']), (120, 600))
            # Once the new policy is saved, even former default values are explicit.
            settings.save(path, dict(settings.DEFAULTS, idle_timeout=300, stt_idle_timeout=3600))
            value = settings.load(path)
            self.assertEqual((value['idle_timeout'], value['stt_idle_timeout']), (300, 3600))

    def test_legacy_default_moves_to_locale_and_compact_model(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            path.write_text(json.dumps({'stt_model':'small', 'stt_language':'', 'stt_idle_timeout':300}))
            with patch('akousousin_app.settings.system_language', return_value='en'):
                value = settings.load(path)
            self.assertEqual((value['stt_model'], value['stt_language']), ('base.en', 'en'))
            self.assertEqual(value['stt_idle_timeout'], 0)
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
