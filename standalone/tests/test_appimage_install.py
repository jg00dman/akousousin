# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from akousousin_app import appimage_install as integration, updates
from akousousin_app.desktop_identity import APP_ID, ensure_desktop_entry


class AppImageInstallTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / 'Downloads/AKS trial.AppImage'
        self.source.parent.mkdir()
        self.source.write_bytes(b'current AppImage')
        self.source.chmod(0o755)
        self.config = self.root / 'settings.json'
        self.resources = self.root / 'resources'; self.resources.mkdir()
        (self.resources / 'akousousin.png').write_bytes(b'icon')
        (self.resources / 'build.json').write_text('{"distribution":"appimage"}')
        for context in (patch.dict(os.environ, {'APPIMAGE': str(self.source),
                            'XDG_DATA_HOME': str(self.root / 'data'), 'XDG_STATE_HOME': str(self.root / 'state')}),
                        patch.object(integration.resources, 'root', return_value=self.resources),
                        patch('akousousin_app.speech_dispatcher.run_setup')):
            context.start(); self.addCleanup(context.stop)

    def test_visible_menu_uses_persistent_icon_and_survives_identity_refresh(self):
        entry = integration.create_menu_entry()
        text = entry.read_text()
        self.assertIn('NoDisplay=false', text)
        self.assertIn('"' + str(self.source) + '" "--configure"', text)
        icon = self.root / 'data/Akousousin/icons/akousousin.png'
        self.assertEqual(icon.read_bytes(), b'icon')
        self.assertIn('Icon=' + str(icon), text)
        ensure_desktop_entry()
        self.assertEqual(entry.read_text(), text)

    def test_custom_hidden_identity_is_preserved_with_separate_visible_shortcut(self):
        entry = self.root / 'data/applications' / (APP_ID + '.desktop')
        entry.parent.mkdir(parents=True)
        original = '[Desktop Entry]\nType=Application\nName=Custom\nNoDisplay=true\nExec=/custom\n'
        entry.write_text(original)
        shortcut = integration.create_menu_entry()
        self.assertNotEqual(shortcut, entry)
        self.assertEqual(entry.read_text(), original)
        self.assertIn('NoDisplay=false', shortcut.read_text())

    @patch.object(integration.time, 'sleep')
    @patch.object(integration.subprocess, 'Popen')
    @patch.object(integration.subprocess, 'run')
    @patch.object(integration.runtime, 'call', return_value=None)
    def test_move_keeps_original_until_verified_refresh_and_relaunch(self, call, run, launch, sleep):
        target = integration.recommended_path()
        self.assertTrue(integration.needs_move())
        def refreshed(command, **kwargs):
            self.assertTrue(self.source.exists())
            self.assertEqual(target.read_bytes(), self.source.read_bytes())
            self.assertIn('--refresh-registrations', command)
            self.assertEqual(kwargs['env']['APPIMAGE'], str(target))
        run.side_effect = refreshed
        integration.install(self.config)
        self.assertFalse(self.source.exists())
        self.assertEqual(target.read_bytes(), b'current AppImage')
        self.assertTrue(target.stat().st_mode & 0o100)
        self.assertEqual(launch.call_args.args[0][0], str(target))
        entry = self.root / 'data/applications' / (APP_ID + '.desktop')
        self.assertIn(str(target), entry.read_text())
        with patch.dict(os.environ, {'APPIMAGE': str(target)}):
            self.assertFalse(integration.needs_move())

    def test_existing_destination_requires_explicit_replacement(self):
        target = integration.recommended_path(); target.parent.mkdir(parents=True)
        target.write_bytes(b'previous AppImage')
        with self.assertRaisesRegex(RuntimeError, 'confirm'):
            integration.install(self.config)
        self.assertEqual(target.read_bytes(), b'previous AppImage')
        self.assertTrue(self.source.exists())

    @patch.object(integration.time, 'sleep')
    @patch.object(integration.subprocess, 'Popen')
    @patch.object(integration.subprocess, 'run')
    @patch.object(integration.runtime, 'call', return_value=None)
    def test_failed_registration_restores_existing_target_and_retains_download(self, call, run, launch, sleep):
        target = integration.recommended_path(); target.parent.mkdir(parents=True)
        target.write_bytes(b'previous AppImage')
        run.side_effect = [RuntimeError('registration failed'), Mock()]
        with self.assertRaisesRegex(RuntimeError, 'registration failed'):
            integration.install(self.config, replace=True)
        self.assertEqual(target.read_bytes(), b'previous AppImage')
        self.assertTrue(self.source.exists())
        launch.assert_not_called()
        self.assertEqual(list(target.parent.glob('.akousousin-install-*')), [])

    def test_other_package_formats_do_not_offer_relocation(self):
        with patch.object(updates, 'is_appimage', return_value=False):
            self.assertFalse(integration.needs_move())
            with self.assertRaisesRegex(RuntimeError, 'AppImage launch'):
                integration.install(self.config)

    @patch.object(integration.time, 'sleep')
    @patch.object(integration.subprocess, 'Popen')
    @patch.object(integration.subprocess, 'run')
    @patch.object(integration.runtime, 'call', return_value=None)
    def test_skipped_registration_does_not_block_move_and_retains_original(self, call, run, launch, sleep):
        def refreshed(*args, **kwargs):
            updates.save_update_state(self.config, registration_warnings=['Wine executable/AppImage is missing: /old-wine.AppImage'])
        run.side_effect = refreshed
        target = integration.install(self.config)
        self.assertEqual(target.read_bytes(), b'current AppImage')
        self.assertTrue(self.source.is_file())
        launch.assert_called_once()
        warning = updates.completed_update(self.config)
        self.assertIn('missing', warning)
        self.assertIn(str(self.source), warning)

    def test_declining_prompt_keeps_application_and_menu_unchanged(self):
        from akousousin_app.panel import Panel
        panel = Panel.__new__(Panel)
        panel.busy = panel.updating = False
        panel.root = Mock()
        with patch('akousousin_app.panel.messagebox.askyesno', return_value=False), \
                patch.object(integration, 'install') as install:
            panel.offer_appimage_install()
        install.assert_not_called()
        self.assertTrue(self.source.exists())
        self.assertFalse((self.root / 'data/applications').exists())
