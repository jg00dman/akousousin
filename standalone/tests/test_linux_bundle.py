# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from akousousin_app import linux_bundle as bundle


@unittest.skipUnless(os.name == 'posix', 'Linux bundle installer')
class BundleTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.source = self.root / 'source'
        (self.source / 'resources').mkdir(parents=True)
        (self.source / 'resources/build.json').write_text(json.dumps({'distribution': 'linux-tar'}))
        (self.source / 'resources/akousousin.png').write_bytes(b'icon')
        (self.source / 'akousousin').write_text('#!/bin/sh\nexit 0\n')
        (self.source / 'akousousin').chmod(0o755)
        self.prefix, self.data = self.root / 'prefix with spaces', self.root / 'data'

    def install(self):
        return bundle.install(self.source, self.prefix, self.data)

    def test_install_upgrade_uninstall_preserves_user_data_and_modifications(self):
        target = self.install()
        launcher, desktop, icon, reading = bundle.locations(self.prefix, self.data)
        self.assertTrue(os.access(launcher, os.X_OK))
        self.assertIn('NoDisplay=false', desktop.read_text())
        self.assertIn(str(target), launcher.read_text())
        from akousousin_app.desktop_identity import ensure_desktop_entry
        before = desktop.read_bytes()
        ensure_desktop_entry([target / 'akousousin', '--configure'], data_home=self.data)
        self.assertEqual(desktop.read_bytes(), before)
        models = self.data / 'Akousousin/models'; models.mkdir(parents=True)
        (models / 'keep').write_bytes(b'cached')
        (self.source / 'akousousin').write_text('#!/bin/sh\nexit 1\n')
        self.install()
        self.assertIn('exit 1', (target / 'akousousin').read_text())
        launcher.write_text('user custom launcher')
        bundle.uninstall(target)
        self.assertFalse(target.exists())
        self.assertEqual(launcher.read_text(), 'user custom launcher')
        self.assertFalse(desktop.exists())
        self.assertFalse(icon.exists())
        self.assertEqual((models / 'keep').read_bytes(), b'cached')

    def test_uninstall_restores_previous_appimage_desktop_entry(self):
        desktop = bundle.locations(self.prefix, self.data)[1]
        desktop.parent.mkdir(parents=True)
        old = ('[Desktop Entry]\n' + bundle.MARKER + '\nExec=/old.AppImage\n').encode()
        desktop.write_bytes(old)
        target = self.install()
        self.install()  # An upgrade must preserve the original backup.
        bundle.uninstall(target)
        self.assertEqual(desktop.read_bytes(), old)

    def test_rejects_unowned_file_without_partial_installation(self):
        launcher = bundle.locations(self.prefix, self.data)[0]
        launcher.parent.mkdir(parents=True)
        launcher.write_text('user launcher')
        with self.assertRaisesRegex(RuntimeError, 'unowned'):
            self.install()
        self.assertFalse((self.prefix / 'lib/akousousin').exists())
        self.assertEqual(launcher.read_text(), 'user launcher')

    def test_failed_upgrade_rolls_back_previous_application_and_menu(self):
        target = self.install()
        original = (target / 'akousousin').read_bytes()
        launcher = bundle.locations(self.prefix, self.data)[0]
        original_launcher = launcher.read_bytes()
        write = bundle.atomic_write
        calls = []
        def fail_once(path, *args):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('disk full')
            return write(path, *args)
        (self.source / 'akousousin').write_text('replacement')
        with patch.object(bundle, 'atomic_write', side_effect=fail_once):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.install()
        self.assertEqual((target / 'akousousin').read_bytes(), original)
        self.assertEqual(launcher.read_bytes(), original_launcher)
        self.assertFalse(list((self.prefix / 'lib').glob('.akousousin-stage-*')))
