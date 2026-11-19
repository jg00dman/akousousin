# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Exercise the packaged desktop applet on a private X11 display and session bus."""
import asyncio
import os
from pathlib import Path
import sys
import tempfile

from dbus_next import Message, MessageType
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method


class TrayHost(ServiceInterface):
    def __init__(self):
        super().__init__('org.kde.StatusNotifierWatcher')
        self.items = asyncio.Queue()

    @method()
    def RegisterStatusNotifierItem(self, item: 's'):
        self.items.put_nowait(item)


async def check(command, desktop, late):
    bus = await MessageBus().connect()
    host = TrayHost()

    async def start_host():
        bus.export('/StatusNotifierWatcher', host)
        await bus.request_name(host.name)

    try:
        if not late:
            await start_host()
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, XDG_RUNTIME_DIR=temp, XDG_CONFIG_HOME=temp,
                       XDG_DATA_HOME=temp, XDG_STATE_HOME=temp, XDG_CURRENT_DESKTOP=desktop)
            args = [*command, '--settings', str(Path(temp) / 'settings.json')]
            proc = await asyncio.create_subprocess_exec(*args, '--controller', env=env)
            try:
                if late:
                    # Wait until the controller has entered its event loop.
                    for _ in range(100):
                        if list(Path(temp, 'Akousousin').glob('*.lock')):
                            status = await asyncio.create_subprocess_exec(*args, '--status', env=env,
                                                                          stdout=asyncio.subprocess.PIPE)
                            output, _ = await status.communicate()
                            if b'"independent"' in output:
                                break
                        await asyncio.sleep(.1)
                    else:
                        raise AssertionError('Controller did not start')
                    await start_host()
                item = await asyncio.wait_for(host.items.get(), 15)
                properties = await bus.call(Message(destination=item, path='/StatusNotifierItem',
                    interface='org.freedesktop.DBus.Properties', member='GetAll',
                    signature='s', body=['org.kde.StatusNotifierItem']))
                assert properties.message_type == MessageType.METHOD_RETURN, properties.body
                props = properties.body[0]
                assert any(w > 0 and h > 0 and any(data) for w, h, data in props['IconPixmap'].value)
                menu = await bus.call(Message(destination=item, path=props['Menu'].value,
                    interface='com.canonical.dbusmenu', member='GetLayout', signature='iias',
                    body=[0, 1, ['label']]))
                assert menu.message_type == MessageType.METHOD_RETURN, menu.body
                labels = [child.value[1]['label'].value for child in menu.body[1][2]
                          if 'label' in child.value[1]]
                assert 'Configure' in labels and 'Quit' in labels, labels
            finally:
                if proc.returncode is None:
                    proc.terminate()
                await proc.wait()
    finally:
        bus.disconnect()
        await bus.wait_for_disconnect()


async def main():
    for desktop in ('KDE', 'GNOME'):
        for late in (False, True):
            await check(sys.argv[1:], desktop, late)


if __name__ == '__main__':
    asyncio.run(main())
