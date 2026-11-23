# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Start at login, settings defaults for a ready app, and loading at controller start."""
import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from akousousin_app import settings, startup
from akousousin_app.controller import Sessions
from akousousin_app.desktop_identity import MARKER


@unittest.skipIf(os.name == 'nt', 'XDG autostart is for Linux desktops')
class AutostartTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.root / 'config'),
                                              'XDG_DATA_HOME': str(self.root / 'data')})
        environment.start()
        self.addCleanup(environment.stop)
        self.command = patch('akousousin_app.startup.runtime.command',
                             side_effect=lambda *args: ['/opt/My Apps/Akousousin.AppImage', *args])
        self.command.start()
        self.addCleanup(self.command.stop)

    def test_enable_writes_a_marked_entry_that_starts_in_the_background(self):
        self.assertFalse(startup.enabled())
        self.assertTrue(startup.set_enabled(True))
        entry = startup.autostart_file().read_text()
        self.assertIn('Exec="/opt/My Apps/Akousousin.AppImage" "--background"', entry)
        self.assertIn(MARKER, entry)
        self.assertNotIn('Hidden=true', entry)
        self.assertTrue(Path(entry.split('Icon=')[1].splitlines()[0]).is_file())
        self.assertFalse(startup.set_enabled(False))
        self.assertFalse(startup.autostart_file().exists())

    def test_a_users_own_entry_is_never_changed(self):
        path = startup.autostart_file()
        path.parent.mkdir(parents=True)
        path.write_text('[Desktop Entry]\nExec=my-own-akousousin\n')
        self.assertFalse(startup.enabled())
        with self.assertRaises(RuntimeError):
            startup.enable()
        startup.disable()
        startup.refresh()
        self.assertEqual(path.read_text(), '[Desktop Entry]\nExec=my-own-akousousin\n')

    def test_refresh_follows_a_moved_program_only_when_enabled(self):
        startup.refresh()
        self.assertFalse(startup.autostart_file().exists())
        startup.enable()
        self.command.stop()
        with patch('akousousin_app.startup.runtime.command', side_effect=lambda *a: ['/home/me/Akousousin.AppImage', *a]):
            startup.refresh()
        self.command.start()
        self.assertIn('Exec="/home/me/Akousousin.AppImage" "--background"', startup.autostart_file().read_text())

    def test_uninstalling_a_bundle_removes_only_an_entry_that_points_into_it(self):
        startup.enable()
        startup.disable_if_inside('/somewhere/else')
        self.assertTrue(startup.enabled())
        startup.disable_if_inside('/opt/My Apps')
        self.assertFalse(startup.enabled())

    def test_purge_removes_the_login_entry(self):
        from akousousin_app import purge
        startup.enable()
        path = self.root / 'config/Akousousin/settings.json'
        with patch('akousousin_app.purge.runtime.call'), patch('akousousin_app.purge.bundle_target', return_value=None):
            purge.purge(path, report=lambda _: None)
        self.assertFalse(startup.autostart_file().exists())


class ReadyDefaultsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'settings.json'

    def test_new_users_get_models_loaded_and_kept(self):
        config = settings.load(self.path)
        self.assertTrue(config['preload'])
        self.assertEqual(config['idle_timeout'], 0)
        self.assertTrue(config['stt_keep_loaded'])
        self.assertFalse(config['login_offered'])

    def test_old_five_minute_default_becomes_never_once(self):
        self.path.write_text(json.dumps({'version': 1, 'idle_timeout': 300}))
        config = settings.load(self.path)
        self.assertEqual((config['idle_timeout'], config['version']), (0, 2))
        settings.save(self.path, dict(config, idle_timeout=300))
        self.assertEqual(settings.load(self.path)['idle_timeout'], 300)  # a later choice is kept

    def test_a_chosen_timeout_survives_the_upgrade(self):
        self.path.write_text(json.dumps({'version': 1, 'idle_timeout': 900}))
        self.assertEqual(settings.load(self.path)['idle_timeout'], 900)


class GetReadyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.path = root / 'settings.json'
        voice = root / 'voice.onnx'
        voice.touch()
        self.config = json.loads(json.dumps(settings.DEFAULTS))
        self.config['voices'] = {self.config['voice']: {'path': str(voice)}}
        settings.save(self.path, self.config)
        with patch('akousousin_app.controller.Service', return_value=Mock()):
            self.state = Sessions(self.path)
        self.state.input = Mock()

    def ready(self, installed=True):
        with patch('akousousin_backend.models.installed', return_value=installed):
            self.state.get_ready()

    @unittest.skipIf(os.name == 'nt', 'dictation is Linux-only')
    def test_loads_voice_and_dictation_at_start(self):
        self.ready()
        self.state.service.start.assert_called_once_with(5000)
        self.state.input.prepare.assert_called_once_with()
        self.assertFalse(self.state.input_owned, 'loading must not keep a session-started controller alive')

    def test_when_first_used_loads_nothing(self):
        settings.save(self.path, dict(self.config, preload=False))
        self.ready()
        self.state.service.start.assert_not_called()
        self.state.input.prepare.assert_not_called()

    def test_missing_voice_and_model_are_skipped_without_error(self):
        settings.save(self.path, dict(self.config, voices={}))
        self.ready(installed=False)
        self.state.service.start.assert_not_called()
        self.state.input.prepare.assert_not_called()
        self.assertIsNone(self.state.error)

    def test_dictation_already_running_is_not_an_error(self):
        self.state.input.prepare.side_effect = BlockingIOError
        self.ready()
        self.assertIsNone(self.state.error)

    def test_background_start_keeps_the_controller_running(self):
        self.state.request({'command': 'background'})
        self.assertTrue(self.state.independent)


if __name__ == '__main__':
    unittest.main()
