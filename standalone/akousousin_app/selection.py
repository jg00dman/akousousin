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

from . import runtime, settings

MAX_TEXT = 1024 * 1024


def host_environment():
    env = runtime.environment()
    if 'LD_LIBRARY_PATH_ORIG' in env:
        env['LD_LIBRARY_PATH'] = env['LD_LIBRARY_PATH_ORIG']
    else:
        env.pop('LD_LIBRARY_PATH', None)
    env.pop('QT_PLUGIN_PATH', None)
    env.pop('QT_QPA_PLATFORM_PLUGIN_PATH', None)
    return env


def selected_text(clipboard=False):
    if os.environ.get('WAYLAND_DISPLAY'):
        tool = shutil.which('wl-paste')
        if not tool:
            raise RuntimeError('Install wl-clipboard to read selections on Wayland.')
        command = [tool, '--type', 'text', '--no-newline'] + ([] if clipboard else ['--primary'])
    elif os.environ.get('DISPLAY'):
        tool = shutil.which('xclip')
        if not tool:
            raise RuntimeError('Install xclip to read selections on X11.')
        command = [tool, '-selection', 'clipboard' if clipboard else 'primary', '-o']
    else:
        raise RuntimeError('Read selection requires a Wayland or X11 desktop session.')
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.PIPE,
                                timeout=3, env=host_environment(), check=False)
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
            code, lines = self.response()
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
        SpeechClient(connection).read(text, cancelled, settings.load(path)['voice'])
    finally:
        connection.close()


def toggle(path, clipboard=False, reader=selected_text, speaker=speak):
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
        cancelled, errors = threading.Event(), []
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
        if any(any(c in arg for c in '\r\n\0') for arg in arguments):
            raise ValueError('Unsupported newline or control character in the launcher path')
        # Desktop Exec syntax is not shell syntax; quote every argument and
        # escape desktop-entry field codes, rather than interpolating text.
        return ' '.join('"' + arg.replace('\\', '\\\\\\\\').replace('"', '\\\\"').replace('`', '\\\\`')
                        .replace('$', '\\\\$').replace('%', '%%') + '"'
                        for arg in arguments)
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
