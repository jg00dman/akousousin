# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from akousousin_app import resources, settings


class VoiceRemovalTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        env = patch.dict(os.environ, {'XDG_DATA_HOME': str(self.root / 'data')})
        env.start(); self.addCleanup(env.stop)
        self.path = self.root / 'settings.json'
        self.key = resources.STARTER
        self.cache = settings.data_path() / 'voices' / self.key
        self.cache.mkdir(parents=True)
        self.model = self.cache / (self.key + '.onnx')
        self.model.write_bytes(b'managed voice')
        Path(str(self.model) + '.json').write_text('{"audio":{"sample_rate":22050}}')
        (self.cache / 'provenance.json').write_text(json.dumps({'model_sha256': hashlib.sha256(self.model.read_bytes()).hexdigest()}))
        self.original = self.root / 'imported.onnx'
        self.original.write_bytes(b'keep imported model')
        Path(str(self.original) + '.json').write_text('{}')
        self.config = copy.deepcopy(settings.DEFAULTS)
        self.config['voices'] = {self.key: {'path': str(self.model), 'language': 'en_US', 'name': 'Starter', 'sample_rate':22050},
                                 'local': {'path': str(self.original), 'language': 'de_DE', 'name': 'Local', 'sample_rate':22050}}
        self.config['language_voices'] = {'en_US':self.key, 'de_DE':'local'}
        settings.save(self.path, self.config)

    def test_delete_managed_download_updates_default_and_language_preferences(self):
        value = resources.remove_voice(self.path, self.key)
        self.assertFalse(self.cache.exists())
        self.assertNotIn(self.key, value['voices'])
        self.assertEqual(value['voice'], 'local')
        self.assertEqual(value['language_voices'], {'de_DE':'local'})
        self.assertEqual(self.original.read_bytes(), b'keep imported model')

    def test_import_removal_keeps_original_files(self):
        resources.remove_voice(self.path, 'local')
        self.assertEqual(self.original.read_bytes(), b'keep imported model')
        self.assertTrue(Path(str(self.original)+'.json').is_file())
        self.assertTrue(self.cache.is_dir())

    def test_failed_preferences_save_restores_download(self):
        with patch.object(settings, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                resources.remove_voice(self.path, self.key)
        self.assertEqual(self.model.read_bytes(), b'managed voice')
        self.assertIn(self.key, settings.load(self.path)['voices'])

    def test_deleting_last_voice_does_not_reinstall_bundled_starter(self):
        resources.remove_voice(self.path, 'local')
        resources.remove_voice(self.path, self.key)
        package = self.root / 'offline-package'; (package/'voices').mkdir(parents=True)
        (package/'voices'/(self.key+'.onnx')).write_bytes(b'bundled voice')
        with patch.object(resources, 'root', return_value=package):
            value = resources.bootstrap(self.path)
        self.assertFalse(value['voices'])
        self.assertFalse(self.cache.exists())

    def test_imported_symlink_is_never_followed_for_deletion(self):
        linked = self.root / 'linked.onnx'; linked.symlink_to(self.original)
        self.config['voices']['local']['path'] = str(linked)
        settings.save(self.path, self.config)
        resources.remove_voice(self.path, 'local')
        self.assertTrue(linked.is_symlink())
        self.assertEqual(self.original.read_bytes(), b'keep imported model')

    def test_explicit_reimport_clears_removed_marker(self):
        resources.remove_voice(self.path, 'local')
        resources.register_voice(self.path, 'local', self.config['voices']['local'])
        self.assertNotIn('local', settings.load(self.path)['removed_voices'])
