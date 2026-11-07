# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import json
from pathlib import Path
import tempfile
import unittest
import hashlib
import io
import os
from types import SimpleNamespace
from unittest.mock import patch

from akousousin_backend.models import install, installed


class ModelsTests(unittest.TestCase):
    def setUp(self):
        state = tempfile.TemporaryDirectory()
        self.addCleanup(state.cleanup)
        env = patch.dict(os.environ, {'XDG_STATE_HOME': state.name, 'LOCALAPPDATA': state.name})
        env.start(); self.addCleanup(env.stop)

    def test_import_persistent_no_overwrite_and_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'shared'
            source = Path(folder) / 'source'; source.mkdir()
            for name, data in [('model.bin', b'test'), ('config.json', b'{}'),
                               ('tokenizer.json', b'{}'), ('vocabulary.txt', b'hello')]:
                (source / name).write_bytes(data)
            target = install(root=root, source=source)
            self.assertTrue(installed(root=root))
            receipt = json.loads((target / 'installation.json').read_text())
            self.assertEqual(len(receipt['sha256']), 4)
            (source / 'model.bin').write_bytes(b'replacement')
            install(root=root, source=source)
            self.assertEqual((target / 'model.bin').read_bytes(), b'test')

    def test_new_tiers_import_and_retain_upstream_model_notice(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'shared'
            source = Path(folder) / 'source'; source.mkdir()
            for name, data in [('model.bin', b'model'), ('config.json', b'{}'),
                               ('tokenizer.json', b'{}'), ('vocabulary.json', b'[]'),
                               ('README.md', b'Upstream model notice')]:
                (source / name).write_bytes(data)
            for tier in ('base', 'base.en', 'small.en'):
                target = install(tier, root=root, source=source)
                self.assertTrue(installed(tier, root))
                self.assertEqual((target / 'README.md').read_bytes(), b'Upstream model notice')
                receipt = json.loads((target / 'installation.json').read_text())
                self.assertEqual(receipt['sha256']['vocabulary.json'], hashlib.sha256(b'[]').hexdigest())

    def test_incomplete_import_preserves_existing_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'shared'; (root / 'small').mkdir(parents=True)
            (root / 'small/model.bin').write_bytes(b'original')
            source = Path(folder) / 'source'; source.mkdir()
            with self.assertRaisesRegex(ValueError, 'Incomplete model'):
                install(root=root, source=source)
            self.assertEqual((root / 'small/model.bin').read_bytes(), b'original')
            self.assertFalse(installed(root=root))
            self.assertFalse(list(root.glob('.install-*')))

    def test_turbo_cannot_download_unpinned_revision(self):
        with self.assertRaises(ValueError):
            install('turbo')

    def test_first_download_is_pinned_and_not_repeated(self):
        from akousousin_backend.model_pins import REVISIONS
        self.assertEqual(set(REVISIONS), {'base', 'base.en', 'small', 'small.en'})
        for tier, revision in REVISIONS.items():
            self.assertRegex(revision, r'^[a-f0-9]{40}$')
            with self.subTest(tier=tier), tempfile.TemporaryDirectory() as folder:
                names = ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt', 'README.md')
                payload = {name: b'{}' for name in names}
                entries = [SimpleNamespace(rfilename=name, size=2, lfs=SimpleNamespace(sha256=hashlib.sha256(b'{}').hexdigest())
                           if name == 'model.bin' else None, blob_id=hashlib.sha1(b'blob 2\0{}').hexdigest()) for name in names]
                with patch('huggingface_hub.HfApi') as api, \
                        patch('huggingface_hub.hf_hub_url', side_effect=lambda repo, name, revision: name), \
                        patch('urllib.request.urlopen', side_effect=lambda name, **kwargs: io.BytesIO(payload[name])):
                    api.return_value.model_info.return_value.siblings = entries
                    install(tier, root=folder)
                    self.assertIn('Copyright (c) 2022 OpenAI', (Path(folder) / tier / 'LICENSE.txt').read_text())
                    install(tier, root=folder)
                    api.return_value.model_info.assert_called_once_with('Systran/faster-whisper-' + tier,
                        revision=revision, files_metadata=True)


    def test_abandoned_download_stage_is_removed_without_deleting_cached_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage = root / '.install-cancelled'; stage.mkdir()
            (stage / 'partial.bin').write_bytes(b'incomplete download')
            target = root / 'small'; target.mkdir()
            from akousousin_backend.models import FILES
            for name in FILES:
                (target / name).write_bytes(b'cached asset')
            install(root=root)
            self.assertFalse(stage.exists())
            self.assertEqual((target / 'model.bin').read_bytes(), b'cached asset')
