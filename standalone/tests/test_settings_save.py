# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from akousousin_app import settings


class SaveTests(unittest.TestCase):
    def test_failed_replacement_preserves_settings_and_cleans_staging_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            settings.save(path, settings.DEFAULTS)
            before = path.read_bytes()
            with patch.object(Path, 'replace', side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):
                    settings.save(path, dict(settings.DEFAULTS, volume=.5))
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_windows_transient_lock_is_retried_with_unique_staging(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            legacy = path.with_suffix('.tmp')
            legacy.write_text('another writer')
            original = Path.replace
            attempts = []
            def replace(source, destination):
                attempts.append(source)
                if len(attempts) == 1:
                    raise PermissionError('temporarily locked')
                return original(source, destination)
            platform_os = Mock(wraps=os)
            platform_os.name = 'nt'
            with patch.object(settings, 'os', platform_os), patch.object(Path, 'replace', replace), patch.object(settings.time, 'sleep') as sleep:
                settings.save(path, settings.DEFAULTS)
            self.assertEqual(len(attempts), 2)
            sleep.assert_called_once_with(.05)
            self.assertNotEqual(attempts[0], legacy)
            self.assertEqual(legacy.read_text(), 'another writer')
            self.assertEqual(json.loads(path.read_text())['volume'], settings.DEFAULTS['volume'])


if __name__ == '__main__':
    unittest.main()
