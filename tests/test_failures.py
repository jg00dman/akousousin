#!/usr/bin/env python3
"""Failure/recovery checks in disposable CI prefixes, in addition to all 13 original tests."""
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import unittest
import test_integration as integration
from test_integration import Handler, PCM, ROOT, wav_bytes


class FailureHandler(Handler):
    attempt = 0
    release = threading.Event()

    def do_POST(self):
        mode = self.mode
        if mode == 'refuse':
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if mode in ('stall', 'trickle', 'drop'):
            self.rfile.read(int(self.headers['Content-Length']))
            if mode != 'stall':
                data = wav_bytes()
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data[:100])
                self.wfile.flush()
                if mode == 'drop':
                    self.close_connection = True
                    return
                for _ in range(140):
                    if self.release.wait(0.5):
                        return
                    try:
                        self.wfile.write(b'\x00\x00')
                        self.wfile.flush()
                    except OSError:
                        return
            else:
                self.release.wait(75)
            return
        if mode == 'recover':
            type(self).attempt += 1
            if self.attempt == 1:
                self.send_error(503)
                return
        super().do_POST()


class FailureTests(unittest.TestCase):
    run_probe = integration.IntegrationTests.run_probe

    @classmethod
    def setUpClass(cls):
        import tempfile
        from http.server import ThreadingHTTPServer
        cls.server = ThreadingHTTPServer(('127.0.0.1', 5000), FailureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.temp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        FailureHandler.release.set()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def setUp(self):
        FailureHandler.release.clear()
        FailureHandler.mode = 'valid'

    def tearDown(self):
        FailureHandler.release.set()

    def test_network_cancellation_before_headers_and_during_body(self):
        for mode in ('stall', 'trickle'):
            with self.subTest(mode=mode):
                FailureHandler.mode = mode
                started = time.monotonic()
                output = self.run_probe(direct=True, mode='abort-network')
                self.assertLess(time.monotonic() - started, 3)
                self.assertEqual(output.read_bytes(), b'')
                FailureHandler.release.set()
                time.sleep(0.1)
                FailureHandler.release.clear()

    def test_dropped_response_is_rejected(self):
        FailureHandler.mode = 'drop'
        self.assertEqual(self.run_probe(direct=True, fail=True).read_bytes(), b'')

    def test_http_failure_recovers_on_same_engine(self):
        FailureHandler.mode = 'recover'
        FailureHandler.attempt = 0
        self.assertEqual(self.run_probe(direct=True, mode='recover').read_bytes(), PCM)

    def test_uninitialized_engine(self):
        self.assertEqual(self.run_probe(direct=True, mode='uninitialized', fail=True).read_bytes(), b'')

    def test_backend_not_listening(self):
        # Use an unbound alternate port; restore the registered token even on failure.
        wine = os.environ['WINE']
        key = r'HKLM\SOFTWARE\Microsoft\Speech\Voices\Tokens\OpenSAPI-Piper'
        def port(value):
            subprocess.run([wine, 'reg.exe', 'add', key, '/v', 'Port', '/t', 'REG_DWORD',
                            '/d', str(value), '/f', '/reg:64'], check=True, capture_output=True, timeout=20)
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1', 0))
            unused = reserve.getsockname()[1]
            port(unused)
            try:
                started = time.monotonic()
                self.assertEqual(self.run_probe(direct=True, fail=True).read_bytes(), b'')
                self.assertLess(time.monotonic() - started, 5)
            finally:
                port(5000)

    def test_total_timeout_including_trickling_response(self):
        FailureHandler.mode = 'trickle'
        started = time.monotonic()
        self.assertEqual(self.run_probe(direct=True, fail=True).read_bytes(), b'')
        self.assertLess(time.monotonic() - started, 70)

    def test_missing_registered_voice_and_stale_default(self):
        if not (Path(os.environ['WINEPREFIX']) / '.opensapi-test-prefix').exists():
            self.fail('Refusing registry mutation outside disposable CI prefix')
        wine = os.environ['WINE']
        key = r'HKLM\SOFTWARE\Microsoft\Speech\Voices\Tokens\OpenSAPI-Piper'
        backup = Path(self.temp.name) / 'token.reg'
        subprocess.run([wine, 'reg.exe', 'export', key, 'Z:' + str(backup), '/y'], check=True,
                       capture_output=True, timeout=20)
        try:
            subprocess.run([wine, 'reg.exe', 'delete', key, '/f', '/reg:64'], check=True,
                           capture_output=True, timeout=20)
            result = subprocess.run([wine, str(ROOT / 'build/sapi-probe.exe'), 'unused', '0', '100',
                                     'No registered voice', 'missing'], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('voices: 0', result.stdout)
        finally:
            subprocess.run([wine, 'regedit.exe', '/S', 'Z:' + str(backup)], check=True,
                           capture_output=True, timeout=20)


if __name__ == '__main__':
    unittest.main(verbosity=2)
