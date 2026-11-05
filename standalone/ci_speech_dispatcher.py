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

executable, settings_path = map(lambda p: Path(p).resolve(), sys.argv[1:3])
work = settings_path.parent / 'speech-dispatcher'
work.mkdir(parents=True, exist_ok=True)
logs = work / 'logs'
logs.mkdir(exist_ok=True)
installed = subprocess.run([str(executable), '--settings', str(settings_path), '--install-speech-dispatcher'],
                           capture_output=True, text=True, timeout=45)
# Hosted CI has no systemd user session. Registration must still be saved, and
# only that explicit restart failure is acceptable before our isolated daemon test.
if installed.returncode:
    assert 'Registration saved; Speech Dispatcher could not be restarted.' in installed.stderr, installed.stderr
    print('Expected headless user-service restart failure:', installed.stderr, flush=True)
launcher = Path(os.environ['XDG_DATA_HOME']) / 'Akousousin/speech-dispatcher-module'
sockpath = work / 'socket'
(work / 'speechd.conf').write_text(f'''LogLevel 5
LogDir "{logs}"
CommunicationMethod "unix_socket"
SocketPath "{sockpath}"
AudioOutputMethod "alsa"
AudioALSADevice "null"
AddModule "akousousin" "{launcher}" ""
DefaultModule "akousousin"
''')
events = []
marks = []
with (work / 'daemon.log').open('wb') as log:
    daemon = subprocess.Popen(['speech-dispatcher', '-s', '-C', str(work), '-S', str(sockpath),
                               '-P', str(work / 'pid')], stdout=log, stderr=log)
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
        # The desktop selection is a fixture; speech, toggle IPC and packaged CLI
        # are real. No compositor or clipboard from the runner is accessed.
        from akousousin_app import runtime
        import shlex
        fixtures = work / 'selection-fixture'
        fixtures.mkdir(exist_ok=True)
        selected = fixtures / 'text.txt'
        selected.write_text('Packaged selection reading works.')
        paste = fixtures / 'wl-paste'
        paste.write_text('#!/bin/sh\nexec /bin/cat ' + shlex.quote(str(selected)) + '\n')
        paste.chmod(0o755)
        reader_env = dict(os.environ, WAYLAND_DISPLAY='fixture-only', SPEECHD_ADDRESS='unix_socket:' + str(sockpath),
                          PATH=str(fixtures) + os.pathsep + os.environ['PATH'], PYINSTALLER_RESET_ENVIRONMENT='1')
        read_command = [str(executable), '--settings', str(settings_path), '--read-selection']
        subprocess.run(read_command, env=reader_env, check=True, timeout=90)
        command('SET SELF PRIORITY IMPORTANT')
        command('SPEAK')
        command(('Another application must finish uninterrupted. ' * 250) + '\r\n.')
        event(701)
        selected.write_text('This long reading will be stopped. ' * 1500)
        with (work / 'selection-reader.log').open('wb') as output:
            reader = subprocess.Popen(read_command, env=reader_env, stdout=output, stderr=output)
            try:
                control = Path(runtime.name(settings_path)).with_suffix('.reading.sock')
                deadline = time.monotonic() + 20
                while not control.exists():
                    assert reader.poll() is None, 'Packaged reader exited before accepting a toggle'
                    assert time.monotonic() < deadline, 'Packaged reader did not start'
                    time.sleep(.05)
                stopped = subprocess.run(read_command, env=reader_env, capture_output=True, text=True,
                                         check=True, timeout=30)
                assert 'Stopped reading.' in stopped.stdout, stopped
                assert reader.wait(timeout=20) == 0
            finally:
                if reader.poll() is None:
                    reader.terminate()
                    reader.wait(timeout=10)
        event(702)  # Cancelling the reader must not cancel the other client.
        selected.write_text('The next selection works after stopping.')
        subprocess.run(read_command, env=reader_env, check=True, timeout=90)
        print('PASS: packaged selection read/stop/reset and another client remains unaffected', flush=True)

    finally:
        connection.close()
        daemon.terminate()
        try:
            daemon.wait(timeout=10)
        except subprocess.TimeoutExpired:
            daemon.kill()
            daemon.wait(timeout=5)
        subprocess.run([str(executable), '--settings', str(settings_path), '--quit'], timeout=30)
