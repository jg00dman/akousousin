# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from akousousin_app import __version__, updates


class UpdateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        state = patch.dict(os.environ, {'XDG_STATE_HOME': str(self.root / 'state'),
                                       'LOCALAPPDATA': str(self.root / 'state')})
        state.start(); self.addCleanup(state.stop)
        self.image = self.root / 'Akousousin.AppImage'
        self.image.write_bytes(b'previous image')
        self.image.chmod(0o755)
        (self.root / 'build.json').write_text(json.dumps({'distribution': 'appimage'}))
        resource_root = patch.object(updates.resources, 'root', return_value=self.root)
        resource_root.start(); self.addCleanup(resource_root.stop)
        self.payload = b'verified replacement image'
        self.update = {'version': __version__, 'url': updates.RELEASES + '/download/v0.7.0b1/Akousousin-x86_64.AppImage',
                       'size': len(self.payload), 'sha256': hashlib.sha256(self.payload).hexdigest()}

    def release(self, tag, **options):
        asset = {'name': 'Akousousin-x86_64.AppImage', 'size': len(self.payload),
                 'digest': 'sha256:' + self.update['sha256'], 'browser_download_url': self.update['url']}
        return dict(tag_name=tag, assets=[asset], **options)

    def test_versioned_betas_and_stable_versions_compare_without_run_number_downgrades(self):
        releases = [self.release('standalone-beta-0.6.0b3-123-1', prerelease=True),
                    self.release('v0.6.0'), self.release('standalone-beta-999999-1'),
                    self.release('v9.0.0', draft=True), self.release('v0.5.0')]
        with patch.object(updates.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(releases).encode())):
            result = updates.check('0.6.0b2', windows=False)
        self.assertEqual(result['version'], '0.6.0')
        self.assertIsNone(updates.release_version('standalone-beta-999999-1'))

    def test_no_update_for_equal_or_older_versions_and_unrelated_assets(self):
        unrelated = self.release('v9.0.0')
        unrelated['assets'][0]['name'] = 'whisper.tar.gz'
        releases = [self.release('v0.6.0b2'), self.release('v0.5.0'), unrelated]
        with patch.object(updates.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(releases).encode())):
            self.assertIsNone(updates.check('0.6.0b2', windows=False))

    def test_wrong_repository_and_unverified_assets_are_not_offered(self):
        release = self.release('v9.0.0')
        release['assets'][0]['browser_download_url'] = 'https://example.com/other.AppImage'
        missing = self.release('v8.0.0')
        missing['assets'][0]['digest'] = None
        with patch.object(updates.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps([release, missing]).encode())):
            self.assertIsNone(updates.check('0.6.0b2', windows=False))

    def test_verified_download_is_staged_without_replacing_running_image(self):
        with patch.object(updates.urllib.request, 'urlopen', return_value=io.BytesIO(self.payload)):
            stage = updates.download(self.update, self.root)
        self.assertEqual(stage.read_bytes(), self.payload)
        self.assertTrue(stage.stat().st_mode & 0o100)
        self.assertEqual(self.image.read_bytes(), b'previous image')

    def test_corruption_and_truncation_remove_stage_and_leave_existing_image(self):
        for payload in (b'corrupt', self.payload[:-1], self.payload + b'excess'):
            with patch.object(updates.urllib.request, 'urlopen', return_value=io.BytesIO(payload)):
                with self.assertRaises(ValueError):
                    updates.download(self.update, self.root)
            self.assertEqual(list(self.root.glob('.akousousin-update-*')), [])
            self.assertEqual(self.image.read_bytes(), b'previous image')

    @patch.object(updates.subprocess, 'Popen')
    @patch.object(updates.subprocess, 'run')
    @patch.object(updates.runtime, 'call', return_value=None)
    def test_install_stops_after_download_replaces_at_same_path_and_refreshes_registration(self, call, run, launch):
        def received(*args, **kwargs):
            self.assertEqual(call.call_count, 0)
            return io.BytesIO(self.payload)
        with patch.dict(os.environ, {'APPIMAGE': str(self.image)}), \
                patch.object(updates.urllib.request, 'urlopen', side_effect=received), \
                patch.object(updates.time, 'sleep'):
            backup = updates.install(self.update, self.root / 'settings.json')
        self.assertEqual(self.image.read_bytes(), self.payload)
        self.assertEqual(backup.read_bytes(), b'previous image')
        self.assertEqual(call.call_args_list[0].args[1], {'command': 'quit', 'update_pid': os.getpid()})
        self.assertIn('--refresh-registrations', run.call_args.args[0])
        self.assertIn('--configure', launch.call_args.args[0])
        self.assertEqual(launch.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')

    @patch.object(updates.subprocess, 'Popen')
    @patch.object(updates.subprocess, 'run')
    @patch.object(updates.runtime, 'call', return_value=None)
    def test_failed_refresh_restores_previous_image_and_registration(self, call, run, launch):
        run.side_effect = [subprocess.CalledProcessError(1, 'registration'), Mock()]
        with patch.dict(os.environ, {'APPIMAGE': str(self.image)}), \
                patch.object(updates.urllib.request, 'urlopen', return_value=io.BytesIO(self.payload)):
            with self.assertRaises(subprocess.CalledProcessError):
                updates.install(self.update, self.root / 'settings.json')
        self.assertEqual(self.image.read_bytes(), b'previous image')
        self.assertEqual(run.call_count, 2)
        launch.assert_not_called()
        self.assertEqual(call.call_args.args[1], {'command': 'wake'})

    def test_initial_beta_preference_follows_version_and_then_preserves_choice(self):
        from akousousin_app import settings
        path = self.root / 'settings.json'
        with patch('akousousin_app.__version__', '0.7.0'):
            self.assertFalse(settings.load(path)['update_betas'])
        with patch('akousousin_app.__version__', '0.7.0b2'):
            path.write_text('{}')
            updates.resources.bootstrap(path)
            self.assertTrue(json.loads(path.read_text())['update_betas'])
            self.assertTrue(settings.load(path)['update_betas'])
            config = settings.load(path)
            config['update_betas'] = False
            settings.save(path, config)
            self.assertFalse(settings.load(path)['update_betas'])

    def test_stable_only_does_not_downgrade_installed_beta(self):
        releases = [self.release('v0.6.0'), self.release('v0.7.0b2', prerelease=True),
                    self.release('v0.8.0rc1'), self.release('v0.7.0')]
        with patch.object(updates.urllib.request, 'urlopen', side_effect=lambda *a, **kw: io.BytesIO(json.dumps(releases).encode())):
            self.assertEqual(updates.check('0.7.0b1', include_beta=False)['version'], '0.7.0')
            self.assertEqual(updates.check('0.7.0b1', include_beta=True)['version'], '0.8.0rc1')
            self.assertIsNone(updates.check('0.8.0b1', include_beta=False))

    def test_github_prerelease_flag_is_respected_even_for_stable_tag(self):
        releases = [self.release('v0.8.0', prerelease=True)]
        with patch.object(updates.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(releases).encode())):
            self.assertIsNone(updates.check('0.7.0b1', include_beta=False))

    def test_source_flatpak_and_distro_builds_cannot_enable_self_updating(self):
        with patch.dict(os.environ, {'APPIMAGE': str(self.image)}, clear=False):
            self.assertTrue(updates.is_appimage())
            with patch.dict(os.environ, {'FLATPAK_ID': 'org.akousousin.Akousousin'}):
                self.assertFalse(updates.is_appimage())
            for distribution in ('flatpak', 'deb', 'source'):
                (self.root / 'build.json').write_text(json.dumps({'distribution': distribution}))
                self.assertFalse(updates.is_appimage())
                with patch.object(updates.urllib.request, 'urlopen') as network:
                    self.assertIsNone(updates.perform_check(self.root / 'settings.json'))
                    network.assert_not_called()

    def test_weekly_check_persists_and_reminder_does_not_install(self):
        from akousousin_app import settings
        path = self.root / 'settings.json'
        settings.save(path, dict(settings.DEFAULTS))
        candidate = dict(self.update, version='0.8.0b1')
        def thread(**kwargs):
            return Mock(start=kwargs['target'])
        with patch.object(updates, 'is_appimage', return_value=True), \
                patch.object(updates.time, 'time', return_value=2000000), \
                patch.object(updates.threading, 'Thread', side_effect=thread), \
                patch.object(updates, 'check', return_value=candidate) as check, \
                patch.object(updates, 'install') as install:
            monitor = updates.UpdateMonitor(path)
            self.assertIsNone(monitor.tick(quiet=True))
            check.assert_called_once_with(include_beta=True)
            self.assertEqual(monitor.tick()['version'], '0.8.0b1')
            updates.remind_later(path)
            self.assertIsNone(updates.UpdateMonitor(path).tick())
            self.assertEqual(check.call_count, 1)
            config = settings.load(path); config['update_betas'] = False; settings.save(path, config)
            self.assertIsNone(updates.available_update(path))
            install.assert_not_called()
        with patch.object(updates, 'is_appimage', return_value=True), \
                patch.object(updates.time, 'time', return_value=2000000 + updates.WEEK + 1), \
                patch.object(updates.threading, 'Thread', side_effect=thread), \
                patch.object(updates, 'check', return_value=None) as check:
            updates.UpdateMonitor(path).tick()
            check.assert_called_once_with(include_beta=False)

    def test_disabling_weekly_checks_leaves_manual_check_available(self):
        from akousousin_app import settings
        path = self.root / 'settings.json'
        settings.save(path, dict(settings.DEFAULTS, update_weekly=False, update_betas=False))
        with patch.object(updates, 'is_appimage', return_value=True), \
                patch.object(updates, 'check', return_value=None) as check:
            self.assertIsNone(updates.UpdateMonitor(path).tick())
            check.assert_not_called()
            updates.perform_check(path)
            check.assert_called_once_with(include_beta=False)

    def test_restart_warning_stays_visible_and_success_is_shown_once(self):
        path = self.root / 'settings.json'
        phases = []
        original = updates.Transfer.phase
        def phase(progress, text, **kwargs):
            phases.append(text)
            return original(progress, text, **kwargs)
        with patch.dict(os.environ, {'APPIMAGE': str(self.image)}), \
                patch.object(updates.urllib.request, 'urlopen', return_value=io.BytesIO(self.payload)), \
                patch.object(updates.runtime, 'call', return_value=None), \
                patch.object(updates.subprocess, 'run'), \
                patch.object(updates.subprocess, 'Popen'), \
                patch.object(updates.Transfer, 'phase', phase), \
                patch.object(updates.time, 'sleep') as pause:
            updates.install(self.update, path)
        self.assertEqual(phases, ['Downloading update', 'Verifying update…',
                                 'Applying update… Speech will stop briefly.',
                                 'Update ready — restarting Akousousin…'])
        pause.assert_called_once_with(3)
        self.assertIn(__version__, updates.completed_update(path))
        self.assertIsNone(updates.completed_update(path))

    def test_packaged_and_project_versions_agree(self):
        import tomllib
        project = Path(__file__).resolve().parents[1] / 'pyproject.toml'
        self.assertEqual(tomllib.loads(project.read_text())['project']['version'], __version__)

    def test_declining_update_does_not_install_or_stop_speech(self):
        from akousousin_app.panel import Panel
        panel = Panel.__new__(Panel)
        panel.busy = 0
        panel.update_status = Mock()
        panel.root = Mock()
        panel.path = self.root / 'settings.json'
        panel.updating = False
        panel.worker = lambda function, success: success(function())
        with patch.object(updates, 'is_appimage', return_value=True), \
                patch('akousousin_app.panel.updates.perform_check', return_value=self.update), \
                patch('akousousin_app.panel.messagebox.askyesno', return_value=False), \
                patch('akousousin_app.panel.updates.install') as install, \
                patch.object(updates.runtime, 'call') as call:
            panel.check_updates()
        install.assert_not_called()
        call.assert_not_called()

    def test_refresh_updates_only_existing_dispatcher_launcher(self):
        from akousousin_app import settings
        from akousousin_app.speech_dispatcher import dispatcher_paths
        path = self.root / 'settings.json'
        settings.save(path, dict(settings.DEFAULTS))
        with patch.dict(os.environ, {'XDG_DATA_HOME': str(self.root / 'data')}), \
                patch('akousousin_app.speech_dispatcher.install') as register:
            updates.refresh_registrations(path)
            register.assert_not_called()
            _, launcher, _ = dispatcher_paths()
            launcher.parent.mkdir(parents=True, exist_ok=True)
            launcher.write_text('#!/bin/sh\nexec /old.AppImage --speech-dispatcher\n')
            updates.refresh_registrations(path)
            register.assert_called_once_with(path, set_default=False)

    def test_refresh_does_not_reinstall_uninstalled_or_deleted_prefixes(self):
        active, removed = self.root / 'active', self.root / 'removed'
        for prefix in (active, removed):
            prefix.mkdir()
            (prefix / 'system.reg').touch()
        records = [{'prefix': str(prefix), 'wine': 'wine64'}
                   for prefix in (active, removed, self.root / 'deleted')]
        current, uninstalled = Mock(), Mock()
        current.manifest.is_file.return_value = True
        uninstalled.manifest.is_file.return_value = False
        with patch.object(updates.settings, 'load', return_value={'registrations': records}), \
                patch('akousousin_app.install.Installer', side_effect=[current, uninstalled]) as installer:
            updates.refresh_registrations(self.root / 'settings.json')
        self.assertEqual(installer.call_count, 2)
        current.install.assert_called_once()
        uninstalled.install.assert_not_called()
