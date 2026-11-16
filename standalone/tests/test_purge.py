# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from akousousin_app import linux_bundle as bundle
from akousousin_app import purge


@unittest.skipUnless(os.name == 'posix', 'Linux purge')
class PurgeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.data, self.config = self.root / 'data', self.root / 'config'
        env = patch.dict(os.environ, {'HOME': str(self.root), 'XDG_DATA_HOME': str(self.data),
                                      'XDG_CONFIG_HOME': str(self.config)})
        env.start()
        self.addCleanup(env.stop)
        for p in (patch('akousousin_app.runtime.call', return_value=None),
                  patch('akousousin_app.speech_dispatcher.configure')):
            p.start()
            self.addCleanup(p.stop)
        self.settings = self.config / 'Akousousin/settings.json'
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({}))
        (self.data / 'Akousousin/voices/en').mkdir(parents=True)
        (self.data / 'Akousousin/models/whisper/small').mkdir(parents=True)
        self.keep = self.data / 'applications/someone-else.desktop'
        self.keep.parent.mkdir(parents=True)
        self.keep.write_text('[Desktop Entry]\n')
        (self.data / 'applications/akousousin-read-selection.desktop').write_text('[Desktop Entry]\n')
        (self.data / 'applications/org.akousousin.Akousousin.Launcher.desktop').write_text(
            '[Desktop Entry]\n' + bundle.MARKER + '\n')
        source = self.root / 'source'
        (source / 'resources').mkdir(parents=True)
        (source / 'resources/build.json').write_text(json.dumps({'distribution': 'linux-tar'}))
        (source / 'resources/akousousin.png').write_bytes(b'icon')
        (source / 'akousousin').write_text('#!/bin/sh\nexit 0\n')
        (source / 'akousousin').chmod(0o755)
        self.prefix = self.root / '.local'
        self.target = bundle.install(source, self.prefix, self.data)

    def test_removes_application_data_and_settings(self):
        problems = purge.purge(self.settings, bundle_prefix=self.prefix, report=lambda _: None)
        self.assertEqual(problems, [])
        self.assertFalse(self.target.exists())
        self.assertFalse((self.prefix / 'bin/akousousin').exists())
        self.assertFalse((self.data / 'Akousousin').exists())
        self.assertFalse((self.config / 'Akousousin').exists())
        self.assertEqual(sorted(p.name for p in (self.data / 'applications').iterdir()), ['someone-else.desktop'])

    def test_one_failure_does_not_stop_the_rest(self):
        with patch('akousousin_app.runtime.call', side_effect=OSError('socket')):
            problems = purge.purge(self.settings, bundle_prefix=self.prefix, report=lambda _: None)
        self.assertEqual(len(problems), 1)
        self.assertFalse((self.data / 'Akousousin').exists())
        self.assertFalse(self.target.exists())

    def test_wine_registration_restored_when_prefix_exists(self):
        prefix = self.root / 'wineprefix'
        prefix.mkdir()
        with patch('akousousin_app.purge.Installer') as installer:
            purge.purge(self.settings, wine_prefix=str(prefix), bundle_prefix=self.prefix, report=lambda _: None)
        installer.return_value.uninstall.assert_called_once()


if __name__ == '__main__':
    unittest.main()
