# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Opt-in protocol tests on a private D-Bus; never opens desktop consent dialogs."""
import asyncio
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch
from akousousin_app.desktop_input import Desktop


@unittest.skipUnless(os.environ.get('AKS_TEST_PORTALS') == '1', 'Run with AKS_TEST_PORTALS=1 inside dbus-run-session')
class PortalBusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from dbus_next.aio import MessageBus
        from dbus_next import Variant, DBusError
        from dbus_next.service import ServiceInterface, method, signal
        self.folder = tempfile.TemporaryDirectory()
        self.server = await MessageBus().connect()
        await self.server.request_name('org.freedesktop.portal.Desktop')
        self.desktop = Desktop(None, lambda: {}, self.folder.name, 'test')
        self.desktop.loop = asyncio.get_running_loop()
        self.desktop.bus = await MessageBus().connect()
        self.desktop.portal_owner = self.server.unique_name
        self.desktop.bus.add_message_handler(self.desktop.message)
        await self.desktop.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'AddMatch', 's', ["type='signal',sender='org.freedesktop.portal.Desktop'"])
        self.identity = None
        self.data_patch = patch.dict(os.environ, {'XDG_DATA_HOME': self.folder.name})
        self.data_patch.start()
        self.keys = []
        self.deny = False
        owner = self
        class Request(ServiceInterface):
            def __init__(self):
                super().__init__('org.freedesktop.portal.Request')
            @signal()
            def Response(self, code, values) -> 'ua{sv}':
                return [code, values]
            @method()
            def Close(self):
                pass
        def response(options, values):
            sender = owner.desktop.bus.unique_name[1:].replace('.', '_')
            path = '/org/freedesktop/portal/desktop/request/' + sender + '/' + options['handle_token'].value
            request = Request(); owner.server.export(path, request)
            # Signal before the method return to test the request/response race.
            request.Response(1 if owner.deny else 0, values)
            return path
        class Registry(ServiceInterface):
            def __init__(self):
                super().__init__('org.freedesktop.host.portal.Registry')
            @method()
            def Register(self, app_id: 's', options: 'a{sv}'):
                from akousousin_app.desktop_identity import APP_ID
                assert app_id in (APP_ID, APP_ID + '.ReadSelection')
                assert (Path(owner.folder.name) / 'applications' / (app_id + '.desktop')).is_file()
                owner.identity = app_id
        class Portal(ServiceInterface):
            def __init__(self):
                super().__init__('org.freedesktop.portal.RemoteDesktop')
            @method()
            def CreateSession(self, options: 'a{sv}') -> 'o':
                if owner.identity is None:
                    raise DBusError('org.freedesktop.portal.Error.Failed', 'An app id is required.')
                return response(options, {'session_handle': Variant('s', '/session/test')})
            @method()
            def SelectDevices(self, session: 'o', options: 'a{sv}') -> 'o':
                assert session == '/session/test'
                assert options['types'].value == 1
                return response(options, {})
            @method()
            def Start(self, session: 'o', parent: 's', options: 'a{sv}') -> 'o':
                return response(options, {'devices': Variant('u', 1)})
            @method()
            def NotifyKeyboardKeysym(self, session: 'o', options: 'a{sv}', symbol: 'i', state: 'u'):
                owner.keys.append((symbol, state))
        self.server.export('/org/freedesktop/portal/desktop', Registry())
        self.server.export('/org/freedesktop/portal/desktop', Portal())
        class ReadingPortal(ServiceInterface):
            def __init__(self):
                super().__init__('org.freedesktop.portal.GlobalShortcuts')
            @method()
            def CreateSession(self, options: 'a{sv}') -> 'o':
                assert owner.identity == 'org.akousousin.Akousousin.ReadSelection'
                return response(options, {'session_handle': Variant('s', '/session/reading')})
            @method()
            def BindShortcuts(self, session: 'o', shortcuts: 'a(sa{sv})', parent: 's', options: 'a{sv}') -> 'o':
                assert session == '/session/reading'
                assert {item[0] for item in shortcuts} == {'read-selection', 'read-clipboard'}
                values = [[key, {'trigger_description': fields['preferred_trigger']}] for key, fields in shortcuts]
                return response(options, {'shortcuts': Variant('a(sa{sv})', values)})
            @signal()
            def Activated(self, session, shortcut, timestamp, options) -> 'osta{sv}':
                return [session, shortcut, timestamp, options]
            @signal()
            def Deactivated(self, session, shortcut, timestamp, options) -> 'osta{sv}':
                return [session, shortcut, timestamp, options]
        self.reading_portal = ReadingPortal()
        self.server.export('/org/freedesktop/portal/desktop', self.reading_portal)

    async def asyncTearDown(self):
        self.desktop.bus.disconnect()
        self.server.disconnect()
        await asyncio.sleep(.02)
        self.data_patch.stop()
        self.folder.cleanup()

    async def test_reading_identity_binds_global_shortcuts_and_routes_real_signals(self):
        from akousousin_app.selection_shortcuts import ReadingShortcuts
        from akousousin_app.desktop_identity import APP_ID
        activated = asyncio.Event()
        calls = []
        def read(clipboard):
            calls.append(clipboard); activated.set()
        reader = ReadingShortcuts(read, lambda: None)
        reader.loop = asyncio.get_running_loop()
        with patch.dict(os.environ, {'WAYLAND_DISPLAY': 'fixture-only'}):
            try:
                await self.desktop.register_identity()
                await reader.setup()
                self.assertTrue(reader.enabled)
                self.assertNotEqual(reader.app_id, APP_ID)
                self.assertTrue((Path(self.folder.name) / 'applications' / (APP_ID + '.desktop')).exists())
                self.assertIn('CTRL+ALT+R', reader.status)
                self.reading_portal.Activated('/session/reading', 'read-selection', 1, {})
                await asyncio.wait_for(activated.wait(), 1)
                self.assertEqual(calls, [False])
                activated.clear()
                self.reading_portal.Activated('/session/reading', 'read-selection', 2, {})
                self.reading_portal.Deactivated('/session/reading', 'read-selection', 3, {})
                self.reading_portal.Activated('/session/reading', 'read-clipboard', 4, {})
                await asyncio.wait_for(activated.wait(), 1)
                self.assertEqual(calls, [False, True])
                self.assertEqual(self.keys, [], 'Reading shortcuts must not request keyboard injection')
            finally:
                reader.stopping.set()
                await reader.cleanup()

    async def test_early_response_and_actual_keyboard_messages(self):
        from dbus_next import Variant
        await self.desktop.register_identity()
        interface = 'org.freedesktop.portal.RemoteDesktop'
        self.desktop.remote = await self.desktop.session(interface)
        await self.desktop.request(interface, 'SelectDevices', '', 'o', [self.desktop.remote], {'types': Variant('u', 1)})
        result = await self.desktop.request(interface, 'Start', '', 'os', [self.desktop.remote, ''])
        self.assertEqual(result['devices'].value, 1)
        self.desktop.enabled = True
        self.desktop.guard.report('editor', 1)
        self.desktop.confirm_focus = AsyncMock()
        await self.desktop.type_text('hé', self.desktop.guard.snapshot(), threading.Event())
        self.assertEqual(self.keys, [(104, 1), (104, 0), (233, 1), (233, 0), (32, 1), (32, 0)])

    async def test_denial_never_types(self):
        await self.desktop.register_identity()
        self.deny = True
        with self.assertRaisesRegex(RuntimeError, 'denied'):
            await self.desktop.session('org.freedesktop.portal.RemoteDesktop')
        self.assertFalse(self.desktop.enabled)
        self.assertEqual(self.keys, [])

    async def test_unregistered_peer_reproduces_reported_error(self):
        with self.assertRaisesRegex(RuntimeError, 'An app id is required'):
            await self.desktop.session('org.freedesktop.portal.RemoteDesktop')
        self.assertEqual(self.keys, [])
