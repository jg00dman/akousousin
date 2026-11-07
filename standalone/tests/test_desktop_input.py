# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import asyncio
import threading
import time
import unittest
from unittest.mock import AsyncMock

from akousousin_app.desktop_input import Desktop, FocusGuard, focus_script, keysyms


class FocusTests(unittest.TestCase):
    def test_switch_away_and_back_invalidates_original_target(self):
        guard = FocusGuard()
        guard.report('editor', 0)
        target = guard.snapshot()
        guard.report('browser', 1)
        guard.report('editor', 2)
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            guard.check(target)

    def test_stale_and_lost_focus_are_rejected(self):
        guard = FocusGuard()
        guard.report('editor', 1)
        guard.updated = time.monotonic() - 4
        with self.assertRaises(RuntimeError):
            guard.snapshot()
        guard.report('editor', 2)
        guard.invalidate()
        guard.report('editor', 2)  # Delayed report must not restore old focus.
        with self.assertRaises(RuntimeError):
            guard.snapshot()

    def test_unicode_without_enter_tab_or_clipboard(self):
        symbols = keysyms('Hallo\tκόσμε\n€')
        self.assertIn(0x010003BA, symbols)
        self.assertIn(0x010020AC, symbols)
        self.assertNotIn(0xFF0D, symbols)
        self.assertNotIn(0xFF09, symbols)
        with self.assertRaises(ValueError):
            keysyms('hello\x1b')

    def test_focus_script_quotes_its_values(self):
        script = focus_script('org.example.Test', 'a"b')
        self.assertIn('workspace.windowActivated.connect', script)
        self.assertIn('"a\\"b"', script)
        self.assertNotIn('SERVICE', script)


class InsertionTests(unittest.IsolatedAsyncioTestCase):
    def desktop(self):
        desktop = Desktop.__new__(Desktop)
        desktop.enabled = True
        desktop.shortcut_down = False
        desktop.remote = '/session'
        desktop.guard = FocusGuard()
        desktop.guard.report('editor', 1)
        desktop.confirm_focus = AsyncMock()
        desktop.notify_keysym = AsyncMock()
        return desktop

    async def test_focus_change_stops_remaining_characters_and_releases_key(self):
        desktop = self.desktop()
        target = desktop.guard.snapshot()
        events = []
        async def call(symbol, state, **kwargs):
            events.append((symbol, state))
            if state == 1:
                desktop.guard.report('other window', 2)
            return []
        desktop.notify_keysym = call
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            await desktop.type_text('hello', target, threading.Event())
        self.assertEqual(events, [(ord('h'), 1), (ord('h'), 0)])

    async def test_cancelled_result_never_types(self):
        desktop = self.desktop()
        desktop.notify_keysym = AsyncMock()
        cancel = threading.Event(); cancel.set()
        with self.assertRaises(InterruptedError):
            await desktop.type_text('hello', desktop.guard.snapshot(), cancel)
        desktop.notify_keysym.assert_not_called()

    async def test_remote_error_still_releases_pressed_key(self):
        desktop = self.desktop()
        desktop.notify_keysym = AsyncMock(side_effect=[RuntimeError('session closed'), []])
        with self.assertRaisesRegex(RuntimeError, 'session closed'):
            await desktop.type_text('hi', desktop.guard.snapshot(), threading.Event())
        self.assertEqual(desktop.notify_keysym.await_count, 2)
        self.assertEqual(desktop.notify_keysym.call_args.args[-1], 0)

    async def test_keyboard_writes_are_ordered_with_one_final_reply(self):
        from types import SimpleNamespace
        from dbus_next import MessageFlag
        desktop = self.desktop()
        desktop.notify_keysym = Desktop.notify_keysym.__get__(desktop)
        desktop.bus = SimpleNamespace(send=AsyncMock())
        desktop.call = AsyncMock(return_value=[])
        await desktop.type_text('abc', desktop.guard.snapshot(), threading.Event())
        desktop.confirm_focus.assert_awaited_once()
        self.assertEqual(desktop.bus.send.await_count, 7)
        messages = [call.args[0] for call in desktop.bus.send.await_args_list]
        self.assertTrue(all(message.flags & MessageFlag.NO_REPLY_EXPECTED for message in messages))
        self.assertEqual([message.body[-2:] for message in messages],
                         [[97,1], [97,0], [98,1], [98,0], [99,1], [99,0], [32,1]])
        desktop.call.assert_awaited_once()
        self.assertEqual(desktop.call.call_args.args[-1][-2:], [32,0])

    async def test_push_to_talk_release_finishes_without_a_second_activation(self):
        from unittest.mock import Mock
        desktop = self.desktop()
        desktop.config = lambda: {'stt_mode': 'push-to-talk'}
        desktop.dictation = Mock()
        desktop.dictation.status.return_value = {'busy': False}
        desktop.confirm_focus.return_value = ('editor', 1)
        desktop.shortcut_down = True
        await desktop.shortcut(True)
        desktop.dictation.start.assert_called_once_with(target=('editor', 1))
        desktop.shortcut_down = False
        await desktop.shortcut(False)
        desktop.dictation.finish.assert_called_once()

    async def test_toggle_release_does_not_stop_but_next_press_does(self):
        from unittest.mock import Mock
        desktop = self.desktop()
        desktop.config = lambda: {'stt_mode': 'toggle'}
        desktop.dictation = Mock()
        desktop.dictation.status.return_value = {'busy': False}
        desktop.confirm_focus.return_value = ('editor', 1)
        await desktop.shortcut(True)
        await desktop.shortcut(False)
        desktop.dictation.finish.assert_not_called()
        desktop.dictation.status.return_value = {'busy': True}
        await desktop.shortcut(True)
        desktop.dictation.finish.assert_called_once()


class IdentityStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_peer_registers_before_any_other_portal_call(self):
        import importlib.util
        if importlib.util.find_spec('dbus_next') is None:
            self.skipTest('Desktop dependency is not installed')
        import os
        from pathlib import Path
        import tempfile
        from unittest.mock import Mock, patch
        with tempfile.TemporaryDirectory() as folder:
            desktop = Desktop(Mock(), lambda: {}, folder, 'startup')
            desktop.loop = asyncio.get_running_loop()
            bus = Mock()
            bus.request_name = AsyncMock()
            factory = Mock(); factory.connect = AsyncMock(return_value=bus)
            calls = []
            async def call(service, path, interface, member, *args, **kwargs):
                calls.append((interface, member))
                if member == 'GetNameOwner': return [':1.2']
                if service == 'org.kde.KWin': raise RuntimeError('Stop after identity setup')
                return []
            desktop.call = call
            with patch.dict(os.environ, {'WAYLAND_DISPLAY': 'test', 'XDG_DATA_HOME': folder}), patch('dbus_next.aio.MessageBus', return_value=factory):
                with self.assertRaisesRegex(RuntimeError, 'Stop after identity setup'):
                    await desktop.setup()
            portal_calls = [item for item in calls if item[0].startswith('org.freedesktop.') and 'portal.' in item[0]]
            self.assertEqual(portal_calls[0], ('org.freedesktop.host.portal.Registry', 'Register'))
            from akousousin_app.desktop_identity import APP_ID
            self.assertTrue((Path(folder) / 'applications' / (APP_ID + '.desktop')).exists())


    async def test_identity_retries_only_transient_app_lookup_failures(self):
        import tempfile
        from unittest.mock import Mock, patch
        with tempfile.TemporaryDirectory() as folder:
            desktop = Desktop(Mock(), lambda: {}, folder, 'startup')
            desktop.call = AsyncMock(side_effect=[RuntimeError('Register: App info not found'), []])
            with patch('akousousin_app.desktop_identity.ensure_desktop_entry', return_value=folder), patch('akousousin_app.desktop_input.asyncio.sleep', new_callable=AsyncMock) as delay:
                await desktop.register_identity()
                delay.assert_awaited_once_with(.25)
            self.assertEqual(desktop.call.await_count, 2)
            desktop.call = AsyncMock(side_effect=RuntimeError('Register: Permission denied'))
            with patch('akousousin_app.desktop_identity.ensure_desktop_entry', return_value=folder):
                with self.assertRaisesRegex(RuntimeError, 'Permission denied'):
                    await desktop.register_identity()
            self.assertEqual(desktop.call.await_count, 1)
