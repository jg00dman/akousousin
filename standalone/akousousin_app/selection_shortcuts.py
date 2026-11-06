# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Opt-in global reading shortcuts without microphone or keyboard-injection access."""
import asyncio
import os
import threading

from .desktop_input import PortalRequests


class ReadingShortcuts(PortalRequests):
    # KDE stores bindings per application ID. A separate component prevents
    # BindShortcuts from removing the existing dictation action.
    app_id = 'org.akousousin.Akousousin.ReadSelection'
    desktop_name = 'Akousousin Read selection'
    actions = {'read-selection': ('Read selected text / Stop', 'CTRL+ALT+R'),
               'read-clipboard': ('Read copied text / Stop', 'CTRL+ALT+SHIFT+R')}

    def __init__(self, activate, cancel):
        self.activate, self.cancel = activate, cancel
        self.enabled = False
        self.status = 'Reading shortcuts are disabled'
        self.descriptions = {}
        self.loop = self.bus = self.thread = self.setup_task = None
        self.sessions, self.requests, self.early = [], {}, {}
        self.down = set()
        self.stopping = threading.Event()

    def start(self):
        self.status = 'Approve the reading shortcuts in KDE…'
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.setup_task = self.loop.create_task(self.setup())
        try:
            self.loop.run_until_complete(self.setup_task)
            if not self.stopping.is_set():
                self.loop.run_forever()
        except asyncio.CancelledError:
            pass
        except Exception as error:
            self.status = 'Reading shortcuts unavailable: ' + str(error)
        finally:
            self.enabled = False
            self.stopping.set()
            self.loop.run_until_complete(self.cleanup())
            tasks = asyncio.all_tasks(self.loop)
            for task in tasks:
                task.cancel()
            if tasks:
                self.loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            self.loop.close()

    async def setup(self):
        if os.name == 'nt' or not os.environ.get('WAYLAND_DISPLAY'):
            raise RuntimeError('Automatic global reading shortcuts currently require KDE Wayland; use the desktop action on X11')
        from dbus_next.aio import MessageBus
        from dbus_next import Variant
        self.bus = await MessageBus().connect()
        try:
            owner = await self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                   'org.freedesktop.DBus', 'GetNameOwner', 's', ['org.freedesktop.portal.Desktop'])
        except RuntimeError:
            await self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                            'org.freedesktop.DBus', 'StartServiceByName', 'su', ['org.freedesktop.portal.Desktop', 0])
            owner = await self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                   'org.freedesktop.DBus', 'GetNameOwner', 's', ['org.freedesktop.portal.Desktop'])
        self.portal_owner = owner[0]
        await self.register_identity()
        self.bus.add_message_handler(self.message)
        for rule in ("type='signal',sender='org.freedesktop.portal.Desktop'",
                     "type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',member='NameOwnerChanged'"):
            await self.call('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'AddMatch', 's', [rule])
        interface = 'org.freedesktop.portal.GlobalShortcuts'
        self.shortcuts = await self.session(interface)
        actions = [[key, {'description': Variant('s', title), 'preferred_trigger': Variant('s', trigger)}]
                   for key, (title, trigger) in self.actions.items()]
        result = await self.request(interface, 'BindShortcuts', '', 'oa(sa{sv})s', [self.shortcuts, actions, ''])
        if 'shortcuts' not in result:
            raise RuntimeError('No reading shortcuts were approved')
        self.bindings(result['shortcuts'].value)
        self.enabled = True

    def bindings(self, values):
        self.descriptions = {key: fields['trigger_description'].value or 'Unassigned'
                             for key, fields in values if key in self.actions and 'trigger_description' in fields}
        self.status = 'Reading shortcuts — ' + '; '.join(self.actions[key][0] + ': ' + value
                                                        for key, value in self.descriptions.items())

    def message(self, message):
        from dbus_next import MessageType
        if message.message_type != MessageType.SIGNAL:
            return
        if message.interface == 'org.freedesktop.DBus' and message.member == 'NameOwnerChanged':
            name, old, new = message.body
            if name == 'org.freedesktop.portal.Desktop' and old and old != new:
                self.enabled = False; self.cancel()
                self.status = 'Desktop portal restarted; enable reading shortcuts again'
            return
        if message.sender != self.portal_owner:
            return
        if message.interface == 'org.freedesktop.portal.Request' and message.member == 'Response':
            future = self.requests.get(message.path)
            if future is not None and not future.done():
                future.set_result(message.body)
            elif len(self.early) < 16:
                self.early[message.path] = message.body
        elif message.interface == 'org.freedesktop.portal.Session' and message.member == 'Closed':
            if message.path in self.sessions and not self.stopping.is_set():
                self.enabled = False; self.cancel()
                self.status = 'Reading shortcut permission closed; enable it again'
        elif message.interface == 'org.freedesktop.portal.GlobalShortcuts' and message.body[0] == getattr(self, 'shortcuts', None):
            if message.member == 'ShortcutsChanged':
                self.bindings(message.body[1])
                return
            key = message.body[1]
            if key not in self.actions or not self.enabled:
                return
            if message.member == 'Deactivated':
                self.down.discard(key)
            elif message.member == 'Activated' and key not in self.down:
                self.down.add(key)
                self.activate(clipboard=key == 'read-clipboard')

    async def cleanup(self):
        if self.bus:
            for handle in self.sessions:
                try:
                    await self.call('org.freedesktop.portal.Desktop', handle, 'org.freedesktop.portal.Session', 'Close', timeout=2)
                except Exception:
                    pass
            self.bus.disconnect()

    def close(self):
        self.stopping.set(); self.enabled = False
        if self.loop and self.loop.is_running():
            def stop():
                if self.setup_task and not self.setup_task.done():
                    self.setup_task.cancel()
                else:
                    self.loop.stop()
            self.loop.call_soon_threadsafe(stop)
        if self.thread:
            self.thread.join(10)
