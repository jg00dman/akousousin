# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Real byte accounting and first-use storage, without external network access."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import psutil

from akousousin_backend.downloads import Transfer, directory
from akousousin_app import catalogue, resources, settings
from akousousin_app.download_status import current, caption


class DownloadsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        env = patch.dict(os.environ, {'XDG_STATE_HOME': str(self.root / 'state'),
            'XDG_DATA_HOME': str(self.root / 'data'), 'LOCALAPPDATA': str(self.root / 'data')})
        env.start(); self.addCleanup(env.stop)

    def test_shared_byte_progress_known_and_unknown_size(self):
        payload = b'a' * 700000
        for total in (len(payload), None):
            with self.subTest(total=total), Transfer('Test download') as transfer:
                transfer.phase('Downloading', total=total)
                observed = []
                class Response(io.BytesIO):
                    def read(response, size=-1):
                        observed.append(dict(transfer.value))
                        return super().read(size)
                with patch('urllib.request.urlopen', return_value=Response(payload)):
                    transfer.fetch('https://example.test/model', self.root / 'model', size=total,
                                   sha256=hashlib.sha256(payload).hexdigest())
                self.assertEqual([value['completed'] for value in observed], [0, 262144, 524288, 700000])
                report = next(value for value in current() if value['id'] == transfer.path.stem)
                self.assertEqual(report['completed'], len(payload))
                self.assertEqual(report['total'], total)
                self.assertEqual('%' in caption(report), total is not None)
                self.assertEqual((self.root / 'model').read_bytes(), payload)

    def test_truncation_oversize_and_corruption_report_failure(self):
        for payload in (b'x', b'xxxx', b'bad'):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError), Transfer('Bad download') as transfer:
                    transfer.phase('Downloading', total=3)
                    with patch('urllib.request.urlopen', return_value=io.BytesIO(payload)):
                        transfer.fetch('https://example.test/model', self.root / 'bad', size=3,
                                       sha256=hashlib.sha256(b'yes').hexdigest())
                self.assertEqual(json.loads(transfer.path.read_text())['status'], 'error')

    def test_dead_download_worker_does_not_leave_an_active_indicator(self):
        transfer = Transfer('Killed worker'); transfer.report(force=True)
        with patch('akousousin_app.download_status.psutil.Process', side_effect=psutil.NoSuchProcess(123)):
            self.assertEqual(current(), [])
        self.assertFalse(transfer.path.exists())

    def test_startup_has_no_network_and_download_is_reused_after_preferences_reset(self):
        path = self.root / 'settings.json'
        with patch.object(resources, 'root', return_value=self.root), patch('urllib.request.urlopen') as network:
            self.assertFalse(resources.bootstrap(path)['voices'])
            network.assert_not_called()
        key = resources.STARTER
        target = settings.data_path() / 'voices' / key
        target.mkdir(parents=True)
        model = target / (key + '.onnx'); model.write_bytes(b'verified voice')
        (target / (key + '.onnx.json')).write_text('{"audio":{"sample_rate":22050}}')
        (target / 'provenance.json').write_text(json.dumps({'model_sha256': hashlib.sha256(model.read_bytes()).hexdigest()}))
        with patch.object(resources, 'root', return_value=self.root), patch.object(catalogue, 'install') as download:
            config = resources.download_starter(path)
            path.unlink()
            restored = resources.download_starter(path)
            download.assert_not_called()
        self.assertEqual(restored['voices'], config['voices'])
        self.assertEqual(restored['voice'], key)

    def test_registering_download_preserves_existing_voice_and_current_preferences(self):
        path = self.root / 'settings.json'
        config = settings.load(path)
        config.update(voice='german', voices={'german': {'language': 'de_DE'}}, stt_language='fr')
        settings.save(path, config)
        updated = resources.register_voice(path, resources.STARTER, {'path': '/voice', 'language': 'en_US'})
        self.assertEqual(updated['voice'], 'german')
        self.assertEqual(updated['stt_language'], 'fr')

    def test_optional_bundled_voice_bootstraps_offline_and_survives_lean_upgrade(self):
        package = self.root / 'package'; voices = package / 'voices'; voices.mkdir(parents=True)
        key = resources.STARTER
        (voices / (key + '.onnx')).write_bytes(b'offline voice')
        (voices / (key + '.onnx.json')).write_text('{"audio":{"sample_rate":22050}}')
        (voices / 'provenance.json').write_text(json.dumps({'model_sha256': hashlib.sha256(b'offline voice').hexdigest()}))
        path = self.root / 'settings.json'
        with patch.object(resources, 'root', return_value=package), patch('urllib.request.urlopen') as network:
            config = resources.bootstrap(path)
            self.assertEqual(Path(config['voices'][key]['path']).read_bytes(), b'offline voice')
            network.assert_not_called()
        with patch.object(resources, 'root', return_value=self.root / 'lean-package'), patch.object(catalogue, 'install') as download:
            updated = resources.download_starter(path)
            download.assert_not_called()
        self.assertEqual(updated['voices'], config['voices'])

    def test_failed_voice_download_publishes_no_voice(self):
        entry = {'key': 'test', 'name': 'Test', 'language': {'family': 'en', 'code': 'en_US'},
                 'quality': 'medium', 'files': {'voice/test.onnx': {'size_bytes': 5},
                    'voice/test.onnx.json': {'size_bytes': 2}, 'voice/MODEL_CARD': {'size_bytes': 4}}}
        listing = [{'path': 'voice/test.onnx', 'lfs': {'oid': hashlib.sha256(b'12345').hexdigest()}}]
        def response(url, **kwargs):
            return io.BytesIO(json.dumps(listing).encode() if '/api/' in url else b'123')
        with patch('urllib.request.urlopen', side_effect=response), self.assertRaisesRegex(ValueError, 'truncated'):
            catalogue.install(entry, self.root / 'voices', reviewed=True)
        self.assertFalse((self.root / 'voices/test').exists())
        self.assertEqual(list((self.root / 'voices').iterdir()), [])
