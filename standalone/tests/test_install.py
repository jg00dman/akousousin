import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from opensapi_app.install import CLASS, FULL_TOKEN, Installer, VOICES
from opensapi_app.settings import DEFAULTS


class FakeInstaller(Installer):
    def execute(self, *args, check=True, timeout=45):
        if args[0] == '--version':
            return subprocess.CompletedProcess(args, 0, 'wine-11.21\n', '')
        if str(args[0]).endswith('compat-probe.exe'):
            return subprocess.CompletedProcess(args, 0, '', '')
        result, output = 0, ''
        if args[0] == 'regedit.exe':
            self.reg.update(json.loads(Path(str(args[2]).removeprefix('Z:')).read_text()))
        else:
            action, key = args[1:3]
            if action == 'query':
                if '/v' in args:
                    name = args[args.index('/v') + 1]
                    value = self.reg.get(key, {}).get(name)
                    if value:
                        output = f'    {name}    {value[0]}    {value[1]}\n'
                    else:
                        result = 1
                elif not any(k == key or k.startswith(key + '\\') for k in self.reg):
                    result = 1
            elif action == 'export':
                value = {k: v for k, v in self.reg.items() if k == key or k.startswith(key + '\\')}
                Path(str(args[3]).removeprefix('Z:')).write_text(json.dumps(value))
            elif action == 'delete':
                if '/v' in args:
                    self.reg.get(key, {}).pop(args[args.index('/v') + 1], None)
                else:
                    self.reg = {k: v for k, v in self.reg.items() if k != key and not k.startswith(key + '\\')}
            elif action == 'add':
                name = args[args.index('/v') + 1]
                self.reg.setdefault(key, {})[name] = [args[args.index('/t') + 1], args[args.index('/d') + 1]]
        return subprocess.CompletedProcess(args, result, output, '')

    def registry(self, text):
        key = None
        for line in text.splitlines():
            if line.startswith('['):
                key = line[1:-1].replace('HKEY_CURRENT_USER', 'HKCU').replace('HKEY_LOCAL_MACHINE', 'HKLM')
                self.reg[key] = {}
            elif '=' in line:
                name, value = line.split('=', 1)
                self.reg[key][name.strip('"')] = ['REG_SZ', value]
        if getattr(self, 'fail', False):
            raise RuntimeError('Injected registration failure')


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.prefix = root / 'prefix with spaces'
        (self.prefix / 'drive_c/windows/system32').mkdir(parents=True)
        (self.prefix / 'system.reg').write_text('WINE REGISTRY Version 2\n#arch=win64\n')
        self.resource = root / 'resource'
        (self.resource / 'compat').mkdir(parents=True)
        (self.resource / 'opensapi-piper.dll').write_bytes(b'engine')
        (self.resource / 'compat/sapi.dll').write_bytes(b'compat')
        self.app = FakeInstaller(self.resource, self.prefix, '/custom/Wine.AppImage')
        self.app.reg = {CLASS + r'\InprocServer32': {'@': ['REG_SZ', 'original-engine']},
                        VOICES: {'DefaultDefaultTokenId': ['REG_SZ', 'original-default']},
                        r'HKCU\Software\Unrelated': {'Unrelated': ['REG_SZ', 'keep']}}
        self.original = copy.deepcopy(self.app.reg)
        self.config = copy.deepcopy(DEFAULTS)
        self.config['voices'] = {'en_US-ljspeech-medium': {'path': '/model.onnx', 'name': 'LJSpeech',
                                        'sample_rate': 22050, 'language': 'en_US'}}

    def test_install_and_uninstall_preserve_original_registration(self):
        self.app.install(self.config)
        self.assertTrue(self.app.manifest.exists())
        self.assertEqual(self.app.reg[VOICES]['DefaultDefaultTokenId'][1], FULL_TOKEN + self.config['voice'])
        self.app.uninstall()
        # Empty keys created by setting a default are harmless; original values and all unrelated keys survive.
        for key, value in self.original.items():
            self.assertEqual(self.app.reg[key], value)
        self.assertFalse(self.app.manifest.exists())
        self.assertFalse((self.app.directory / 'opensapi-piper.dll').exists())

    def test_failed_update_rolls_back_to_installed_version(self):
        self.app.install(self.config)
        before = copy.deepcopy(self.app.reg)
        state = self.app.manifest.read_bytes()
        (self.resource / 'opensapi-piper.dll').write_bytes(b'new-engine')
        self.app.fail = True
        with self.assertRaisesRegex(RuntimeError, 'Injected'):
            self.app.install(self.config)
        self.assertEqual(self.app.reg, before)
        self.assertEqual((self.app.directory / 'opensapi-piper.dll').read_bytes(), b'engine')
        self.assertEqual(self.app.manifest.read_bytes(), state)

    def test_manual_dll_change_is_not_overwritten_by_uninstall(self):
        self.app.install(self.config)
        path = self.app.directory / 'opensapi-piper.dll'
        path.write_bytes(b'user-change')
        before = copy.deepcopy(self.app.reg)
        with self.assertRaisesRegex(RuntimeError, 'modified'):
            self.app.uninstall()
        self.assertEqual(path.read_bytes(), b'user-change')
        self.assertEqual(self.app.reg, before)

    def test_compatibility_dlls_are_backed_up_and_restored(self):
        path = self.prefix / 'drive_c/windows/system32/sapi.dll'
        path.write_bytes(b'original-sapi')
        self.app.force_compat = True
        self.app.install(self.config)
        self.assertEqual(path.read_bytes(), b'compat')
        self.app.uninstall()
        self.assertEqual(path.read_bytes(), b'original-sapi')

    def test_32_bit_prefix_is_rejected(self):
        (self.prefix / 'system.reg').write_text('#arch=win32')
        with self.assertRaisesRegex(ValueError, '64-bit'):
            Installer(self.resource, self.prefix, '/wine')

    def test_commands_preserve_prefix_and_never_use_shell(self):
        with patch('subprocess.run') as run:
            Installer.execute(self.app, 'reg.exe', 'query', VOICES)
        self.assertEqual(run.call_args.args[0][0], '/custom/Wine.AppImage')
        self.assertEqual(run.call_args.kwargs['env']['WINEPREFIX'], str(self.prefix))
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_engine_only_install_does_not_change_existing_voice_defaults(self):
        self.config['voices'] = {}
        self.app.install(self.config)
        self.assertEqual(self.app.reg[VOICES], self.original[VOICES])
        self.assertFalse(any(key.startswith(VOICES + r'\Tokens\OpenSAPI-Piper-') for key in self.app.reg))
        self.app.uninstall()
        self.assertEqual(self.app.reg[CLASS + r'\InprocServer32'], self.original[CLASS + r'\InprocServer32'])

    def test_builtin_symlink_is_replaced_atomically_and_restored(self):
        original = Path(self.temp.name) / 'wine-builtin.dll'
        original.write_bytes(b'original-runtime')
        path = self.prefix / 'drive_c/windows/system32/sapi.dll'
        path.symlink_to(original)
        self.app.force_compat = True
        self.app.install(self.config)
        self.assertFalse(path.is_symlink())
        self.assertEqual(original.read_bytes(), b'original-runtime')
        self.app.uninstall()
        self.assertTrue(path.is_symlink())
        self.assertEqual(path.resolve(), original)
