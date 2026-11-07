# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import os
import unittest
from unittest.mock import patch
from akousousin_backend.recognition_config import cpu_threads, default_model, system_language


class ConfigTests(unittest.TestCase):
    def test_locale_and_model_defaults(self):
        for locale, language, model in [('en_GB.UTF-8','en','base.en'), ('fr_FR.UTF-8','fr','base'),
                                        ('he_IL.UTF-8','he','base'), ('C.UTF-8','en','base.en')]:
            with patch.dict(os.environ, {'LANG':locale}, clear=True):
                self.assertEqual(system_language(), language)
                self.assertEqual(default_model(language), model)
        with patch.dict(os.environ, {'LANG':'en_US','LC_MESSAGES':'el_GR','LC_ALL':'de_DE'}):
            self.assertEqual(system_language(), 'de')

    def test_physical_thread_default_minimum_and_override(self):
        with patch('psutil.cpu_count', return_value=4) as physical:
            self.assertEqual(cpu_threads(), 4)
            physical.assert_called_with(logical=False)
        with patch('psutil.cpu_count', return_value=None), patch('os.cpu_count', return_value=None):
            self.assertEqual(cpu_threads(), 1)
        self.assertEqual(cpu_threads(2), 2)
        for invalid in (0, -1, True, 1.5, '2'):
            with self.assertRaises(ValueError):
                cpu_threads(invalid)

    def test_cli_download_defaults_follow_locale_and_auto_is_explicit(self):
        from akousousin_backend.recognition import main
        import tempfile
        for language, expected in [('en', 'base.en'), ('de', 'base')]:
            with tempfile.TemporaryDirectory() as folder, \
                    patch('akousousin_backend.recognition.system_language', return_value=language), \
                    patch('sys.argv', ['akousousin-whisper','--download-model','--models',folder]), \
                    patch('akousousin_backend.models.install') as install:
                main()
                self.assertEqual(install.call_args.args[0], expected)
        with tempfile.TemporaryDirectory() as folder, \
                patch('sys.argv', ['akousousin-whisper','--download-model','--language','auto','--models',folder]), \
                patch('akousousin_backend.models.install') as install:
            main()
            self.assertEqual(install.call_args.args[0], 'base')
