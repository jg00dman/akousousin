# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

from akousousin_app.desktop_preferences import DesktopPreferences
from akousousin_app.desktop_input import Desktop
from akousousin_app.controller import Sessions
from akousousin_app import settings


class PreferencesTests(unittest.TestCase):
    def test_model_restore_only_reloads_opted_in_models_without_download_or_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            model = Path(folder) / 'voice.onnx'; model.write_bytes(b'model')
            settings.save(path, dict(settings.DEFAULTS, voice='test', voices={'test': {'path':str(model)}}))
            with patch('akousousin_app.controller.Service', return_value=Mock()):
                state = Sessions(path)
            state.request = Mock()
            state.restore_models()
            state.request.assert_not_called()
            state.desktop_preferences.update(speech_model_enabled=True, recognition_model_enabled=True)
            state.restore_models()
            self.assertEqual([call.args[0] for call in state.request.call_args_list],
                             [{'command':'start', 'allow_download':False}, {'command':'stt-prepare', 'allow_download':False}])
            self.assertFalse(state.input.status()['busy'])
            self.assertIsNone(state.input.capture)

    def test_private_atomic_state_survives_settings_save_and_recreation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            prefs = DesktopPreferences(path)
            prefs.update(dictation_enabled=True, reading_enabled=True, restore_token='opaque-token')
            settings.save(path, settings.DEFAULTS)
            saved = DesktopPreferences(path).load()
            self.assertTrue(saved['dictation_enabled'])
            self.assertTrue(saved['reading_enabled'])
            self.assertEqual(saved['restore_token'], 'opaque-token')
            if os.name != 'nt':
                self.assertEqual(prefs.path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(list(Path(folder).glob('*.desktop.json.*')))

    def test_late_approval_does_not_overwrite_explicit_disable(self):
        with tempfile.TemporaryDirectory() as folder:
            prefs = DesktopPreferences(Path(folder) / 'settings.json')
            stopped = threading.Event(); stopped.set()
            prefs.update(dictation_enabled=False)
            prefs.update(condition=lambda: not stopped.is_set(), dictation_enabled=True)
            self.assertFalse(prefs.load()['dictation_enabled'])

    def test_restore_only_opted_in_sessions_without_listening(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            settings.save(path, settings.DEFAULTS)
            with patch('akousousin_app.controller.Service', return_value=Mock()):
                state = Sessions(path)
            state.desktop_preferences.update(dictation_enabled=True, reading_enabled=True)
            state.input_request = Mock()
            state.selection.enable = Mock()
            state.restore_desktop_shortcuts()
            state.input_request.assert_called_once_with({'command':'stt-desktop-enable'})
            state.selection.enable.assert_called_once()
            state.closed = True
            state.input_request.reset_mock()
            state.restore_desktop_shortcuts()
            state.input_request.assert_not_called()

    def test_explicit_disable_survives_restart_but_quit_preserves_enabled(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            settings.save(path, settings.DEFAULTS)
            with patch('akousousin_app.controller.Service', return_value=Mock()):
                state = Sessions(path)
            state.desktop_preferences.update(dictation_enabled=True, reading_enabled=True, restore_token='token')
            state.input = Mock()
            state.input.status.return_value = {}
            state.selection = Mock()
            state.quit()
            saved = DesktopPreferences(path).load()
            self.assertTrue(saved['dictation_enabled'])
            self.assertTrue(saved['reading_enabled'])
            self.assertEqual(saved['restore_token'], 'token')
            state.closed = False
            state.request({'command': 'stt-desktop-disable'})
            state.request({'command': 'selection-shortcuts-disable'})
            saved = DesktopPreferences(path).load()
            self.assertFalse(saved['dictation_enabled'])
            self.assertFalse(saved['reading_enabled'])
            self.assertEqual(saved['restore_token'], '')


@unittest.skipUnless(importlib.util.find_spec('dbus_next'), 'Desktop dependency is not installed')
class PortalPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_shortcut_editor_uses_the_portal_and_reports_older_backends(self):
        from dbus_next import Variant
        desktop = Desktop.__new__(Desktop)
        desktop.enabled = True
        desktop.shortcuts = '/session'
        desktop.call = AsyncMock(side_effect=[[Variant('u', 2)], []])
        await desktop.edit_shortcuts()
        self.assertEqual(desktop.call.call_args.args[3], 'ConfigureShortcuts')
        self.assertEqual(desktop.call.call_args.args[-1], ['/session', '', {}])
        desktop.call = AsyncMock(return_value=[Variant('u', 1)])
        with self.assertRaisesRegex(RuntimeError, 'System Settings'):
            await desktop.edit_shortcuts()
        self.assertEqual(desktop.call.await_count, 1)

    async def test_tray_dictation_does_not_start_in_a_different_window(self):
        desktop = Desktop.__new__(Desktop)
        desktop.dictation = Mock()
        desktop.dictation.status.return_value = {'busy':False}
        desktop.preferences = None
        desktop.confirm_focus = AsyncMock(return_value=('other-editor', 2))
        await desktop.toggle_recording(expected_window='original-editor')
        desktop.dictation.start.assert_not_called()
        self.assertIn('editor changed', desktop.status)

    async def test_version_one_does_not_receive_unsupported_options(self):
        from dbus_next import Variant
        with tempfile.TemporaryDirectory() as folder:
            desktop = Desktop.__new__(Desktop)
            desktop.preferences = DesktopPreferences(Path(folder) / 'settings.json')
            desktop.stopping = threading.Event()
            desktop.session = AsyncMock(return_value='/remote')
            desktop.call = AsyncMock(return_value=[Variant('u', 1)])
            desktop.request = AsyncMock(side_effect=[{}, {'devices': Variant('u', 1)}])
            await desktop.keyboard_permission()
            options = desktop.request.call_args_list[0].args[-1]
            self.assertEqual(set(options), {'types'})
            self.assertTrue(desktop.preferences.load()['dictation_enabled'])

    async def test_single_use_token_is_consumed_and_rotated(self):
        from dbus_next import Variant
        with tempfile.TemporaryDirectory() as folder:
            prefs = DesktopPreferences(Path(folder) / 'settings.json')
            prefs.update(restore_token='old-token')
            desktop = Desktop.__new__(Desktop)
            desktop.preferences = prefs
            desktop.stopping = threading.Event()
            desktop.session = AsyncMock(return_value='/remote')
            desktop.call = AsyncMock(return_value=[Variant('u', 2)])
            requests = []
            async def request(interface, member, *args):
                requests.append((member, args))
                if member == 'SelectDevices':
                    options = args[-1]
                    self.assertEqual(options['persist_mode'].value, 2)
                    self.assertEqual(options['restore_token'].value, 'old-token')
                    self.assertEqual(prefs.load()['restore_token'], '')
                    return {}
                return {'devices':Variant('u', 1), 'restore_token':Variant('s', 'new-token')}
            desktop.request = request
            await desktop.keyboard_permission()
            self.assertTrue(prefs.load()['dictation_enabled'])
            self.assertEqual(prefs.load()['restore_token'], 'new-token')

    async def test_denied_permission_is_not_saved_as_enabled(self):
        from dbus_next import Variant
        with tempfile.TemporaryDirectory() as folder:
            desktop = Desktop.__new__(Desktop)
            desktop.preferences = DesktopPreferences(Path(folder) / 'settings.json')
            desktop.stopping = threading.Event()
            desktop.session = AsyncMock(return_value='/remote')
            desktop.call = AsyncMock(return_value=[Variant('u', 2)])
            desktop.request = AsyncMock(side_effect=[{}, {'devices':Variant('u', 0)}])
            with self.assertRaisesRegex(RuntimeError, 'permission'):
                await desktop.keyboard_permission()
            self.assertFalse(desktop.preferences.load()['dictation_enabled'])
