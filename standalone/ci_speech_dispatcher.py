# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Real Speech Dispatcher daemon + packaged module + Piper, using ALSA null.

This verifies protocol/audio delivery, not audible playback or a screen reader.
All daemon configuration, sockets and logs belong to this disposable CI run.
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import json
import shlex

executable, settings_path = map(lambda p: Path(p).resolve(), sys.argv[1:3])
work = settings_path.parent / 'speech-dispatcher'
work.mkdir(parents=True, exist_ok=True)
logs = work / 'logs'
logs.mkdir(exist_ok=True)
subprocess.run([str(executable), '--settings', str(settings_path), '--download-starter-voice'],
               check=True, timeout=180)
installed = subprocess.run([str(executable), '--settings', str(settings_path), '--install-speech-dispatcher'],
                           capture_output=True, text=True, timeout=45)
# Hosted CI has no systemd user session. Registration must still be saved, and
# only that explicit restart failure is acceptable before our isolated daemon test.
if installed.returncode:
    assert 'Registration saved; Speech Dispatcher could not be restarted.' in installed.stderr, installed.stderr
    print('Expected headless user-service restart failure:', installed.stderr, flush=True)
launcher = Path(os.environ['XDG_DATA_HOME']) / 'Akousousin/speech-dispatcher-module'
sockpath = work / 'socket'
fixtures = work / 'selection-fixture'
fixtures.mkdir(exist_ok=True)
selected = fixtures / 'text.txt'; selected.write_text('Packaged selection reading works.')
copied = fixtures / 'clipboard.txt'; copied.write_text('Copied text is read only when explicitly requested.')
paste = fixtures / 'wl-paste'
paste.write_text('#!/bin/sh\ncase " $* " in *" --primary "*) exec /bin/cat ' + shlex.quote(str(selected)) +
                 ';; *) exec /bin/cat ' + shlex.quote(str(copied)) + ';; esac\n')
paste.chmod(0o755)
reader_env = dict(os.environ, WAYLAND_DISPLAY='fixture-only', QT_QPA_PLATFORM='offscreen',
                  SPEECHD_ADDRESS='unix_socket:' + str(sockpath),
                  PATH=str(fixtures) + os.pathsep + os.environ['PATH'])
(work / 'speechd.conf').write_text(f'''LogLevel 5
LogDir "{logs}"
CommunicationMethod "unix_socket"
SocketPath "{sockpath}"
AudioOutputMethod "alsa"
AudioALSADevice "null"
AddModule "akousousin" "{launcher}" ""
AddModule "espeak-ng" "sd_espeak-ng" "espeak-ng.conf"
DefaultModule "espeak-ng"
''')
# Regression: a user registration must add AKS to the real engine list without
# hiding auto-discovered eSpeak. Use normal user-config lookup (no -C) here.
user_config = Path(os.environ['XDG_CONFIG_HOME']) / 'speech-dispatcher/speechd.conf'
user_config.parent.mkdir(parents=True, exist_ok=True)
user_config.write_text(f'LogDir "{logs}"\nAudioOutputMethod "alsa"\nAudioALSADevice "null"\nDefaultModule "espeak-ng"\n')
installed = subprocess.run([str(executable), '--settings', str(settings_path), '--install-speech-dispatcher'],
                           capture_output=True, text=True, timeout=45)
assert not installed.returncode or 'Registration saved;' in installed.stderr, installed.stderr
assert 'AddModule' not in user_config.read_text(), 'Registration disabled module autodiscovery'
with (work / 'discovery.log').open('wb') as discovery_log:
    discovery = subprocess.Popen(['speech-dispatcher', '-s', '-S', str(sockpath), '-P', str(work / 'discovery.pid')],
                                 stdout=discovery_log, stderr=discovery_log, env=reader_env)
    try:
        deadline = time.monotonic() + 20
        with socket.socket(socket.AF_UNIX) as client:
            while True:
                try:
                    client.connect(str(sockpath)); break
                except OSError:
                    if discovery.poll() is not None or time.monotonic() > deadline:
                        raise AssertionError((work / 'discovery.log').read_text(errors='replace'))
                    time.sleep(.1)
            client.settimeout(20)
            client.sendall(b'LIST OUTPUT_MODULES\r\n')
            stream = client.makefile('rb')
            reply = []
            while True:
                line = stream.readline()
                assert line, 'Dispatcher closed module-list connection'
                reply.append(line)
                if line[3:4] == b' ':
                    break
            text = b''.join(reply).decode()
            names = {line[4:].split()[0] for line in text.splitlines() if line[3:4] == '-'}
            assert {'akousousin', 'espeak-ng'} <= names, text
            print('PASS: real engine list retains eSpeak alongside AKS:', text, flush=True)
            client.sendall(b'GET OUTPUT_MODULE\r\n')
            default = []
            while True:
                line = stream.readline()
                assert line, 'Dispatcher closed default-engine query'
                default.append(line)
                if line[3:4] == b' ':
                    break
            assert b'akousousin' in b''.join(default), default
            print('PASS: installing support selects AKS as the real daemon default', flush=True)
    finally:
        discovery.terminate()
        try:
            discovery.wait(10)
        except subprocess.TimeoutExpired:
            discovery.kill(); discovery.wait(5)
        sockpath.unlink(missing_ok=True)

events = []
marks = []
with (work / 'daemon.log').open('wb') as log:
    daemon = subprocess.Popen(['speech-dispatcher', '-s', '-C', str(work), '-S', str(sockpath),
                               '-P', str(work / 'pid')], stdout=log, stderr=log, env=reader_env)
    connection = socket.socket(socket.AF_UNIX)
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                connection.connect(str(sockpath))
                break
            except OSError:
                if daemon.poll() is not None or time.monotonic() >= deadline:
                    raise AssertionError((work / 'daemon.log').read_text(errors='replace'))
                time.sleep(.1)
        connection.settimeout(90)
        stream = connection.makefile('rb')
        def response():
            lines = []
            while True:
                line = stream.readline()
                if not line:
                    raise AssertionError('Speech Dispatcher disconnected')
                lines.append(line)
                if len(line) >= 4 and line[3:4] == b' ':
                    code = int(line[:3])
                    text = b''.join(lines).decode(errors='replace')
                    if code == 700:
                        marks.append(text)
                    print(text, end='', flush=True)
                    return code, text
        def command(text):
            connection.sendall(text.encode() + b'\r\n')
            while True:
                code, result = response()
                if code >= 700:
                    events.append(code)
                    continue
                assert 200 <= code < 300, result
                return result
        def event(wanted):
            if wanted in events:
                events.remove(wanted)
                return
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                code, result = response()
                if code == wanted:
                    return
                assert code < 300 or code >= 700, result
            raise AssertionError(f'Missing event {wanted}')
        command('SET SELF CLIENT_NAME aks:ci:test')
        command('SET SELF OUTPUT_MODULE akousousin')
        command('SET SELF NOTIFICATION ALL ON')
        voices = command('LIST SYNTHESIS_VOICES')
        assert 'en_US-ljspeech-medium' in voices, voices
        command('SPEAK')
        command('Akousousin is speaking through the real Speech Dispatcher daemon.\r\n.')
        event(702)
        events.clear()
        command('SPEAK')
        command(('This speech will be cancelled. ' * 80) + '\r\n.')
        event(701)
        command('STOP SELF')
        event(703)
        # The next utterance must still work after interruption.
        events.clear()
        command('SPEAK')
        command('Speech recovered after cancellation.\r\n.')
        event(702)
        events.clear()
        command('SET SELF SSML_MODE on')
        command('SPEAK')
        command('<speak><mark name="0:5"/>Hello &amp; café.</speak>\r\n.')
        event(702)
        assert any('0:5' in mark for mark in marks), marks
        command('SET SELF SSML_MODE off')
        print('PASS: real Speech Dispatcher voices, PCM, cancellation, recovery and Orca SSML marks', flush=True)
        # Clipboard data is a fixture; the packaged resident controller, SSIP
        # connection, speech and cancellation are real. No compositor is used.
        def reading(*args):
            result = subprocess.run([str(executable), '--settings', str(settings_path), *args], env=reader_env,
                                    capture_output=True, text=True, check=True, timeout=30)
            return json.loads(result.stdout.splitlines()[-1])
        def finished():
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                status = reading('--selection-status')
                if not status['reading']:
                    assert status['state'] in ('Reading finished', 'Reading stopped'), status
                    return status
                time.sleep(.1)
            raise AssertionError('Selection reading did not finish')
        reading('--read-selection'); finished()
        command('SET SELF PRIORITY IMPORTANT')
        command('SPEAK')
        # Keep this comfortably within the 90-second deadline on shared runners.
        # Check below that it is still active when the reader is stopped.
        command(('Another application must finish uninterrupted. ' * 50) + '\r\n.')
        event(701)
        selected.write_text('This long reading will be stopped. ' * 1500)
        assert reading('--read-selection')['reading']
        command('GET OUTPUT_MODULE')  # Drain notifications received during startup.
        assert 702 not in events, 'Other-client fixture finished before the stop test'
        reading('--read-selection')
        assert finished()['state'] == 'Reading stopped'
        event(702)  # Stopping the reader must preserve this other client's speech.
        selected.write_text('The next selection works after stopping.')
        reading('--read-selection'); finished()
        reading('--read-clipboard'); finished()
        print('PASS: packaged resident selection read/stop/reset, explicit clipboard and another client unaffected', flush=True)
    finally:
        connection.close()
        daemon.terminate()
        try:
            daemon.wait(timeout=10)
        except subprocess.TimeoutExpired:
            daemon.kill()
            daemon.wait(timeout=5)
        subprocess.run([str(executable), '--settings', str(settings_path), '--quit'], timeout=30)
