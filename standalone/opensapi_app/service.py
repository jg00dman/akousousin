"""Manage only a server started by this panel; never signal an unrelated PID."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
import uuid
import secrets

from . import runtime


def command(*args):
    return [sys.executable, *args] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'opensapi_app.main', *args]


class Service:
    def __init__(self, settings):
        self.settings = Path(settings)
        self.process = None
        self.instance = uuid.uuid4().hex
        base = runtime.directory() / runtime.name(self.settings).split('/')[-1]
        self.record = base.with_suffix('.server.json')
        self.control = base.with_suffix('.control')
        self.log = runtime.log_path()
        self.log.parent.mkdir(parents=True, exist_ok=True)

    def health(self, port):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(f'http://127.0.0.1:{port}/health', timeout=1) as response:
                data = json.load(response)
            return data if data.get('service') == 'opensapi-piper' else None
        except (OSError, ValueError):
            return None

    def start(self, port):
        if self.record.exists():
            record = json.loads(self.record.read_text())
            if record.get('port', port) != port:
                self.stop(record['port'])
        existing = self.health(port)
        if existing:
            if existing.get('settings') != str(self.settings.resolve()):
                raise RuntimeError('This port is used by another Piper service; choose another port or stop it yourself')
            return existing
        token = secrets.token_hex(32)
        descriptor = os.open(self.control, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.chmod(self.control, 0o600)
        with os.fdopen(descriptor, 'w') as secret:
            secret.write(token)
        self.record.write_text(json.dumps({'instance': self.instance, 'settings': str(self.settings.resolve()), 'port': port}))
        invocation = command()
        with self.log.open('ab') as output:
            options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {
                'start_new_session': True}
            self.process = subprocess.Popen(invocation + ['--serve', '--settings', str(self.settings),
                                                    '--instance', self.instance, '--control-file', str(self.control)], stdin=subprocess.DEVNULL,
                                            stdout=output, stderr=output, **options)
        deadline = time.monotonic() + 65
        while self.process.poll() is None and time.monotonic() < deadline:
            status = self.health(port)
            if status and status.get('instance') == self.instance and status.get('ready'):
                return status
            time.sleep(.2)
        self.stop(port)
        raise RuntimeError(f'Server did not become ready. See {self.log}')

    def stop(self, port):
        if self.record.exists():
            record = json.loads(self.record.read_text())
            if record.get('settings') == str(self.settings.resolve()):
                port = record.get('port', port)
        status = self.health(port)
        if status:
            try:
                record = json.loads(self.record.read_text())
                if record['instance'] != status.get('instance') or status.get('settings') != str(self.settings.resolve()):
                    return False
                token = self.control.read_text()
                request = urllib.request.Request(f'http://127.0.0.1:{port}/shutdown', data=b'',
                                                  headers={'X-OpenSAPI-Control': token})
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(request, timeout=5):
                    pass
                deadline = time.monotonic() + 6
                while time.monotonic() < deadline:
                    current = self.health(port)
                    if not current or current.get('instance') != record['instance']:
                        if self.process is not None:
                            try:
                                self.process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                break  # Fall through to the owned-process cleanup below.
                            self.process = None
                        return True
                    time.sleep(.1)
                if self.process is None:
                    raise RuntimeError('Server acknowledged stop but has not exited yet')
            except (OSError, ValueError, KeyError):
                if self.process is None or self.process.poll() is not None:
                    return False
        if self.process is None or self.process.poll() is not None:
            return False
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        else:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.process = None
        return True
