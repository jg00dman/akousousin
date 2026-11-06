# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import unittest

from akousousin_app.transport import fetch


class Handler(BaseHTTPRequestHandler):
    mode = 'valid'
    release = threading.Event()
    def log_message(self, *args):
        pass
    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        try:
            if self.mode == 'stall':
                self.release.wait(2)
                return
            self.send_response(200)
            self.send_header('Content-Length', '100' if self.mode == 'trickle' else '4')
            self.end_headers()
            if self.mode == 'trickle':
                while not self.release.wait(.05):
                    self.wfile.write(b'x')
                    self.wfile.flush()
            else:
                self.wfile.write(b'PCM!')
        except OSError:
            pass


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        Handler.release.set()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
    def setUp(self):
        Handler.mode = 'valid'
        Handler.release.clear()
    def tearDown(self):
        Handler.release.set()
        time.sleep(.06)
    def test_success(self):
        self.assertEqual(fetch(self.server.server_port, b'{}', threading.Event(), 'id'), b'PCM!')
    def test_trickling_response_has_total_deadline(self):
        Handler.mode = 'trickle'
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            fetch(self.server.server_port, b'{}', threading.Event(), 'id', timeout=.2)
        self.assertLess(time.monotonic() - started, .7)
    def test_cancellation_before_headers_is_responsive(self):
        Handler.mode = 'stall'
        cancelled = threading.Event()
        timer = threading.Timer(.1, cancelled.set)
        timer.start()
        started = time.monotonic()
        with self.assertRaises(InterruptedError):
            fetch(self.server.server_port, b'{}', cancelled, 'id')
        timer.join()
        self.assertLess(time.monotonic() - started, .7)
