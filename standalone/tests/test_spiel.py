# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Spiel discovery, default selection and audio streaming on a private bus."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import wave

from akousousin_app import runtime, settings, spiel

PCM = b'\x01\x12' * 4000
PREVIOUS = "@m(ss) ('org.example.Speech.Provider', 'previous')"
VOICE = 'fixture-voice'


class FakePiper(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append(request)
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setparams((1, 2, request['sample_rate'], 0, 'NONE', ''))
            wav.writeframes(PCM)
        audio = output.getvalue()
        self.send_response(200)
        self.send_header('Content-Length', str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)


async def fake_controller(reader, writer):
    await reader.readline()
    writer.write(b'{}\n')
    await writer.drain()
    writer.close()
    await writer.wait_closed()


class AvailabilityTests(unittest.TestCase):
    def test_spiel_is_found_by_its_settings_schema(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            schemas = Path(folder) / 'glib-2.0/schemas'
            schemas.mkdir(parents=True)
            environment = {'XDG_DATA_HOME': str(Path(folder) / 'none'), 'XDG_DATA_DIRS': folder}
            with patch.object(spiel.runtime, 'host_environment', return_value=environment), \
                    patch.object(spiel.Path, 'is_file', lambda self: str(self).startswith(folder) and os.path.isfile(self)):
                self.assertFalse(spiel.available())
                (schemas / (spiel.SCHEMA + '.gschema.xml')).write_text('<schemalist/>')
                self.assertTrue(spiel.available())


@unittest.skipUnless(sys.platform == 'linux' and all(shutil.which(tool) for tool in
                     ('dbus-run-session', 'gdbus', 'gsettings', 'glib-compile-schemas')),
                     'requires the Linux session bus and GLib tools')
class SpielTests(unittest.TestCase):
    def test_activation_default_pcm_and_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schema = root / 'schema'
            schema.mkdir()
            (schema / (spiel.SCHEMA + '.gschema.xml')).write_text(
                f'<schemalist><schema id="{spiel.SCHEMA}" path="/org/monotonous/libspiel/">'
                '<key name="default-voice" type="m(ss)"><default>nothing</default></key>'
                '</schema></schemalist>', encoding='utf-8')
            subprocess.run(['glib-compile-schemas', str(schema)], check=True)
            env = dict(os.environ, GSETTINGS_SCHEMA_DIR=str(schema), GSETTINGS_BACKEND='dconf')
            for name in ('DATA', 'CONFIG', 'RUNTIME', 'STATE'):
                folder = root / name.lower()
                folder.mkdir(mode=0o700)
                env[f'XDG_{name}_DIR' if name == 'RUNTIME' else f'XDG_{name}_HOME'] = str(folder)
            result = subprocess.run(['dbus-run-session', '--', sys.executable, str(Path(__file__).resolve()), '--exercise'],
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


async def exercise():
    from dbus_next import Message, MessageType
    from dbus_next.aio import MessageBus

    profile = settings.config_path().with_name('settings with spaces.json')
    controller = await asyncio.start_unix_server(fake_controller, path=runtime.name(profile))
    server = ThreadingHTTPServer(('127.0.0.1', 0), FakePiper)
    server.requests = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    model = profile.with_suffix('.onnx')
    model.parent.mkdir(parents=True)
    model.touch()
    model.with_suffix('.onnx.json').write_text('{}', encoding='utf-8')
    config = settings.load(profile)
    config.update(port=server.server_port, voice=VOICE, voices={
        VOICE: {'name': 'Fixture voice', 'path': str(model), 'language': 'en_US', 'sample_rate': 22050}})
    settings.save(profile, config)

    async def cli(flag):
        command = runtime.command('--settings', str(profile), flag)
        await asyncio.to_thread(subprocess.run, command, check=True, capture_output=True, text=True, timeout=10)

    bus = await MessageBus(negotiate_unix_fd=True).connect()

    async def bus_names(member):
        reply = await bus.call(Message(destination='org.freedesktop.DBus', path='/org/freedesktop/DBus',
                                       interface='org.freedesktop.DBus', member=member))
        assert reply.message_type == MessageType.METHOD_RETURN, reply.body
        return reply.body[0]

    async def check_pcm():
        read_fd, write_fd = os.pipe()
        with os.fdopen(read_fd, 'rb') as output:
            try:
                result = await bus.call(Message(destination=spiel.BUS_NAME, path=spiel.OBJECT_PATH, interface=spiel.INTERFACE,
                                                member='Synthesize', signature='hssddbs', unix_fds=[write_fd],
                                                body=[0, '<speak>Hello <emphasis>Spiel</emphasis>!</speak>',
                                                      VOICE, 1.0, 1.25, True, 'en-US']))
            finally:
                os.close(write_fd)
            assert result.message_type == MessageType.METHOD_RETURN, result.body
            assert await asyncio.to_thread(output.read) == PCM

    try:
        spiel.set_default(PREVIOUS)
        await cli('--install-spiel')
        await cli('--install-spiel')
        assert spiel.current_default() == f"@m(ss) ('{spiel.BUS_NAME}', '{VOICE}')"
        assert spiel.BUS_NAME in await bus_names('ListActivatableNames')
        reply = await bus.call(Message(destination=spiel.BUS_NAME, path=spiel.OBJECT_PATH,
                                       interface='org.freedesktop.DBus.Properties', member='GetAll',
                                       signature='s', body=[spiel.INTERFACE]))
        assert reply.body[0]['Name'].value == 'Akousousin'
        assert reply.body[0]['Voices'].value == [
            ['Fixture voice', VOICE, 'audio/x-raw,format=S16LE,channels=1,rate=22050', 0, ['en-US']]]
        await asyncio.gather(check_pcm(), check_pcm())
        assert server.requests == [
            {'text': 'Hello Spiel!', 'voice': VOICE, 'length_scale': .8, 'sample_rate': 22050}] * 2

        await cli('--uninstall-spiel')
        assert spiel.current_default() == PREVIOUS
        assert spiel.BUS_NAME not in await bus_names('ListActivatableNames')
        for _ in range(20):
            if spiel.BUS_NAME not in await bus_names('ListNames'):
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError('The disabled provider still owns its bus name')

        await cli('--install-spiel')
        alternative = "@m(ss) ('org.example2.Speech.Provider', 'changed')"
        spiel.set_default(alternative)
        await cli('--uninstall-spiel')
        assert spiel.current_default() == alternative
    finally:
        bus.disconnect()
        await bus.wait_for_disconnect()
        controller.close()
        await controller.wait_closed()
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    if sys.argv[1:] == ['--exercise']:
        asyncio.run(exercise())
    else:
        unittest.main()
