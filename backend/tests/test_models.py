import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from akousousin_backend.models import install, installed


class ModelsTests(unittest.TestCase):
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
        with tempfile.TemporaryDirectory() as folder:
            def download(repository, revision, local_dir, allow_patterns):
                self.assertEqual(repository, 'Systran/faster-whisper-small')
                self.assertEqual(revision, '536b0662742c02347bc0e980a01041f333bce120')
                for name in ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt'):
                    (local_dir / name).write_bytes(b'{}')
            with patch('huggingface_hub.snapshot_download', side_effect=download) as call:
                install(root=folder)
                install(root=folder)
                call.assert_called_once()


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
