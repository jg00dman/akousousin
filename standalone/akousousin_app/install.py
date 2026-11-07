# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Transactional private-DLL installation. Wine/Windows system DLLs stay untouched."""
import copy
import hashlib
import ntpath
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .settings import lcid
from . import runtime, settings

CLSID = '{EA7A00AB-0FB7-4DEB-81C5-550D854F390F}'
CLASS = 'HKCU\\Software\\Classes\\CLSID\\' + CLSID
VOICES = r'HKLM\SOFTWARE\Microsoft\Speech\Voices'
TOKEN_BASE = VOICES + r'\Tokens\Akousousin-Piper-'
FULL_TOKEN = r'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\Tokens\Akousousin-Piper-'
SAPI_CLASSES = r'HKLM\Software\Classes\CLSID'
PRIVATE_SAPI = r'C:\Program Files\Akousousin\compat\x64\sapi.dll'
SAPI_REQUIRED = {'{D9F6EE60-58C9-458B-88E1-2F908FD7F87C}',
                 '{96749377-3391-11D2-9EE3-00C04F797396}'}


def value_selector(name):
    return ['/ve'] if name is None else ['/v', name]



def digest(path):
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_copy(source, target):
    source, target = Path(source), Path(target)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
        stage = Path(temporary.name)
    try:
        if source.is_symlink():
            stage.unlink()
            stage.symlink_to(os.readlink(source))
        else:
            shutil.copy2(source, stage)
        stage.replace(target)
    finally:
        stage.unlink(missing_ok=True)


def quote(text):
    if any(c in str(text) for c in '\r\n\x00'):
        raise ValueError('Invalid registry string')
    return str(text).replace('\\', '\\\\').replace('"', '\\"')


class Installer:
    def __init__(self, resource, prefix=None, wine=None, force_compat=False):
        self.resource = Path(resource)
        self.prefix = Path(prefix).expanduser().resolve() if prefix else None
        self.wine = wine
        self.force_compat = force_compat
        if os.name != 'nt':
            if self.prefix is None or not (self.prefix / 'drive_c').is_dir() or not (self.prefix / 'system.reg').is_file():
                raise ValueError('Choose an existing initialized 64-bit Wine prefix')
            if '#arch=win32' in (self.prefix / 'system.reg').read_text(errors='replace')[:4096]:
                raise ValueError('This beta supports 64-bit prefixes only')
            self.wine = wine or shutil.which('wine')
            if not self.wine:
                raise ValueError('Select the Wine executable or AppImage used by this prefix')
            self.directory = self.prefix / 'drive_c/Program Files/Akousousin'
        else:
            if prefix:
                raise ValueError('--wine-prefix is for Linux; use --install on Windows')
            self.directory = Path(os.environ['PROGRAMFILES']) / 'Akousousin'
        # Wine commonly runs with an administrative token and ignores per-user COM classes.
        # HKLM here belongs exclusively to the selected prefix; Windows keeps per-user registration.
        self.class_key = CLASS.replace('HKCU', 'HKLM', 1) if self.prefix else CLASS
        self.manifest = self.directory / 'install-state.json'
        self.backups = self.directory / 'backups'
        self.state = json.loads(self.manifest.read_text()) if self.manifest.exists() else {
            'product': 'Akousousin', 'version': 1, 'files': {}, 'keys': {}, 'values': [], 'compatibility': False}
        if self.state.get('product') != 'Akousousin':
            raise ValueError('Installation record does not belong to Akousousin')

    def environment(self):
        env = os.environ.copy()
        if self.prefix:
            env.update(WINEPREFIX=str(self.prefix), APPIMAGE_EXTRACT_AND_RUN='1')
            if self.state['compatibility']:
                env['WINEDLLOVERRIDES'] = env.get('WINEDLLOVERRIDES', '') + ';sapi=n,b'
        return env

    def execute(self, *args, check=True, timeout=45):
        command = [self.wine, *map(str, args)] if self.prefix else list(map(str, args))
        # Wine services can inherit stdout beyond the command's lifetime. Capture to
        # files so command completion does not wait for an unrelated service's EOF.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            try:
                result = subprocess.run(command, env=self.environment(), stdout=output, stderr=errors,
                                        timeout=timeout, check=False)
            except subprocess.TimeoutExpired as error:
                output.seek(0)
                errors.seek(0)
                raise RuntimeError(f'Wine/Windows command timed out after {timeout}s: '
                                   f'{output.read().decode(errors="replace")} '
                                   f'{errors.read().decode(errors="replace")}') from error
            output.seek(0)
            errors.seek(0)
            completed = subprocess.CompletedProcess(command, result.returncode,
                output.read().decode('utf-8', errors='replace'), errors.read().decode('utf-8', errors='replace'))
        if check and completed.returncode:
            raise RuntimeError(f'Wine/Windows command failed ({completed.returncode}): '
                               f'{completed.stdout} {completed.stderr}')
        return completed

    def windows(self, path):
        return 'Z:' + str(Path(path).resolve()) if self.prefix else str(Path(path).resolve())

    def capture_key(self, key):
        if key in self.current_keys:
            return
        destination = Path(self.transaction.name) / f'key-{len(self.current_keys)}.reg'
        query = self.execute('reg.exe', 'query', key, '/reg:64', check=False)
        if query.returncode:
            self.current_keys[key] = None
        else:
            self.execute('reg.exe', 'export', key, self.windows(destination), '/y')
            self.current_keys[key] = destination

    def read_value(self, key, name):
        result = self.execute('reg.exe', 'query', key, *value_selector(name), '/reg:64', check=False)
        if result.returncode:
            return None
        # /ve returns exactly one value. Its display label can be localized.
        match = re.search(r'^[ \t]+[^\r\n]*?[ \t]+(REG_SZ|REG_EXPAND_SZ)[ \t]+([^\r\n]*)\r?$',
                          result.stdout, re.M)
        if not match:
            raise RuntimeError(f'Cannot safely preserve registry value {name or "(Default)"}')
        return {'type': match[1], 'data': match[2]}

    def write_value(self, key, name, value):
        if value is None:
            self.execute('reg.exe', 'delete', key, *value_selector(name), '/f', '/reg:64', check=False)
        else:
            self.execute('reg.exe', 'add', key, *value_selector(name), '/t', value['type'],
                         '/d', value['data'], '/f', '/reg:64')

    def sapi_registrations(self):
        result = self.execute('reg.exe', 'query', SAPI_CLASSES, '/s', '/reg:64')
        candidates, key = set(), None
        for line in result.stdout.splitlines():
            if line.upper().startswith('HKEY_LOCAL_MACHINE'):
                key = line.strip()
            if not key or not re.fullmatch(r'HKEY_LOCAL_MACHINE\\Software\\Classes\\CLSID\\\{[0-9a-f-]{36}\}\\InprocServer32', key, re.I):
                continue
            match = re.search(r'[ \t]+REG_(?:EXPAND_)?SZ[ \t]+(.+)$', line)
            if match and ntpath.basename(match[1].strip().strip('"')).casefold() == 'sapi.dll':
                candidates.add('HKLM' + key[len('HKEY_LOCAL_MACHINE'):])
        allowed = {r'c:\windows\system32\sapi.dll',
                   r'c:\windows\system32\speech\common\sapi.dll', PRIVATE_SAPI.casefold(), 'sapi.dll'}
        registrations = []
        for candidate in sorted(candidates):
            original = self.read_value(candidate, None)
            if original is None:
                continue
            path = ntpath.normpath(original['data'].strip().strip('"')).casefold()
            path = path.replace('%systemroot%', r'c:\windows').replace('%windir%', r'c:\windows')
            if path in allowed:
                registrations.append(candidate)
        if not all(any(identifier in key.upper() for key in registrations) for identifier in SAPI_REQUIRED):
            raise RuntimeError('Could not identify the Wine SAPI COM registrations safely')
        return registrations

    def remember_key(self, key):
        self.capture_key(key)
        if key in self.state['keys']:
            return
        destination = self.backups / f'key-{len(self.state["keys"])}.reg'
        query = self.execute('reg.exe', 'query', key, '/reg:64', check=False)
        if query.returncode:
            self.state['keys'][key] = None
        else:
            self.execute('reg.exe', 'export', key, self.windows(destination), '/y')
            self.state['keys'][key] = str(destination.relative_to(self.directory))

    def remember_value(self, key, name):
        current = self.read_value(key, name)
        self.current_values.setdefault((key, name), current)
        if any(item['key'] == key and item['name'] == name for item in self.state['values']):
            return
        self.state['values'].append({'key': key, 'name': name, 'value': current})

    def put(self, source, target):
        target = Path(target)
        # Every file path in the manifest must remain within this prefix (or our Windows directory).
        allowed = self.prefix if self.prefix else self.directory
        if (not target.parent.resolve().is_relative_to(allowed.resolve())
                or not target.parent.resolve().is_relative_to(self.directory.resolve())):
            raise ValueError('Destination is outside the Akousousin directory')
        if str(target) not in self.current_files:
            current = None
            if target.exists():
                current = Path(self.transaction.name) / f'file-{len(self.current_files)}'
                shutil.copy2(target, current, follow_symlinks=False)
            self.current_files[str(target)] = current
        key = str(target.relative_to(allowed))
        if key not in self.state['files']:
            backup = None
            if target.exists():
                backup = 'file-' + str(len(self.state['files']))
                shutil.copy2(target, self.backups / backup, follow_symlinks=False)
            self.state['files'][key] = {'backup': backup, 'sha256': None}
        elif target.exists() and digest(target) != self.state['files'][key]['sha256']:
            raise RuntimeError(f'{target} was modified outside this installer; refusing to overwrite it')
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_copy(source, target)
        self.state['files'][key]['sha256'] = digest(target)

    def registry(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'install.reg'
            path.write_text('Windows Registry Editor Version 5.00\n\n' + text, encoding='utf-16')
            self.execute('regedit.exe', '/S', self.windows(path))

    def install(self, config, settings_path=None):
        if config['voices'] and config['voice'] not in config['voices']:
            raise ValueError('Select an installed voice first')
        before_state = copy.deepcopy(self.state)
        self.backups.mkdir(parents=True, exist_ok=True)
        self.transaction = tempfile.TemporaryDirectory()
        self.current_keys, self.current_values, self.current_files = {}, {}, {}
        try:
            if self.prefix:
                if self.state['compatibility']:
                    needs_compat = True
                else:
                    probe = self.execute(self.windows(self.resource / 'compat-probe.exe'), check=False)
                    if probe.returncode not in (0, 1):
                        raise RuntimeError('Could not check SAPI compatibility: ' + probe.stdout + probe.stderr)
                    needs_compat = probe.returncode == 1 or self.force_compat
                if needs_compat:
                    version = self.execute('--version').stdout
                    if not re.search(r'\b11\.21\b', version):
                        raise RuntimeError('This Wine needs the SAPI compatibility fix; this beta supplies it for 11.21 only')
                    registrations = self.sapi_registrations()
                    self.state['compatibility'] = True
                    self.state['compatibility_mode'] = 'private-com'
                    self.put(self.resource / 'compat/sapi.dll', self.directory / 'compat/x64/sapi.dll')
                    for key in registrations:
                        self.remember_value(key, None)
                        self.write_value(key, None, {'type': 'REG_SZ', 'data': PRIVATE_SAPI})
                    key = r'HKCU\Software\Wine\DllOverrides'
                    self.remember_value(key, 'sapi')
                    self.write_value(key, 'sapi', {'type': 'REG_SZ', 'data': 'native,builtin'})
            engine = self.directory / 'akousousin-piper.dll'
            self.put(self.resource / 'akousousin-piper.dll', engine)
            self.remember_key(self.class_key)
            engine_path = r'C:\Program Files\Akousousin\akousousin-piper.dll' if self.prefix else str(engine)
            text = f'[{self.class_key.replace("HKCU", "HKEY_CURRENT_USER").replace("HKLM", "HKEY_LOCAL_MACHINE")}\\InprocServer32]\n@="{quote(engine_path)}"\n"ThreadingModel"="Both"\n\n'
            # Store an explicit launcher; never resolve an executable supplied by text
            # or the HTTP caller. An AppImage must remain at this installed path.
            invocation = runtime.command('--api-start', '--settings', str(settings_path or settings.config_path()))
            if self.prefix:
                # Wine can CreateProcess a Unix executable directly (returning no
                # Win32 process handle). Avoid ShellExecute's file associations
                # and desktop dialogs. env supplies a native argv[0] for AppImage.
                invocation = [self.windows('/usr/bin/env'), 'PYINSTALLER_RESET_ENVIRONMENT=1', *invocation]
            launcher = subprocess.list2cmdline(invocation)
            if len(launcher) >= 4096:
                raise ValueError('Launcher command is too long')
            for identifier, voice in config['voices'].items():
                if not re.fullmatch('[A-Za-z0-9_-]+', identifier):
                    raise ValueError('Invalid voice identifier')
                token = TOKEN_BASE + identifier
                self.remember_key(token)
                language = lcid(voice['language'])
                text += f'''[{token.replace('HKLM', 'HKEY_LOCAL_MACHINE')}]
@="{quote(voice['name'] + ' (Akousousin)')}"
"CLSID"="{CLSID}"
"VoiceID"="{identifier}"
"SampleRate"=dword:{int(voice['sample_rate']):08x}
"Port"=dword:{config['port']:08x}
"LanguageID"=dword:{language:08x}
"RouteLanguages"=dword:00000001
"Launcher"="{quote(launcher)}"

[{token.replace('HKLM', 'HKEY_LOCAL_MACHINE')}\\Attributes]
"Name"="{quote(voice['name'] + ' (Akousousin)')}"
"Vendor"="Akousousin"
"Language"="{language:x}"

'''
            # Removed voices must disappear on the next explicit Apply. Only
            # restore/delete keys recorded as owned by this installation.
            wanted = {TOKEN_BASE + key for key in config['voices']}
            for key, backup in self.state['keys'].items():
                if key.startswith(TOKEN_BASE) and key not in wanted:
                    self.capture_key(key)
                    self.execute('reg.exe', 'delete', key, '/f', '/reg:64', check=False)
                    if backup:
                        self.execute('regedit.exe', '/S', self.windows(self.directory / backup))
            self.registry(text)
            activation = self.execute(self.windows(self.resource / 'compat-probe.exe'), '--engine', check=False)
            if activation.returncode:
                raise RuntimeError('Installed Akousousin engine could not be activated: ' + activation.stdout + activation.stderr)
            defaults = [(VOICES, 'DefaultDefaultTokenId'), (r'HKCU\SOFTWARE\Microsoft\Speech\Voices', 'DefaultTokenId')] if config['voices'] else []
            for key, name in defaults:
                self.remember_value(key, name)
                self.execute('reg.exe', 'add', key, '/v', name, '/t', 'REG_SZ', '/d',
                             FULL_TOKEN + config['voice'], '/f', '/reg:64')
            if not config['voices']:
                # Do not leave a default pointing at a removed AKS token.
                for item in self.state['values']:
                    if item['name'] not in ('DefaultDefaultTokenId', 'DefaultTokenId'):
                        continue
                    current = self.read_value(item['key'], item['name'])
                    if current and current['data'].startswith(FULL_TOKEN):
                        self.remember_value(item['key'], item['name'])
                        self.write_value(item['key'], item['name'], item['value'])
            stage = self.manifest.with_suffix('.tmp')
            stage.write_text(json.dumps(self.state, indent=2))
            stage.replace(self.manifest)
        except BaseException:
            try:
                self.rollback()
            finally:
                self.state = before_state
            raise
        finally:
            self.transaction.cleanup()
        return self.manifest

    def rollback(self):
        for key, backup in self.current_keys.items():
            self.execute('reg.exe', 'delete', key, '/f', '/reg:64', check=False)
            if backup:
                self.execute('regedit.exe', '/S', self.windows(backup))
        for (key, name), value in self.current_values.items():
            self.write_value(key, name, value)
        for target, backup in self.current_files.items():
            if backup:
                atomic_copy(backup, target)
            else:
                Path(target).unlink(missing_ok=True)

    def restore(self):
        # Check every file first; never partially uninstall over a user's manual changes.
        base = self.prefix if self.prefix else self.directory
        for relative, record in self.state['files'].items():
            path = base / relative
            if (not path.parent.resolve().is_relative_to(base.resolve())
                    or not path.parent.resolve().is_relative_to(self.directory.resolve())):
                raise RuntimeError('Installation record contains a file outside the Akousousin directory')
            if path.exists() and record['sha256'] and digest(path) != record['sha256']:
                raise RuntimeError(f'{path} was modified after installation; manual recovery required')
        for key, backup in self.state['keys'].items():
            self.execute('reg.exe', 'delete', key, '/f', '/reg:64', check=False)
            if backup:
                self.execute('regedit.exe', '/S', self.windows(self.directory / backup))
        for item in self.state['values']:
            self.write_value(item['key'], item['name'], item['value'])
        for relative, record in self.state['files'].items():
            path = base / relative
            if record['backup']:
                atomic_copy(self.backups / record['backup'], path)
            else:
                path.unlink(missing_ok=True)
        self.manifest.unlink(missing_ok=True)

    def uninstall(self):
        if not self.manifest.exists():
            raise ValueError('No Akousousin installation record was found in this prefix')
        self.restore()
