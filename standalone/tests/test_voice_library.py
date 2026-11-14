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


class BundledStarterTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.path = self.root / 'config/settings.json'
        self.package = self.root / 'package'
        voices = self.package / 'voices'
        voices.mkdir(parents=True)
        self.model = voices / (resources.STARTER + '.onnx')
        self.model.write_bytes(b'fixture voice weights')
        Path(str(self.model) + '.json').write_text('{"audio":{"sample_rate":22050}}')
        (voices / 'provenance.json').write_text(json.dumps({
            'model_sha256': hashlib.sha256(self.model.read_bytes()).hexdigest()}))
        (voices / 'MODEL_CARD').write_text('Fixture voice model card')
        environment = patch.dict(os.environ, {'XDG_DATA_HOME': str(self.root / 'data')})
        environment.start(); self.addCleanup(environment.stop)
        package = patch.object(resources, 'root', return_value=self.package)
        package.start(); self.addCleanup(package.stop)
        download = patch('akousousin_app.catalogue.install', side_effect=AssertionError('No startup download'))
        download.start(); self.addCleanup(download.stop)

    def test_fresh_install_has_persistent_default_voice_without_downloading(self):
        config = resources.bootstrap(self.path)
        self.assertEqual(config['voice'], resources.STARTER)
        model = Path(config['voices'][config['voice']]['path'])
        self.assertTrue(resources.voice_available(config, config['voice']))
        self.assertEqual(model.read_bytes(), self.model.read_bytes())
        self.assertTrue((model.parent / 'MODEL_CARD').is_file())
        self.assertEqual(settings.load(self.path)['voice'], resources.STARTER)
        before = model.stat().st_mtime_ns
        resources.bootstrap(self.path)
        self.assertEqual(model.stat().st_mtime_ns, before)

    def test_working_selected_voice_survives_installing_bundled_starter(self):
        config = json.loads(json.dumps(settings.DEFAULTS))
        model = self.root / 'alan.onnx'; model.write_bytes(b'existing voice')
        Path(str(model) + '.json').write_text('{}')
        config.update(voice='alan', voices={'alan': {'path': str(model), 'name': 'Alan',
            'language': 'en_GB', 'sample_rate': 22050}})
        settings.save(self.path, config)
        installed = resources.bootstrap(self.path)
        self.assertEqual(installed['voice'], 'alan')
        self.assertIn(resources.STARTER, installed['voices'])

    def test_stale_starter_path_is_recovered_from_verified_cache(self):
        config = resources.bootstrap(self.path)
        cached = config['voices'][resources.STARTER]['path']
        config['voices'][resources.STARTER]['path'] = '/missing/old-install/starter.onnx'
        settings.save(self.path, config)
        installed = resources.bootstrap(self.path)
        self.assertEqual(installed['voices'][resources.STARTER]['path'], cached)
        self.assertTrue(resources.voice_available(installed, installed['voice']))

    def test_missing_selected_voice_falls_back_to_usable_starter(self):
        config = resources.bootstrap(self.path)
        config.update(voice='old', voices={**config['voices'], 'old': {
            'path': '/missing/old-install/voice.onnx', 'name': 'Old', 'language': 'en_GB'}})
        settings.save(self.path, config)
        installed = resources.bootstrap(self.path)
        self.assertEqual(installed['voice'], resources.STARTER)
        self.assertEqual(settings.load(self.path)['voice'], resources.STARTER)

    def test_explicitly_removed_starter_is_not_reinstalled(self):
        config = json.loads(json.dumps(settings.DEFAULTS))
        config['removed_voices'] = [resources.STARTER]
        settings.save(self.path, config)
        self.assertFalse(resources.bootstrap(self.path)['voices'])
        self.assertFalse((settings.data_path() / 'voices').exists())

    def test_lean_build_does_not_download_implicitly(self):
        empty = self.root / 'lean-package'; empty.mkdir()
        with patch.object(resources, 'root', return_value=empty):
            self.assertFalse(resources.bootstrap(self.path)['voices'])


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
