# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Session-bus speech provider. Spiel owns playback and closes the pipe to stop."""
import asyncio
import fcntl
import io
import json
import logging
import math
import os
from pathlib import Path
import select
import stat
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from xml.etree import ElementTree

from dbus_next import Message, MessageType, NameFlag, RequestNameReply
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.errors import DBusError
from dbus_next.service import ServiceInterface, dbus_property, method

from . import resources, runtime, settings, speech_gate, spiel
from .speech_dispatcher import MAX_MESSAGE, chunks
from .transport import fetch

SAMPLE_RATE = 22050
FORMAT = f'audio/x-raw,format=S16LE,channels=1,rate={SAMPLE_RATE}'
MAX_REQUESTS = 3
LOG = logging.getLogger(__name__)


def installed_voices(config):
    return {key: voice for key, voice in config['voices'].items() if resources.voice_available(config, key)}


def pipeline_text(text, is_ssml):
    if not is_ssml:
        return text
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('XML declarations are unsupported in Spiel speech')
    root = ElementTree.fromstring(text)
    if root.tag.rsplit('}', 1)[-1] != 'speak':
        raise ValueError('Expected a speak element')
    return ''.join(root.itertext())


class OutputPipe:
    def __init__(self, fd, path):
        self.fd = fd
        self.path = path
        self.gate = speech_gate.snapshot(path)
        self.stopped = threading.Event()
        self.poll = select.poll()
        self.poll.register(fd, select.POLLERR | select.POLLHUP)

    def is_set(self):
        return self.stopped.is_set() or bool(self.poll.poll(0)) or speech_gate.suppressed(self.path, self.gate)

    def write(self, pcm):
        data = memoryview(pcm)
        deadline = time.monotonic() + 65
        while data and not self.is_set():
            if time.monotonic() >= deadline:
                raise TimeoutError('Spiel client did not read its speech pipe')
            try:
                data = data[os.write(self.fd, data[:8192]):]
            except BlockingIOError:
                self.stopped.wait(.025)


def cancel_backend_request(port, request_id):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/cancel', data=b'',
                                     headers={'X-Akousousin-Request': request_id})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=1):
            pass
    except OSError:
        pass


def render(pipe, text, voice, rate, port):
    request_id = uuid.uuid4().hex
    started = False
    try:
        if pipe.is_set() or not text.strip():
            return
        runtime.call(pipe.path, {'command': 'wake'}, timeout=20)
        for part in chunks(text):
            if pipe.is_set():
                return
            if not part.strip():
                continue
            data = json.dumps({'text': part, 'voice': voice, 'length_scale': 1 / max(.5, min(2, rate)),
                               'sample_rate': SAMPLE_RATE}).encode()
            deadline = time.monotonic() + 2
            while not pipe.is_set():
                try:
                    started = True
                    audio = fetch(port, data, pipe, request_id)
                    break
                except urllib.error.HTTPError as error:
                    if error.code != 503 or time.monotonic() >= deadline:
                        raise
                    pipe.stopped.wait(.05)
            else:
                return
            with wave.open(io.BytesIO(audio), 'rb') as wav:
                if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, SAMPLE_RATE, 'NONE'):
                    raise ValueError('Invalid PCM from the Akousousin speech service')
                pcm = wav.readframes(wav.getnframes())
                if len(pcm) != wav.getnframes() * 2:
                    raise ValueError('Truncated PCM from the Akousousin speech service')
            pipe.write(pcm)
    except (BrokenPipeError, InterruptedError):
        pass  # The client closed its pipe or dictation cancelled the speech.
    except Exception:
        LOG.exception('Spiel synthesis failed')
    finally:
        cancelled = pipe.is_set()
        os.close(pipe.fd)
        if started and cancelled:
            cancel_backend_request(port, request_id)


class Provider(ServiceInterface):
    def __init__(self, path):
        super().__init__(spiel.INTERFACE)
        self.path = path
        self.requests = {}
        self.voices = self.voice_list()

    def voice_list(self):
        return [[voice.get('name') or key, key, FORMAT, 0, [voice['language'].replace('_', '-')]]
                for key, voice in installed_voices(settings.load(self.path)).items()]

    def refresh(self):
        voices = self.voice_list()
        if voices != self.voices:
            self.voices = voices
            self.emit_properties_changed({'Voices': voices})

    @dbus_property(access=PropertyAccess.READ)
    def Name(self) -> 's':
        return 'Akousousin'

    @dbus_property(access=PropertyAccess.READ)
    def Voices(self) -> 'a(ssstas)':
        return self.voices

    @method()
    def Synthesize(self, pipe_fd: 'h', text: 's', voice_id: 's', pitch: 'd', rate: 'd', is_ssml: 'b', language: 's'):
        try:
            if not stat.S_ISFIFO(os.fstat(pipe_fd).st_mode) or fcntl.fcntl(pipe_fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_WRONLY:
                raise ValueError('Spiel needs the writable end of a pipe')
            if len(text.encode()) > MAX_MESSAGE or not math.isfinite(rate) or rate <= 0:
                raise ValueError('Invalid Spiel text or speech rate')
            text = pipeline_text(text, is_ssml)
            config = settings.load(self.path)
            config['voices'] = installed_voices(config)
            voice = settings.usable_voice(config, voice_id, language=language)
            if voice is None:
                raise ValueError('No Akousousin voice is installed')
            if len(self.requests) >= MAX_REQUESTS:
                raise DBusError('org.freedesktop.DBus.Error.LimitsExceeded', 'Akousousin is busy')
            os.set_blocking(pipe_fd, False)
            pipe = OutputPipe(pipe_fd, self.path)
            # Acknowledge acceptance immediately, as Spiel reads the stream asynchronously.
            task = asyncio.create_task(asyncio.to_thread(render, pipe, text, voice, rate, config['port']))
            self.requests[task] = pipe
            task.add_done_callback(self.requests.pop)
        except (OSError, ValueError, ElementTree.ParseError) as error:
            os.close(pipe_fd)
            raise DBusError('org.freedesktop.DBus.Error.InvalidArgs', str(error)) from error
        except Exception:
            os.close(pipe_fd)
            raise


def check_descriptors(message):
    # dbus-next resolves the handle before dispatch and leaves descriptor
    # ownership to us. Reject extras and close descriptors on malformed calls.
    synthesis = (message.message_type == MessageType.METHOD_CALL and message.path == spiel.OBJECT_PATH
                 and message.interface == spiel.INTERFACE and message.member == 'Synthesize')
    if synthesis and message.signature == 'hssddbs' and message.body[0] == 0 and len(message.unix_fds) == 1:
        return None
    for fd in message.unix_fds:
        os.close(fd)
    if synthesis or message.unix_fds and message.message_type == MessageType.METHOD_CALL:
        return Message.new_error(message, 'org.freedesktop.DBus.Error.InvalidArgs', 'Expected one Spiel speech pipe')
    return True if message.unix_fds else None


async def serve(path):
    service = spiel.service_path()
    record, registration = spiel.load_registration()
    command = spiel.invocation(path)
    if not record or record['command'] != command:
        return  # A queued activation may outlive the registration.
    executable = Path(command[0])
    original = executable.stat()
    provider = Provider(path)
    bus = await MessageBus(negotiate_unix_fd=True).connect()
    bus.add_message_handler(check_descriptors)
    bus.export(spiel.OBJECT_PATH, provider)
    disconnected = asyncio.create_task(bus.wait_for_disconnect())
    try:
        if await bus.request_name(spiel.BUS_NAME, NameFlag.DO_NOT_QUEUE) != RequestNameReply.PRIMARY_OWNER:
            return
        while not disconnected.done():
            await asyncio.wait([disconnected], timeout=.5)
            try:
                if service.read_bytes() != registration or not os.path.samestat(original, executable.stat()):
                    break
            except FileNotFoundError:
                break
            provider.refresh()
    finally:
        for pipe in provider.requests.values():
            pipe.stopped.set()
        if not disconnected.done():
            bus.disconnect()
        await asyncio.gather(disconnected, *provider.requests, return_exceptions=True)
