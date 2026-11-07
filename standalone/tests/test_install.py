# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from akousousin_app.install import CLASS, FULL_TOKEN, Installer, VOICES, SAPI_CLASSES, PRIVATE_SAPI
from akousousin_app.settings import DEFAULTS


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
                if '/v' in args or '/ve' in args:
                    name = '@' if '/ve' in args else args[args.index('/v') + 1]
                    value = self.reg.get(key, {}).get(name)
                    if value:
                        output = f'    {name}    {value[0]}    {value[1]}\n'
                    else:
                        result = 1
                elif '/s' in args:
                    for current, values in self.reg.items():
                        if current == key or current.startswith(key + '\\'):
                            output += current.replace('HKLM', 'HKEY_LOCAL_MACHINE', 1) + '\n'
                            for name, value in values.items():
                                output += f'    {name}    {value[0]}    {value[1]}\n'
                elif not any(k == key or k.startswith(key + '\\') for k in self.reg):
                    result = 1
            elif action == 'export':
                value = {k: v for k, v in self.reg.items() if k == key or k.startswith(key + '\\')}
                Path(str(args[3]).removeprefix('Z:')).write_text(json.dumps(value))
            elif action == 'delete':
                if '/v' in args or '/ve' in args:
                    name = '@' if '/ve' in args else args[args.index('/v') + 1]
                    self.reg.get(key, {}).pop(name, None)
                else:
                    self.reg = {k: v for k, v in self.reg.items() if k != key and not k.startswith(key + '\\')}
            elif action == 'add':
                name = '@' if '/ve' in args else args[args.index('/v') + 1]
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
        (self.resource / 'akousousin-piper.dll').write_bytes(b'engine')
        (self.resource / 'compat/sapi.dll').write_bytes(b'compat')
        self.app = FakeInstaller(self.resource, self.prefix, '/custom/Wine.AppImage')
        self.app.reg = {CLASS + r'\InprocServer32': {'@': ['REG_SZ', 'original-engine']},
                        VOICES: {'DefaultDefaultTokenId': ['REG_SZ', 'original-default']},
                        r'HKCU\Software\Unrelated': {'Unrelated': ['REG_SZ', 'keep']}}
        self.sapi_keys = [SAPI_CLASSES + '\\' + identifier + r'\InprocServer32'
                          for identifier in ('{D9F6EE60-58C9-458B-88E1-2F908FD7F87C}', '{96749377-3391-11D2-9EE3-00C04F797396}')]
        for key in self.sapi_keys:
            self.app.reg[key] = {'@': ['REG_EXPAND_SZ', r'%SystemRoot%\system32\Speech\Common\sapi.dll'],
                                 'ThreadingModel': ['REG_SZ', 'Both']}
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
        self.assertFalse((self.app.directory / 'akousousin-piper.dll').exists())

    def test_failed_update_rolls_back_to_installed_version(self):
        self.app.install(self.config)
        before = copy.deepcopy(self.app.reg)
        state = self.app.manifest.read_bytes()
        (self.resource / 'akousousin-piper.dll').write_bytes(b'new-engine')
        self.app.fail = True
        with self.assertRaisesRegex(RuntimeError, 'Injected'):
            self.app.install(self.config)
        self.assertEqual(self.app.reg, before)
        self.assertEqual((self.app.directory / 'akousousin-piper.dll').read_bytes(), b'engine')
        self.assertEqual(self.app.manifest.read_bytes(), state)

    def test_apply_removes_deleted_voice_token_and_restores_default_when_empty(self):
        from akousousin_app.install import TOKEN_BASE, FULL_TOKEN
        self.app.install(self.config)
        key = TOKEN_BASE + self.config['voice']
        self.assertIn(key, self.app.reg)
        self.config['voices'] = {}
        self.app.install(self.config)
        self.assertNotIn(key, self.app.reg)
        self.assertEqual(self.app.reg[VOICES]['DefaultDefaultTokenId'], self.original[VOICES]['DefaultDefaultTokenId'])
        self.assertEqual(self.app.reg[r'HKCU\Software\Unrelated'], self.original[r'HKCU\Software\Unrelated'])

    def test_manual_dll_change_is_not_overwritten_by_uninstall(self):
        self.app.install(self.config)
        path = self.app.directory / 'akousousin-piper.dll'
        path.write_bytes(b'user-change')
        before = copy.deepcopy(self.app.reg)
        with self.assertRaisesRegex(RuntimeError, 'modified'):
            self.app.uninstall()
        self.assertEqual(path.read_bytes(), b'user-change')
        self.assertEqual(self.app.reg, before)

    def test_private_compatibility_dll_preserves_system_files_and_com_defaults(self):
        system = self.prefix / 'drive_c/windows/system32/sapi.dll'
        system.write_bytes(b'original-sapi')
        common = system.parent / 'Speech/Common/sapi.dll'
        common.parent.mkdir(parents=True); common.write_bytes(b'original-common')
        self.app.force_compat = True
        self.app.install(self.config)
        private = self.app.directory / 'compat/x64/sapi.dll'
        self.assertEqual(private.read_bytes(), b'compat')
        self.assertEqual(system.read_bytes(), b'original-sapi')
        self.assertEqual(common.read_bytes(), b'original-common')
        for key in self.sapi_keys:
            self.assertEqual(self.app.reg[key]['@'], ['REG_SZ', PRIVATE_SAPI])
            self.assertEqual(self.app.reg[key]['ThreadingModel'], ['REG_SZ', 'Both'])
        self.assertTrue(all(name.startswith('drive_c/Program Files/Akousousin/') for name in self.app.state['files']))
        self.app.uninstall()
        self.assertFalse(private.exists())
        self.assertEqual(system.read_bytes(), b'original-sapi')
        self.assertEqual(common.read_bytes(), b'original-common')
        for key in self.sapi_keys:
            self.assertEqual(self.app.reg[key], self.original[key])

    def test_compatible_probe_still_updates_an_installed_private_shim(self):
        self.app.force_compat = True
        self.app.install(self.config)
        self.app.force_compat = False
        (self.resource / 'compat/sapi.dll').write_bytes(b'compat-v2')
        self.app.install(self.config)
        self.assertEqual((self.app.directory / 'compat/x64/sapi.dll').read_bytes(), b'compat-v2')
        self.app.uninstall()
        for key in self.sapi_keys:
            self.assertEqual(self.app.reg[key], self.original[key])

    def test_private_registration_failure_restores_defaults_files_and_state(self):
        self.app.force_compat = True
        before = copy.deepcopy(self.app.state)
        self.app.fail = True
        with self.assertRaisesRegex(RuntimeError, 'Injected'):
            self.app.install(self.config)
        self.assertEqual(self.app.state, before)
        self.assertFalse((self.app.directory / 'compat/x64/sapi.dll').exists())
        for key in self.sapi_keys:
            self.assertEqual(self.app.reg[key], self.original[key])

    def test_missing_sapi_class_refuses_partial_redirection(self):
        del self.app.reg[self.sapi_keys[0]]
        self.app.force_compat = True
        before = copy.deepcopy(self.app.reg)
        with self.assertRaisesRegex(RuntimeError, 'identify'):
            self.app.install(self.config)
        self.assertEqual(self.app.reg, before)
        self.assertFalse((self.app.directory / 'compat/x64/sapi.dll').exists())

    def test_32_bit_prefix_is_rejected(self):
        (self.prefix / 'system.reg').write_text('#arch=win32')
        with self.assertRaisesRegex(ValueError, '64-bit'):
            Installer(self.resource, self.prefix, '/wine')

    def test_commands_preserve_prefix_and_never_use_shell(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
            Installer.execute(self.app, 'reg.exe', 'query', VOICES)
        self.assertEqual(run.call_args.args[0][0], '/custom/Wine.AppImage')
        self.assertEqual(run.call_args.kwargs['env']['WINEPREFIX'], str(self.prefix))
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_engine_only_install_does_not_change_existing_voice_defaults(self):
        self.config['voices'] = {}
        self.app.install(self.config)
        self.assertEqual(self.app.reg[VOICES], self.original[VOICES])
        self.assertFalse(any(key.startswith(VOICES + r'\Tokens\Akousousin-Piper-') for key in self.app.reg))
        self.app.uninstall()
        self.assertEqual(self.app.reg[CLASS + r'\InprocServer32'], self.original[CLASS + r'\InprocServer32'])

    def test_builtin_symlink_is_never_replaced(self):
        original = Path(self.temp.name) / 'wine-builtin.dll'
        original.write_bytes(b'original-runtime')
        path = self.prefix / 'drive_c/windows/system32/sapi.dll'
        path.symlink_to(original)
        self.app.force_compat = True
        self.app.install(self.config)
        self.assertTrue(path.is_symlink())
        self.assertEqual(path.resolve(), original)
        self.assertEqual(original.read_bytes(), b'original-runtime')
        self.app.uninstall()
        self.assertTrue(path.is_symlink())
        self.assertEqual(path.resolve(), original)

    def test_failed_engine_activation_rolls_back_install(self):
        execute = self.app.execute
        def reject(*args, **kwargs):
            if '--engine' in args:
                return subprocess.CompletedProcess(args, 2, 'Class not registered', '')
            return execute(*args, **kwargs)
        self.app.execute = reject
        with self.assertRaisesRegex(RuntimeError, 'could not be activated'):
            self.app.install(self.config)
        self.assertFalse(self.app.manifest.exists())
        self.assertFalse((self.app.directory / 'akousousin-piper.dll').exists())
        for key, value in self.original.items():
            self.assertEqual(self.app.reg[key], value)

    def test_command_does_not_wait_for_background_service_output_eof(self):
        import sys
        import time
        self.app.wine = sys.executable
        started = time.monotonic()
        script = "import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(2)']);print('ready')"
        result = Installer.execute(self.app, '-c', script, timeout=1)
        self.assertEqual(result.stdout.strip(), 'ready')
        self.assertLess(time.monotonic() - started, 1.5)


    def test_system_directory_file_writes_are_rejected(self):
        target = self.prefix / 'drive_c/windows/system32/sapi.dll'
        with self.assertRaisesRegex(ValueError, 'Akousousin directory'):
            self.app.put(self.resource / 'compat/sapi.dll', target)
        self.assertFalse(target.exists())

    def test_unrelated_sapi_named_com_server_is_not_redirected(self):
        key = SAPI_CLASSES + r'\{11111111-1111-1111-1111-111111111111}\InprocServer32'
        original = {'@': ['REG_SZ', r'C:\OtherApp\sapi.dll']}
        self.app.reg[key] = copy.deepcopy(original)
        self.app.force_compat = True
        self.app.install(self.config)
        self.assertEqual(self.app.reg[key], original)
        self.app.uninstall()
        self.assertEqual(self.app.reg[key], original)

    def test_default_value_read_handles_localized_labels(self):
        with patch.object(self.app, 'execute', return_value=subprocess.CompletedProcess([], 0, '    (Standard)    REG_EXPAND_SZ    %SystemRoot%\\system32\\sapi.dll\n', '')):
            self.assertEqual(self.app.read_value('HKLM\\Test', None),
                             {'type': 'REG_EXPAND_SZ', 'data': r'%SystemRoot%\system32\sapi.dll'})

    def test_registry_values_preserve_data_without_windows_line_endings(self):
        for name, display in ((None, '(Default)'), ('sapi', 'sapi')):
            output = '\r\nHKEY_LOCAL_MACHINE\\Test\r\n    ' + display + '    REG_SZ    C:\\private\\sapi.dll\r\n\r\n'
            with self.subTest(name=name), patch.object(self.app, 'execute', return_value=subprocess.CompletedProcess([], 0, output, '')):
                self.assertEqual(self.app.read_value(r'HKLM\Test', name),
                                 {'type': 'REG_SZ', 'data': r'C:\private\sapi.dll'})
