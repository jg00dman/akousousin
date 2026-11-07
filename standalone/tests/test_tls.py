# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Real TLS handshakes over memory BIOs: no sockets or external network."""
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from akousousin_backend import tls


@unittest.skipUnless(shutil.which('openssl'), 'Certificate fixture requires OpenSSL')
class TrustStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.root = Path(cls.directory.name)
        cls.cert, cls.key = cls.root / 'host-ca.pem', cls.root / 'test-key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
                        '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost',
                        '-addext', 'basicConstraints=critical,CA:TRUE',
                        '-keyout', str(cls.key), '-out', str(cls.cert)],
                       check=True, capture_output=True)

    def setUp(self):
        environment = patch.dict(os.environ)
        environment.start(); self.addCleanup(environment.stop)
        os.environ.pop('SSL_CERT_FILE', None)
        os.environ.pop('SSL_CERT_DIR', None)

    def handshake(self, context, hostname='localhost'):
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(self.cert, self.key)
        client_in, client_out, server_in, server_out = (ssl.MemoryBIO() for _ in range(4))
        client = context.wrap_bio(client_in, client_out, server_hostname=hostname)
        server = server_context.wrap_bio(server_in, server_out, server_side=True)
        client_done = server_done = False
        for _ in range(20):
            try:
                client.do_handshake(); client_done = True
            except ssl.SSLWantReadError:
                pass
            server_in.write(client_out.read())
            try:
                server.do_handshake(); server_done = True
            except ssl.SSLWantReadError:
                pass
            client_in.write(server_out.read())
            if client_done and server_done:
                return
        self.fail('TLS handshake did not finish')

    def test_host_bundle_works_when_frozen_openssl_default_paths_are_empty(self):
        empty = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertEqual(empty.cert_store_stats()['x509_ca'], 0)
        with patch.object(tls.sys, 'platform', 'linux'), \
                patch.object(tls.ssl, 'create_default_context', return_value=empty), \
                patch.object(tls, 'CA_BUNDLES', (str(self.root / 'absent-ubuntu-ca.pem'), str(self.cert))):
            context = tls.https_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.handshake(context)
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.handshake(context, 'wrong-host.example')

    def test_unknown_issuer_is_still_rejected(self):
        empty = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with patch.object(tls.ssl, 'create_default_context', return_value=empty), \
                patch.object(tls, 'CA_BUNDLES', ()):
            context = tls.https_context()
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.handshake(context)

    def test_explicit_custom_bundle_is_honoured(self):
        with patch.dict(os.environ, {'SSL_CERT_FILE': str(self.cert)}), \
                patch.object(tls, 'CA_BUNDLES', (str(self.root / 'unused.pem'),)):
            self.handshake(tls.https_context())

    def test_invalid_explicit_bundle_does_not_silently_fall_back(self):
        with patch.dict(os.environ, {'SSL_CERT_FILE': str(self.root / 'missing-custom.pem')}), \
                patch.object(tls, 'CA_BUNDLES', (str(self.cert),)):
            with self.assertRaises(FileNotFoundError):
                tls.https_context()

    def test_windows_keeps_its_native_default_trust_store(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with patch.object(tls.sys, 'platform', 'win32'), \
                patch.object(tls.ssl, 'create_default_context', return_value=context), \
                patch.object(tls, 'CA_BUNDLES', (str(self.cert),)):
            self.assertIs(tls.https_context(), context)
        self.assertEqual(context.cert_store_stats()['x509_ca'], 0)
