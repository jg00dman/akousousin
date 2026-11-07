# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Verified HTTPS using the host trust store across Linux distributions.

A frozen Ubuntu Python/OpenSSL can retain /usr/lib/ssl paths which do not
exist on SteamOS/Arch. Add the host's standard CA bundle to the default store;
never disable certificate or hostname checks, or override explicit user trust.
"""
import os
from pathlib import Path
import ssl
import sys

CA_BUNDLES = (
    '/etc/ssl/cert.pem',
    '/etc/ca-certificates/extracted/tls-ca-bundle.pem',
    '/etc/ssl/certs/ca-certificates.crt',
    '/etc/pki/tls/certs/ca-bundle.crt',
    '/etc/ssl/ca-bundle.pem',
    '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem',
)


def https_context():
    cafile, capath = os.environ.get('SSL_CERT_FILE'), os.environ.get('SSL_CERT_DIR')
    if cafile or capath:
        # A configured custom store is intentional, including failure if invalid.
        return ssl.create_default_context(cafile=cafile or None, capath=capath or None)
    context = ssl.create_default_context()
    if sys.platform.startswith('linux'):
        for name in CA_BUNDLES:
            if Path(name).is_file():
                context.load_verify_locations(cafile=name)
                break
    return context
