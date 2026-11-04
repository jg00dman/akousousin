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
subprocess.run([str(executable), '--settings', str(settings_path), '--install-speech-dispatcher'], check=True, timeout=45)
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
        print('PASS: real Speech Dispatcher voices, PCM delivery, stop and recovery', flush=True)
    finally:
        connection.close()
        daemon.terminate()
        try:
            daemon.wait(timeout=10)
        except subprocess.TimeoutExpired:
            daemon.kill()
            daemon.wait(timeout=5)
        subprocess.run([str(executable), '--settings', str(settings_path), '--quit'], timeout=30)
