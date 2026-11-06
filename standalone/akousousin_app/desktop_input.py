# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""KDE focus tracking and consent-based desktop portals. Loaded only on enable."""
import asyncio
import concurrent.futures
import json
import os
from pathlib import Path
import secrets
import threading
import time
import uuid


class FocusGuard:
    def __init__(self):
        self.lock = threading.Lock()
        self.identity = ''
        self.epoch = -1
        self.updated = 0

    def report(self, identity, epoch):
        with self.lock:
            if epoch >= self.epoch:
                self.identity, self.epoch = identity, epoch
                self.updated = time.monotonic()

    def invalidate(self):
        with self.lock:
            self.identity = ''
            self.epoch += 1
            self.updated = 0

    def snapshot(self):
        with self.lock:
            if not self.identity or time.monotonic() - self.updated > 3:
                raise RuntimeError('Active window could not be verified')
            return self.identity, self.epoch

    def check(self, expected):
        if self.snapshot() != expected:
            raise RuntimeError('Active window changed')


def keysyms(text):
    # No Enter/Tab/control sequences: dictation must not submit a form or execute
    # a terminal command. Unicode is sent as symbols, without using the clipboard.
    clean = ' '.join(text.split())
    if not clean or len(clean) > 4000:
        raise ValueError('Invalid text length for insertion')
    result = []
    for character in clean + ' ':
        code = ord(character)
        if code < 32 or code == 127 or 0xD800 <= code <= 0xDFFF:
            raise ValueError('Unsupported control character')
        result.append(code if code <= 255 else 0x01000000 | code)
    return result


def focus_script(destination, token):
    service, secret = json.dumps(destination), json.dumps(token)
    return '''// Akousousin session-only focus observer; removed on disable.
var epoch = 0;
function publish(query) {
    var window = workspace.activeWindow;
    var id = window && window.normalWindow ? String(window.internalId) : "";
    callDBus(SERVICE, "/Focus", "org.akousousin.Focus", "Report", TOKEN,
             JSON.stringify({id: id, epoch: epoch, query: query}));
}
workspace.windowActivated.connect(function () { epoch += 1; publish(""); });
function poll() {
    callDBus(SERVICE, "/Focus", "org.akousousin.Focus", "Next", TOKEN,
             function(query) { publish(query); poll(); });
}
publish("");
poll();
'''.replace('SERVICE', service).replace('TOKEN', secret)


class PortalRequests:
    """Shared portal RPC/identity handling; sessions retain their own lifecycle."""
    async def call(self, service, path, interface, member, signature='', body=None, timeout=10):
        from dbus_next import Message, MessageType
        reply = await asyncio.wait_for(self.bus.call(Message(destination=service, path=path,
            interface=interface, member=member, signature=signature, body=body or [])), timeout)
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(member + ': ' + (str(reply.body[0]) if reply.body else reply.error_name))
        return reply.body


    async def request(self, interface, member, prefix, signature, args, options=None):
        from dbus_next import Variant
        token = 'r' + uuid.uuid4().hex
        sender = self.bus.unique_name[1:].replace('.', '_')
        predicted = '/org/freedesktop/portal/desktop/request/' + sender + '/' + token
        future = self.loop.create_future()
        self.requests[predicted] = future
        values = dict(options or {}, handle_token=Variant('s', token))
        handle = None
        try:
            handle = (await self.call('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
                                     interface, member, signature + 'a{sv}', [*args, values]))[0]
            self.requests[handle] = future
            if handle in self.early and not future.done():
                future.set_result(self.early.pop(handle))
            code, result = await asyncio.wait_for(future, 120)
            if code != 0:
                raise RuntimeError('Desktop permission was cancelled or denied')
            return result
        except BaseException:
            if handle:
                try:
                    await self.call('org.freedesktop.portal.Desktop', handle, 'org.freedesktop.portal.Request', 'Close', timeout=2)
                except Exception:
                    pass
            raise
        finally:
            self.requests.pop(predicted, None)
            if handle:
                self.requests.pop(handle, None)


    async def session(self, interface):
        from dbus_next import Variant
        result = await self.request(interface, 'CreateSession', '', '', [],
                                    {'session_handle_token': Variant('s', 's' + uuid.uuid4().hex)})
        handle = result['session_handle'].value
        self.sessions.append(handle)
        return handle


    async def register_identity(self):
        # Registry associates this exact D-Bus peer with the application. Qt's
        # desktopFileName alone does not identify dbus-next's separate connection.
        # Registration must precede every other portal call on a new connection.
        from .desktop_identity import APP_ID, ensure_desktop_entry
        app_id = getattr(self, 'app_id', APP_ID)
        entry = ensure_desktop_entry(app_id=app_id, name=getattr(self, 'desktop_name', 'Akousousin'))
        # GIO's desktop-file monitor may not have processed a just-installed or
        # updated launcher. Failed lookups do not associate this peer with an ID.
        for attempt in range(4):
            try:
                await self.call('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
                                'org.freedesktop.host.portal.Registry', 'Register', 'sa{sv}', [app_id, {}])
                return
            except RuntimeError as error:
                if 'App info not found' not in str(error):
                    raise
                if attempt == 3:
                    raise RuntimeError('Desktop portal could not find ' + str(entry)
                                       + '. Check that its AppImage exists and is executable. '
                                       'If it does, sign out and back in to refresh the desktop application cache. '
                                       'Your settings and models can stay in place.') from error
                await asyncio.sleep(.25 * 2 ** attempt)


class Desktop(PortalRequests):
    def __init__(self, dictation, config, directory, identity):
        self.dictation, self.config = dictation, config
        self.directory = Path(directory)
        self.name = 'org.akousousin.Dictation.p' + identity
        self.plugin = 'akousousin-focus-' + identity
        self.token = secrets.token_hex(24)
        self.guard = FocusGuard()
        self.status = 'Starting desktop integration…'
        self.enabled = False
        self.loop = None
        self.bus = None
        self.thread = None
        self.stopping = threading.Event()
        self.sessions = []
        self.requests = {}
        self.early = {}
        self.focus_waiters = {}
        self.start_requested = False
        self.shortcut_down = False
        self.shortcut_description = ''
        self.tasks = set()
        self.setup_task = None

    def start(self, listen=False):
        self.start_requested = listen
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
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
            self.status = 'Desktop dictation unavailable: ' + str(error)
        finally:
            self.stopping.set()
            self.enabled = False
            self.guard.invalidate()
            self.loop.run_until_complete(self.cleanup())
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            if pending:
                self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self.loop.close()


    def message(self, message):
        from dbus_next import MessageType
        if message.message_type != MessageType.SIGNAL:
            return
        if message.interface == 'org.freedesktop.DBus' and message.member == 'NameOwnerChanged':
            name, old, new = message.body
            if name in ('org.kde.KWin', 'org.freedesktop.portal.Desktop') and old and old != new:
                self.enabled = False
                self.guard.invalidate()
                self.dictation.cancel()
                self.status = 'Desktop service restarted; disable and enable dictation again'
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
                self.enabled = False
                self.guard.invalidate()
                self.dictation.cancel()
                self.status = 'Desktop permission session closed; enable dictation again'
        elif message.interface == 'org.freedesktop.portal.GlobalShortcuts':
            session, shortcut = message.body[:2]
            if session == getattr(self, 'shortcuts', None) and shortcut == 'dictate' and self.enabled:
                active = message.member == 'Activated'
                if message.member not in ('Activated', 'Deactivated'):
                    return
                if active and self.shortcut_down:
                    return
                self.shortcut_down = active
                task = self.loop.create_task(self.shortcut(active))
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)




    async def setup(self):
        if os.name == 'nt' or not os.environ.get('WAYLAND_DISPLAY'):
            raise RuntimeError('Desktop dictation currently requires KDE Wayland')
        from dbus_next.aio import MessageBus
        from dbus_next import Variant
        from dbus_next.service import ServiceInterface, method
        self.bus = await MessageBus().connect()
        await self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                        'org.freedesktop.DBus', 'StartServiceByName', 'su', ['org.freedesktop.portal.Desktop', 0])
        self.portal_owner = (await self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'GetNameOwner', 's', ['org.freedesktop.portal.Desktop']))[0]
        await self.register_identity()
        self.bus.add_message_handler(self.message)
        for rule in ("type='signal',sender='org.freedesktop.portal.Desktop'",
                     "type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',member='NameOwnerChanged'"):
            await self.call('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'AddMatch', 's', [rule])
        await self.bus.request_name(self.name)
        self.focus_queries = asyncio.Queue(maxsize=8)
        owner = self
        class Focus(ServiceInterface):
            def __init__(self):
                super().__init__('org.akousousin.Focus')
            @method()
            def Report(self, token: 's', payload: 's'):
                if token != owner.token:
                    return
                data = json.loads(payload)
                owner.guard.report(data['id'], int(data['epoch']))
                waiter = owner.focus_waiters.get(data.get('query'))
                if waiter is not None and not waiter.done():
                    waiter.set_result(True)
            @method()
            async def Next(self, token: 's') -> 's':
                if token != owner.token:
                    return ''
                try:
                    return await asyncio.wait_for(owner.focus_queries.get(), 1)
                except asyncio.TimeoutError:
                    return ''
        self.bus.export('/Focus', Focus())
        script = self.directory / (self.plugin + '.js')
        descriptor = os.open(script, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'w') as file:
            file.write(focus_script(self.name, self.token))
        await self.call('org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting', 'unloadScript', 's', [self.plugin])
        identifier = (await self.call('org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting', 'loadScript', 'ss', [str(script), self.plugin]))[0]
        if identifier < 0:
            raise RuntimeError('KDE focus observer could not load')
        await self.call('org.kde.KWin', '/Scripting/Script' + str(identifier), 'org.kde.kwin.Script', 'run')
        await self.confirm_focus(require_window=False)
        self.status = 'Approve the dictation shortcut in the desktop dialog…'
        interface = 'org.freedesktop.portal.GlobalShortcuts'
        self.shortcuts = await self.session(interface)
        result = await self.request(interface, 'BindShortcuts', '', 'oa(sa{sv})s',
            [self.shortcuts, [['dictate', {'description': Variant('s', 'Akousousin dictation'),
                                        'preferred_trigger': Variant('s', 'CTRL+ALT+SPACE')}]], ''])
        bindings = result.get('shortcuts')
        if bindings is None or not any(item[0] == 'dictate' for item in bindings.value):
            raise RuntimeError('No dictation shortcut was approved')
        self.shortcut_description = bindings.value[0][1].get('trigger_description', Variant('s', 'Desktop shortcut')).value
        self.status = 'Approve keyboard input in the desktop dialog…'
        self.remote = await self.session('org.freedesktop.portal.RemoteDesktop')
        await self.request('org.freedesktop.portal.RemoteDesktop', 'SelectDevices', '', 'o', [self.remote],
                           {'types': Variant('u', 1)})
        result = await self.request('org.freedesktop.portal.RemoteDesktop', 'Start', '', 'os', [self.remote, ''])
        if not result.get('devices') or not result['devices'].value & 1:
            raise RuntimeError('Keyboard permission was not granted')
        self.enabled = True
        self.status = 'Desktop dictation enabled — ' + self.shortcut_description
        if self.start_requested:
            self.start_requested = False
            await self.toggle_recording()

    async def confirm_focus(self, require_window=True):
        identifier = uuid.uuid4().hex
        future = self.loop.create_future()
        self.focus_waiters[identifier] = future
        try:
            self.focus_queries.put_nowait(identifier)
            await asyncio.wait_for(future, 3)
            return self.guard.snapshot() if require_window else None
        except asyncio.TimeoutError as error:
            raise RuntimeError('KDE focus observer did not respond') from error
        finally:
            self.focus_waiters.pop(identifier, None)

    async def toggle_recording(self):
        try:
            if self.dictation.status()['busy']:
                self.dictation.finish()
            else:
                self.dictation.start(target=await self.confirm_focus())
        except Exception as error:
            self.status = str(error)

    def trigger(self):
        self.loop.call_soon_threadsafe(lambda: self.loop.create_task(self.toggle_recording()))

    async def shortcut(self, active):
        if not hasattr(self, '_shortcut_lock'):
            self._shortcut_lock = asyncio.Lock()
        async with self._shortcut_lock:
            await self._shortcut(active)

    async def _shortcut(self, active):
        try:
            config = self.config()
            if active:
                current = self.dictation.status()
                if current['busy']:
                    if config.get('stt_mode', 'toggle') == 'toggle':
                        self.dictation.finish()
                    return
                target = await self.confirm_focus()
                # A quick PTT release during focus verification must not start a
                # recording after the user has already let go.
                if config.get('stt_mode', 'toggle') == 'push-to-talk' and not self.shortcut_down:
                    return
                self.dictation.start(target=target)
            elif config.get('stt_mode', 'toggle') == 'push-to-talk':
                self.dictation.finish()
        except Exception as error:
            self.status = str(error)

    async def type_text(self, text, target, cancelled):
        if not self.enabled:
            raise RuntimeError('Keyboard session closed')
        deadline = time.monotonic() + 3
        while self.shortcut_down:
            if cancelled.is_set() or time.monotonic() >= deadline:
                raise InterruptedError('Shortcut is still held or dictation was cancelled')
            await asyncio.sleep(.03)
        await self.confirm_focus()
        self.guard.check(target)
        count = 0
        for symbol in keysyms(text):
            if cancelled.is_set():
                raise InterruptedError('Text insertion cancelled')
            self.guard.check(target)
            if count % 8 == 0:
                await self.confirm_focus()
                self.guard.check(target)
            try:
                await self.call('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
                    'org.freedesktop.portal.RemoteDesktop', 'NotifyKeyboardKeysym', 'oa{sv}iu',
                    [self.remote, {}, symbol, 1], timeout=3)
                count += 1
            finally:
                await self.call('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
                    'org.freedesktop.portal.RemoteDesktop', 'NotifyKeyboardKeysym', 'oa{sv}iu',
                    [self.remote, {}, symbol, 0], timeout=3)

    def insert(self, text, target, cancelled):
        if not self.loop or not self.enabled:
            raise RuntimeError('Desktop dictation is disabled')
        future = asyncio.run_coroutine_threadsafe(self.type_text(text, target, cancelled), self.loop)
        try:
            return future.result(timeout=30)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise TimeoutError('Text insertion timed out')

    async def cleanup(self):
        if self.bus is None:
            return
        for handle in self.sessions:
            try:
                await self.call('org.freedesktop.portal.Desktop', handle, 'org.freedesktop.portal.Session', 'Close', timeout=2)
            except Exception:
                pass
        try:
            await self.call('org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting', 'unloadScript', 's', [self.plugin], timeout=2)
        except Exception:
            pass
        (self.directory / (self.plugin + '.js')).unlink(missing_ok=True)
        self.bus.disconnect()

    def close(self):
        self.start_requested = False
        self.stopping.set()
        self.enabled = False
        self.guard.invalidate()
        self.dictation.cancel()
        if self.loop and self.loop.is_running():
            def stop():
                if self.setup_task and not self.setup_task.done():
                    self.setup_task.cancel()
                else:
                    self.loop.stop()
            self.loop.call_soon_threadsafe(stop)
        if self.thread:
            self.thread.join(10)
