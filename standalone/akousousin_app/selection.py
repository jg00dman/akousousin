# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Selection reading with a private toggle socket and a dedicated SSIP client."""
from collections import deque
import os
from pathlib import Path
import re
import select
import shutil
import socket
import subprocess
import tempfile
import threading
import time

from . import runtime, settings, resources

MAX_TEXT = 1024 * 1024


def host_environment():
    return runtime.host_environment()


def clipboard_reader(name, package):
    environment = host_environment()
    tool = shutil.which(name)
    if not tool:
        folder = resources.root() / 'helpers' / name
        bundled = folder / 'bin' / name
        if bundled.is_file() and os.access(bundled, os.X_OK):
            tool = str(bundled)
            environment['LD_LIBRARY_PATH'] = str(folder / 'lib')
    if not tool:
        raise RuntimeError(f'Clipboard helper unavailable. Install {package} or use an AppImage that bundles it.')
    return tool, environment


def selected_text(clipboard=False):
    if os.environ.get('WAYLAND_DISPLAY') and os.environ.get('XDG_SESSION_TYPE') != 'x11':
        tool, environment = clipboard_reader('wl-paste', 'wl-clipboard')
        command = [tool, '--type', 'text', '--no-newline'] + ([] if clipboard else ['--primary'])
    elif os.environ.get('DISPLAY'):
        tool, environment = clipboard_reader('xclip', 'xclip')
        command = [tool, '-selection', 'clipboard' if clipboard else 'primary', '-o']
    else:
        raise RuntimeError('Read selection requires a Wayland or X11 desktop session.')
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.PIPE,
                                timeout=3, env=environment, check=False)
        output.seek(0, 2)
        if output.tell() > MAX_TEXT:
            raise ValueError('The selection is too large. Select a smaller passage.')
        output.seek(0)
        text = output.read().decode('utf-8')
    if result.returncode or not text.strip():
        raise RuntimeError('No text is available. Highlight text first, or copy it and use Read clipboard / Stop.')
    if '\0' in text:
        raise ValueError('The selection is not plain text.')
    return text


def dispatcher_socket():
    address = os.environ.get('SPEECHD_ADDRESS')
    if address:
        if not address.startswith('unix_socket:') or not address[12:]:
            raise ValueError('Selection reading requires a local Speech Dispatcher Unix socket.')
        return address[12:]
    base = Path(os.environ.get('XDG_RUNTIME_DIR', os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')))
    return os.environ.get('SPEECHD_SOCKET', str(base / 'speech-dispatcher/speechd.sock'))


class SpeechClient:
    def __init__(self, connection):
        self.connection = connection
        self.buffer = b''
        self.events = deque()

    def response(self, cancelled=None, timeout=10):
        deadline, lines, total = time.monotonic() + timeout, [], 0
        while True:
            if cancelled is not None and cancelled.is_set():
                raise InterruptedError('Reading stopped')
            if time.monotonic() >= deadline:
                raise TimeoutError('Speech Dispatcher did not respond')
            if b'\n' not in self.buffer:
                if not select.select([self.connection], [], [], .1)[0]:
                    continue
                block = self.connection.recv(8192)
                if not block:
                    raise ConnectionError('Speech Dispatcher disconnected')
                self.buffer += block
                if len(self.buffer) > 65536:
                    raise ValueError('Speech Dispatcher response is too large')
                continue
            line, self.buffer = self.buffer.split(b'\n', 1)
            total += len(line)
            if total > 65536 or len(line) < 4 or not line[:3].isdigit() or line[3:4] not in (b'-', b' '):
                raise ValueError('Invalid Speech Dispatcher response')
            lines.append(line.rstrip(b'\r').decode('utf-8'))
            if line[3:4] == b' ':
                return int(line[:3]), lines

    def command(self, text, cancelled=None):
        if cancelled is not None and cancelled.is_set():
            raise InterruptedError('Reading stopped')
        self.connection.sendall(text.encode('utf-8') + b'\r\n')
        while True:
            code, lines = self.response(cancelled)
            if code >= 700:
                self.events.append((code, lines))
            elif 200 <= code < 300:
                return lines
            else:
                raise RuntimeError('Speech Dispatcher: ' + lines[-1][4:])

    def read(self, text, cancelled, voice=''):
        try:
            for command in ('SET SELF CLIENT_NAME akousousin:selection:reader',
                            'SET SELF OUTPUT_MODULE akousousin', 'SET SELF PRIORITY TEXT',
                            'SET SELF SSML_MODE off', 'SET SELF NOTIFICATION END ON',
                            'SET SELF NOTIFICATION CANCEL ON', 'SET SELF RATE 0', 'SET SELF VOLUME 0'):
                self.command(command, cancelled)
            if voice:
                if not re.fullmatch(r'[A-Za-z0-9_-]+', voice):
                    raise ValueError('Invalid configured voice identifier')
                self.command('SET SELF SYNTHESIS_VOICE ' + voice, cancelled)
            active = self.command('GET OUTPUT_MODULE', cancelled)
            if not any(line[3:4] == '-' and line[4:].strip() == 'akousousin' for line in active):
                raise RuntimeError('Speech Dispatcher did not select Akousousin; reading was stopped.')
            # Keep even markup-expanded module messages bounded. Wait for each
            # message so cancellation never needs to affect another client's queue.
            for part in text_parts(text):
                self.command('SPEAK', cancelled)
                lines = self.command(encode_text(part))
                message = lines[0][4:]
                while True:
                    code, event = self.events.popleft() if self.events else self.response(cancelled, 4 * 3600)
                    if code in (702, 703) and event[0][4:] == message:
                        if code == 703:
                            return
                        break
        finally:
            # SELF refers to this still-open connection, even after daemon restart.
            # Never use spd-say --stop/--cancel, which affect other clients.
            try:
                self.command('CANCEL SELF')
            except (OSError, ValueError, RuntimeError):
                pass
            self.connection.close()


def text_parts(text, limit=800):
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    while text:
        end = min(len(text), limit)
        if end < len(text):
            boundary = max(text.rfind(' ', limit // 2, end), text.rfind('\n', limit // 2, end))
            if boundary >= 0:
                end = boundary + 1
        yield text[:end]
        text = text[end:]


def encode_text(text):
    return '\r\n'.join('.' + line if line.startswith('.') else line for line in text.split('\n')) + '\r\n.'


def speak(text, cancelled, path):
    config = settings.load(path)
    if not config['voices']:
        raise RuntimeError('Download or import a voice in Voice library before reading selected text.')
    address = dispatcher_socket()
    connection = socket.socket(socket.AF_UNIX)
    connection.settimeout(5)
    try:
        try:
            connection.connect(address)
        except (FileNotFoundError, ConnectionRefusedError):
            tool = shutil.which('speech-dispatcher')
            if not tool:
                raise RuntimeError('Install Speech Dispatcher and Akousousin speech support first.')
            subprocess.run([tool, '--spawn', '--socket-path', address], env=host_environment(),
                           capture_output=True, check=True, timeout=10)
            connection.connect(address)
        SpeechClient(connection).read(text, cancelled, config['voice'])
    finally:
        connection.close()


def toggle(path, clipboard=False, reader=selected_text, speaker=speak, cancelled=None):
    """One foreground reader per profile; repeat invocations request stop only."""
    if os.name == 'nt':
        raise RuntimeError('Selection reading is currently for Linux desktops.')
    import fcntl
    base = Path(runtime.name(path))
    control = base.with_suffix('.reading.sock')
    with base.with_suffix('.reading.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                try:
                    with socket.socket(socket.AF_UNIX) as connection:
                        connection.settimeout(.5)
                        connection.connect(str(control))
                        connection.sendall(b'STOP\n')
                        if connection.recv(16) == b'OK\n':
                            return 'Stopped reading.'
                except OSError:
                    time.sleep(.05)
            raise RuntimeError('Selection reader is finishing; try the shortcut again.')
        control.unlink(missing_ok=True)
        cancelled = cancelled if cancelled is not None else threading.Event()
        errors = []
        def read():
            try:
                text = reader(clipboard)
                if not cancelled.is_set():
                    speaker(text, cancelled, path)
            except InterruptedError:
                pass
            except Exception as error:
                errors.append(error)
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(control))
            server.listen(4)
            server.settimeout(.1)
            worker = threading.Thread(target=read)
            worker.start()
            try:
                while worker.is_alive():
                    try:
                        connection, _ = server.accept()
                    except socket.timeout:
                        continue
                    with connection:
                        connection.settimeout(.5)
                        if connection.recv(16) == b'STOP\n':
                            cancelled.set()
                            connection.sendall(b'OK\n')
            finally:
                if worker.is_alive():
                    cancelled.set()
                worker.join()
                control.unlink(missing_ok=True)
        if errors:
            raise errors[0]
    return 'Reading finished.'


def install_action(path):
    if os.name == 'nt':
        raise RuntimeError('The selection shortcut action is for Linux desktops.')
    def command(flag):
        arguments = ['/usr/bin/env', 'APPIMAGE_EXTRACT_AND_RUN=1', 'PYINSTALLER_RESET_ENVIRONMENT=1',
                     *runtime.command(flag, '--settings', str(Path(path).resolve()))]
        from .desktop_identity import desktop_exec
        return desktop_exec(arguments)

    directory = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'applications'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'akousousin-read-selection.desktop'
    target.write_text('[Desktop Entry]\nType=Application\nName=Akousousin Read selected text / Stop\n'
                      'Comment=Read highlighted text; run again to stop only this reading\n'
                      'Icon=audio-volume-high\nTerminal=false\nStartupNotify=false\n'
                      'Categories=AudioVideo;Accessibility;\nActions=ReadClipboard;\nExec=' + command('--read-selection') +
                      '\n\n[Desktop Action ReadClipboard]\nName=Read clipboard / Stop\nExec=' + command('--read-clipboard') + '\n')
    return target


def notify(message):
    tool = shutil.which('notify-send')
    if tool:
        try:
            if subprocess.run([tool, '--app-name=Akousousin', 'Akousousin', message],
                              env=host_environment(), timeout=3, check=False).returncode == 0:
                return
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('Akousousin selection reader', message, parent=root)
        root.destroy()
    except Exception:
        pass  # The CLI also reports the error to stderr when no desktop is available.
