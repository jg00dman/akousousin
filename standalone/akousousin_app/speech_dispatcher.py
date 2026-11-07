# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Speech Dispatcher output-module protocol, with audio returned to its mixer.

No shell commands, independent audio device or global preference changes. Speech
Dispatcher owns playback, priorities and STOP/PAUSE of its queued audio.
"""
import io
import json
import logging
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
import unicodedata
import xml.etree.ElementTree as ET
import shlex

from . import runtime, settings
from .transport import fetch

MAX_MESSAGE = 65536


def chunks(text, limit=240):
    while len(text) > limit:
        sentence = re.search(r'[.!?]\s', text[39:limit])
        boundary = max(text.rfind(' ', 40, limit), text.rfind('\n', 40, limit))
        end = 39 + sentence.end() if sentence else boundary + 1 if boundary >= 40 else limit
        yield text[:end]
        text = text[end:]
    if text:
        yield text


def escaped(pcm):
    return pcm.replace(b'}', b'}]').replace(b'\n', b'}*')


def speech_parts(text):
    """Keep real marks at bounded synthesis boundaries, never invent timings."""
    if not text.lstrip().startswith('<speak'):
        yield from ((None, part) for part in chunks(text))
        return
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('XML declarations are unsupported')
    root = ET.fromstring(text)
    pending, marker = '', None
    for node in root.iter():
        if node.tag.split('}')[-1] == 'mark':
            name = node.get('name', '')
            if not name or len(name) > 256 or any(c in name for c in '\r\n\x00'):
                raise ValueError('Invalid index mark')
            if len(pending) >= 160 or name.startswith('__spd_'):
                # Preserve dispatcher sentence marks for pause/resume context.
                yield marker, pending
                pending, marker = '', None
            if not pending.strip():
                if marker:
                    yield marker, pending
                    pending = ''
                marker = name
        elif node.text:
            pending += node.text
        if node is not root and node.tail:
            pending += node.tail
    if marker and not pending:
        yield marker, ''
    for part in chunks(pending):
        yield marker, part
        marker = None


def accessible_text(text, options, character=False):
    """English/Unicode fallback for symbols Piper would otherwise omit."""
    names = {' ': 'space', '\t': 'tab', '\n': 'new line', '.': 'period', ',': 'comma',
             '!': 'exclamation mark', '?': 'question mark', ':': 'colon', ';': 'semicolon',
             '-': 'dash', '_': 'underscore', '/': 'slash', '\\': 'backslash', '@': 'at',
             '#': 'number sign', '$': 'dollar', '%': 'percent', '&': 'ampersand', '*': 'asterisk'}
    level = options.get('punctuation_mode', 'none')
    def name(c):
        return names.get(c, unicodedata.name(c, c).lower())
    if character or options.get('spelling_mode') == 'on':
        return ' '.join(('capital ' if c.isupper() and options.get('cap_let_recogn') == 'spell' else '') +
                        (name(c) if not c.isalnum() else c) for c in text)
    return ''.join(' ' + name(c) + ' ' if unicodedata.category(c).startswith(('P', 'S')) and
                   (level == 'all' or level == 'most' and c not in '.,;:!?' or
                    level == 'some' and c in '@+_') else c for c in text)


class Module:
    def __init__(self, path, source=None, output=None):
        self.path = path
        self.source = source or sys.stdin.buffer
        self.output = output or sys.stdout.buffer
        self.lock = threading.RLock()
        self.options = {}
        self.task = None
        self.cancelled = threading.Event()
        self.request_id = ''
        self.audio_server = False
        self.busy = False

    def send(self, text):
        with self.lock:
            self.output.write(text.encode('utf-8'))
            self.output.flush()

    def block(self):
        lines, size = [], 0
        overflow = False
        while True:
            line = self.source.readline(MAX_MESSAGE + 1)
            if not line:
                raise EOFError
            if line in (b'.\n', b'.\r\n'):
                break
            size += len(line)
            overflow |= size > MAX_MESSAGE
            if not overflow:
                lines.append(line[1:] if line.startswith(b'..') else line)
        if overflow:
            raise ValueError('Message too large')
        return b''.join(lines).decode('utf-8').rstrip('\r\n')

    def parameters(self, command):
        self.send('207 OK RECEIVING SETTINGS\n' if command in ('AUDIO', 'LOGLEVEL') else '203 OK RECEIVING SETTINGS\n')
        pending = dict(line.split('=', 1) for line in self.block().splitlines())
        if command == 'AUDIO':
            if pending != {'audio_output_method': 'server'}:
                raise ValueError('Only Speech Dispatcher server audio is supported')
            self.audio_server = True
        elif command == 'SET':
            for key, allowed in {'punctuation_mode': ('none', 'some', 'most', 'all'), 'spelling_mode': ('on', 'off'),
                                 'cap_let_recogn': ('none', 'spell', 'icon')}.items():
                if key in pending and pending[key] not in allowed:
                    raise ValueError('Invalid speech setting')
            for key in ('rate', 'volume', 'pitch', 'pitch_range'):
                if key in pending and not -100 <= int(pending[key]) <= 100:
                    raise ValueError('Invalid speech parameter')
            self.options.update(pending)
        self.send('203 OK SETTINGS RECEIVED\n')

    def stop(self, paused=False):
        with self.lock:
            if self.cancelled.is_set():
                return
            was_busy = self.busy
            self.cancelled.set()
            request_id = self.request_id
            self.busy = False
            if was_busy:
                self.send('704 PAUSE\n' if paused else '703 STOP\n')
            if not request_id:
                return
        # Never wait for an unresponsive backend in the command-reading thread.
        def cancel():
            try:
                config = settings.load(self.path)
                request = urllib.request.Request(f'http://127.0.0.1:{config["port"]}/cancel',
                    data=b'', headers={'X-Akousousin-Request': request_id})
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=1):
                    pass
            except OSError:
                pass
        threading.Thread(target=cancel, daemon=True).start()

    def speak(self, text, character=False):
        with self.lock:
            if not text or not self.audio_server or self.busy:
                self.send('301 ERROR CANT SPEAK\n')
                return
            self.cancelled = threading.Event()
            self.request_id = uuid.uuid4().hex
            self.busy = True
            self.send('200 OK SPEAKING\n')
            self.task = threading.Thread(target=self.render, args=(text, dict(self.options, character=character), self.cancelled, self.request_id), daemon=True)
            self.task.start()

    def render(self, text, options, cancelled, request_id):
        try:
            runtime.call(self.path, {'command': 'wake'})
            with self.lock:
                if cancelled.is_set():
                    return
                self.send('701 BEGIN\n')
            config = settings.load(self.path)
            voice = options.get('synthesis_voice')
            if voice in (None, 'NULL'):
                language = options.get('language', '').replace('-', '_').casefold()
                preferred = {key.replace('-', '_').casefold(): value
                             for key, value in config['language_voices'].items()}
                voice = preferred.get(language)
                if not voice:
                    voice = next((key for key, entry in config['voices'].items()
                                  if entry['language'].replace('-', '_').casefold() == language), None)
                if not voice:
                    voice = next((key for key, entry in config['voices'].items()
                                  if entry['language'].split('_')[0].casefold() == language.split('_')[0]),
                                 config['voice'])
            if voice not in config['voices']:
                raise ValueError('Voice not installed')
            rate = int(options.get('rate', 0)) / 100
            scale = 1 / (1 + rate) if rate >= 0 else 1 - rate
            for marker, part in speech_parts(text):
                part = accessible_text(part, options, options.get("character", False))
                with self.lock:
                    if cancelled.is_set():
                        return
                    if marker:
                        self.send(f"700-{marker}\n700 INDEX MARK\n")
                if not part.strip():
                    continue
                if cancelled.is_set():
                    return
                data = json.dumps({'text': part, 'voice': voice, 'length_scale': scale,
                                   'volume': (int(options.get('volume', 0)) + 100) / 100,
                                   'sample_rate': config['voices'][voice]['sample_rate']}).encode()
                # A just-cancelled inference may take a short time to release its
                # worker. Keep retries bounded and interruptible, never queue forever.
                deadline = time.monotonic() + 2
                while True:
                    try:
                        audio = fetch(config['port'], data, cancelled, request_id)
                        break
                    except urllib.error.HTTPError as error:
                        if error.code != 503 or time.monotonic() >= deadline or cancelled.wait(.05):
                            raise
                if len(audio) > 64 * 1024 * 1024:
                    raise ValueError('Audio too large')
                with wave.open(io.BytesIO(audio), 'rb') as wav:
                    if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getcomptype() != 'NONE':
                        raise ValueError('Invalid audio format')
                    pcm = wav.readframes(wav.getnframes())
                    if not pcm or len(pcm) != wav.getnframes() * 2:
                        raise ValueError('Truncated audio')
                    sample_rate = wav.getframerate()
                for start in range(0, len(pcm), 8192):
                    block = pcm[start:start + 8192]
                    with self.lock:
                        if cancelled.is_set():
                            return
                        header = (f'705-bits=16\n705-num_channels=1\n705-sample_rate={sample_rate}\n'
                                  f'705-num_samples={len(block)//2}\n705-big_endian=0\n705-AUDIO').encode()
                        self.output.write(header + b'\0' + escaped(block) + b'\n705 AUDIO\n')
                        self.output.flush()
            with self.lock:
                if not cancelled.is_set():
                    self.busy = False
                    self.send('702 END\n')
        except Exception:
            logging.getLogger(__name__).exception('Speech Dispatcher synthesis failed')
            with self.lock:
                if not cancelled.is_set():
                    self.busy = False
                    self.send('703 STOP\n')

    def run(self):
        if self.source.readline(MAX_MESSAGE) != b'INIT\n':
            self.send('399 ERR EXPECTED INIT\n')
            return
        self.send('299-Akousousin neural voice engine\n299 OK LOADED SUCCESSFULLY\n')
        try:
            while True:
                line = self.source.readline(MAX_MESSAGE + 1)
                if not line:
                    return
                command = line.decode('utf-8').strip()
                try:
                    if command in ('SET', 'AUDIO', 'LOGLEVEL'):
                        self.parameters(command)
                    elif command in ('SPEAK', 'CHAR', 'KEY', 'SOUND_ICON'):
                        self.send('202 OK RECEIVING MESSAGE\n')
                        text = self.block()
                        if command == 'SOUND_ICON':
                            self.send('301 ERROR SOUND ICONS UNSUPPORTED\n')
                        else:
                            self.speak(' ' if text == 'space' else text, command in ('CHAR', 'KEY'))
                    elif command.startswith('LIST VOICES'):
                        config = settings.load(self.path)
                        language = command.split()[2:3]
                        for key, voice in config['voices'].items():
                            code = voice['language'].replace('_', '-')
                            if language and code.casefold() != language[0].casefold() and code.split('-')[0].casefold() != language[0].casefold():
                                continue
                            if any(c in key + voice['language'] for c in '\t\r\n'):
                                continue
                            self.send(f'200-{key}\t{voice["language"].replace("_", "-")}\tnone\n')
                        self.send('200 OK VOICE LIST SENT\n')
                    elif command in ('STOP', 'PAUSE'):
                        self.stop(command == 'PAUSE')
                    elif command == 'QUIT':
                        self.stop()
                        self.send('210 OK QUIT\n')
                        return
                    elif command.startswith('DEBUG '):
                        self.send('200 OK DEBUGGING OFF\n')
                    else:
                        self.send('300 ERR UNKNOWN COMMAND\n')
                except (ValueError, UnicodeError, ET.ParseError):
                    self.send('303 ERROR INVALID PARAMETER OR VALUE\n')
        except EOFError:
            return
        finally:
            self.stop()


# Speech Dispatcher disables module autodiscovery when any AddModule is present.
# Its GLib user-data directory is $XDG_DATA_HOME (normally ~/.local/share), and
# it discovers user binaries in the sibling libexec/speech-dispatcher-modules.
SYSTEM_CONFIGS = ('/etc/speech-dispatcher/speechd.conf',
                  '/usr/local/etc/speech-dispatcher/speechd.conf')
LAUNCHER_HEADER = '#!/bin/sh\n# Akousousin managed Speech Dispatcher module\n'
DEFAULT_BLOCK = '\n# Akousousin default output module\nDefaultModule "akousousin"\n# End Akousousin default output module\n'


def dispatcher_paths():
    import os
    from pathlib import Path
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'speech-dispatcher/speechd.conf'
    launcher = settings.data_path() / 'speech-dispatcher-module'
    discovered = settings.data_path().parent.parent / 'libexec/speech-dispatcher-modules/sd_akousousin'
    return config, launcher, discovered


def without_registration(text, launcher):
    """Remove our directive, rejecting a registration owned by another install."""
    kept, owned = [], False
    for line in text.splitlines(keepends=True):
        fields = shlex.split(line, comments=True)
        if len(fields) >= 2 and [field.lower() for field in fields[:2]] == ['addmodule', 'akousousin']:
            if len(fields) < 3 or fields[2] != str(launcher):
                raise ValueError('Module points at another installation; left unchanged')
            owned = True
        elif line.strip() != '# Akousousin user speech module':
            kept.append(line)
    return ''.join(kept), owned


def explicit_modules(text, include_directory, seen=None):
    """Follow dotconf Includes using the daemon's system configuration directory."""
    import glob
    from pathlib import Path
    seen = set() if seen is None else seen
    for line in text.splitlines():
        fields = shlex.split(line, comments=True)
        if not fields:
            continue
        if fields[0].lower() == 'addmodule':
            return True
        if fields[0].lower() == 'include' and len(fields) == 2:
            pattern = Path(fields[1])
            if not pattern.is_absolute():
                pattern = include_directory / pattern
            for name in sorted(glob.glob(str(pattern))):
                file = Path(name).resolve()
                if file not in seen:
                    seen.add(file)
                    if explicit_modules(file.read_text(), include_directory, seen):
                        return True
    return False


def install(path, set_default=True):
    """Register AKS and optionally select it, retaining all other engine choices."""
    import os
    from pathlib import Path
    if os.name == 'nt':
        raise ValueError('Speech Dispatcher integration is for Linux')
    if set_default:
        preferences = settings.load(path)
        if preferences['voice'] not in preferences['voices']:
            raise RuntimeError('Download or import a voice in Voice library before installing Speech Dispatcher support.')
    config, launcher, discovered = dispatcher_paths()
    previous = config.read_text() if config.exists() else ''
    existing, owned = without_registration(previous, launcher)
    # Repair the minimal user config made by older AKS installers. That file
    # shadowed the system config and its AddModule disabled autodiscovery.
    user_config = config.exists() and not (owned and not existing.strip())
    system = next((Path(name) for name in SYSTEM_CONFIGS if Path(name).is_file()), None)
    include_directory = system.parent if system else config.parent
    effective = existing if user_config else system.read_text() if system else ''
    if set_default and not user_config and system:
        existing = f'Include "{system}"\n'
    if discovered.exists() and not discovered.read_text().startswith(LAUNCHER_HEADER):
        raise ValueError('Another installation owns the discovered akousousin module; left unchanged')
    for file in (launcher, discovered):
        if any(c in str(file) for c in '\r\n"'):
            raise ValueError('Unsupported Speech Dispatcher launcher path')
    explicit = explicit_modules(effective, include_directory)
    if explicit:
        if not user_config and system:
            existing = f'Include "{system}"\n'
        registration = f'AddModule "akousousin" "{launcher}" ""'
        existing = existing.rstrip('\n') + '\n# Akousousin user speech module\n' + registration + '\n'
    if set_default:
        existing = existing.replace(DEFAULT_BLOCK, '')
        existing += ('' if not existing or existing.endswith('\n') else '\n') + DEFAULT_BLOCK
    command = runtime.command('--speech-dispatcher', '--settings', str(Path(path).resolve()))
    for file in (launcher, discovered):
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(LAUNCHER_HEADER + 'exec ' + shlex.join(command) + '\n', encoding='utf-8')
        file.chmod(0o700)
    if explicit or user_config or set_default:
        if existing != previous:
            config.parent.mkdir(parents=True, exist_ok=True)
            temporary = config.with_suffix('.tmp')
            temporary.write_text(existing, encoding='utf-8')
            temporary.replace(config)
    elif owned:
        config.unlink()
    return config


def uninstall(path):
    """Remove only our registration and launchers, retaining other engine choices."""
    config, launcher, discovered = dispatcher_paths()
    previous = config.read_text() if config.exists() else ''
    kept, owned = without_registration(previous, launcher)
    owned_default = DEFAULT_BLOCK in kept
    kept = kept.replace(DEFAULT_BLOCK, '')
    if discovered.exists() and not discovered.read_text().startswith(LAUNCHER_HEADER):
        raise ValueError('Another installation owns the discovered akousousin module; left unchanged')
    if (owned or owned_default) and not kept.strip():
        config.unlink()
    elif kept != previous:
        temporary = config.with_suffix('.tmp')
        temporary.write_text(kept)
        temporary.replace(config)
    discovered.unlink(missing_ok=True)
    launcher.unlink(missing_ok=True)
    return config


RESTART_COMMAND = 'env -u LD_LIBRARY_PATH -u LD_PRELOAD systemctl --user restart speech-dispatcher.service'


class RestartError(RuntimeError):
    title = 'Restart Speech Dispatcher'
    message = ('Registration saved; Speech Dispatcher could not be restarted. '
               'Run this command in your normal terminal. No sudo is needed.')
    command = RESTART_COMMAND

    def __init__(self, details):
        self.details = details
        super().__init__(self.message + '\n\n' + self.command + '\n\n' + details)


def configure(path, remove=False):
    """Save registration first; restart only this user's systemd service last."""
    import subprocess
    config = (uninstall if remove else install)(path)
    # A nested AppImage launch can put a previous mount's libraries in ORIG.
    # systemctl must use the host's libraries, including its own OpenSSL.
    environment = runtime.host_environment()
    try:
        subprocess.run(['systemctl', '--user', 'restart', 'speech-dispatcher.service'],
                       check=True, capture_output=True, text=True, timeout=20, env=environment)
        subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'speech-dispatcher.service'],
                       check=True, capture_output=True, text=True, timeout=5, env=environment)
    except (OSError, subprocess.SubprocessError) as error:
        detail = getattr(error, 'stderr', '') or str(error)
        if isinstance(detail, bytes):
            detail = detail.decode(errors='replace')
        raise RestartError(detail.strip()) from error
    return config


def verify_reading_engine(path):
    """Check AKS and the selected Piper voice without speaking or using fallbacks."""
    import socket
    from .selection import SpeechClient, dispatcher_socket
    config = settings.load(path)
    if config['voice'] not in config['voices']:
        raise RuntimeError('Download or import a voice in Voice library before enabling reading shortcuts.')
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(5)
        connection.connect(dispatcher_socket())
        client = SpeechClient(connection)
        modules = client.command('LIST OUTPUT_MODULES')
        if not any(line[3:4] == '-' and line[4:].split()[0] == 'akousousin' for line in modules):
            raise RuntimeError('Akousousin is not available in Speech Dispatcher; reading shortcuts remain disabled.')
        client.command('SET SELF OUTPUT_MODULE akousousin')
        voices = client.command('LIST SYNTHESIS_VOICES')
        if not any(line[3:4] == '-' and line[4:].split()[0] == config['voice'] for line in voices):
            raise RuntimeError('The selected Akousousin voice is unavailable in Speech Dispatcher. Reinstall speech support in Settings.')


def prepare_reading(path):
    """Ensure voice, installed support and a usable module before portal consent."""
    config = settings.load(path)
    if config['voice'] not in config['voices']:
        raise RuntimeError('Download or import a voice in Voice library before enabling reading shortcuts.')
    file, launcher, discovered = dispatcher_paths()
    if file.is_file() and launcher.is_file() and discovered.is_file() and DEFAULT_BLOCK in file.read_text():
        try:
            verify_reading_engine(path)
            return
        except (OSError, RuntimeError):
            pass  # Repair saved registration or a stopped daemon once.
    configure(path)
    verify_reading_engine(path)
