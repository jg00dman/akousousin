"""Transactional prefix-local installation. Windows system SAPI is never replaced."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .settings import lcid

CLSID = '{EA7A00AB-0FB7-4DEB-81C5-550D854F390F}'
CLASS = 'HKCU\\Software\\Classes\\CLSID\\' + CLSID
VOICES = r'HKLM\SOFTWARE\Microsoft\Speech\Voices'
TOKEN_BASE = VOICES + r'\Tokens\OpenSAPI-Piper-'
FULL_TOKEN = r'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\Tokens\OpenSAPI-Piper-'


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
            self.directory = self.prefix / 'drive_c/Program Files/OpenSAPI'
        else:
            if prefix:
                raise ValueError('--wine-prefix is for Linux; use --install on Windows')
            self.directory = Path(os.environ['PROGRAMFILES']) / 'OpenSAPI'
        self.manifest = self.directory / 'install-state.json'
        self.backups = self.directory / 'backups'
        self.state = json.loads(self.manifest.read_text()) if self.manifest.exists() else {
            'product': 'OpenSAPI', 'version': 1, 'files': {}, 'keys': {}, 'values': [], 'compatibility': False}
        if self.state.get('product') != 'OpenSAPI':
            raise ValueError('Installation record does not belong to OpenSAPI')

    def environment(self):
        env = os.environ.copy()
        if self.prefix:
            env.update(WINEPREFIX=str(self.prefix), APPIMAGE_EXTRACT_AND_RUN='1')
            if self.state['compatibility']:
                env['WINEDLLOVERRIDES'] = env.get('WINEDLLOVERRIDES', '') + ';sapi=n,b'
        return env

    def execute(self, *args, check=True, timeout=45):
        command = [self.wine, *map(str, args)] if self.prefix else list(map(str, args))
        return subprocess.run(command, env=self.environment(), capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=timeout, check=check)

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
        result = self.execute('reg.exe', 'query', key, '/v', name, '/reg:64', check=False)
        if result.returncode:
            return None
        match = re.search(r'^\s*' + re.escape(name) + r'\s+(REG_SZ|REG_EXPAND_SZ)\s*(.*)$', result.stdout, re.M)
        if not match:
            raise RuntimeError(f'Cannot safely preserve registry value {name}')
        return {'type': match[1], 'data': match[2]}

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
        if not target.parent.resolve().is_relative_to(allowed.resolve()):
            raise ValueError('Destination is outside the selected installation')
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

    def install(self, config):
        if config['voices'] and config['voice'] not in config['voices']:
            raise ValueError('Select an installed voice first')
        self.backups.mkdir(parents=True, exist_ok=True)
        self.transaction = tempfile.TemporaryDirectory()
        self.current_keys, self.current_values, self.current_files = {}, {}, {}
        try:
            if self.prefix:
                probe = self.execute(self.windows(self.resource / 'compat-probe.exe'), check=False)
                if probe.returncode not in (0, 1):
                    raise RuntimeError('Could not check SAPI compatibility: ' + probe.stdout + probe.stderr)
                if probe.returncode == 1 or self.force_compat:
                    version = self.execute('--version').stdout
                    if not re.search(r'\b11\.21\b', version):
                        raise RuntimeError('This Wine needs the SAPI compatibility fix; this beta supplies it for 11.21 only')
                    self.state['compatibility'] = True
                    system = self.prefix / 'drive_c/windows/system32'
                    self.put(self.resource / 'compat/sapi.dll', system / 'sapi.dll')
                    # Respect existing case on the Linux filesystem.
                    speech = next((p for p in system.iterdir() if p.name.lower() == 'speech'), system / 'speech')
                    common = next((p for p in speech.iterdir() if p.name.lower() == 'common'), speech / 'common') if speech.exists() else speech / 'common'
                    self.put(self.resource / 'compat/sapi.dll', common / 'sapi.dll')
                    self.remember_value(r'HKCU\Software\Wine\DllOverrides', 'sapi')
                    self.execute('reg.exe', 'add', r'HKCU\Software\Wine\DllOverrides', '/v', 'sapi',
                                 '/t', 'REG_SZ', '/d', 'native,builtin', '/f', '/reg:64')
            engine = self.directory / 'opensapi-piper.dll'
            self.put(self.resource / 'opensapi-piper.dll', engine)
            self.remember_key(CLASS)
            engine_path = r'C:\Program Files\OpenSAPI\opensapi-piper.dll' if self.prefix else str(engine)
            text = f'[{CLASS.replace("HKCU", "HKEY_CURRENT_USER")}\\InprocServer32]\n@="{quote(engine_path)}"\n"ThreadingModel"="Both"\n\n'
            for identifier, voice in config['voices'].items():
                if not re.fullmatch('[A-Za-z0-9_-]+', identifier):
                    raise ValueError('Invalid voice identifier')
                token = TOKEN_BASE + identifier
                self.remember_key(token)
                language = lcid(voice['language'])
                text += f'''[{token.replace('HKLM', 'HKEY_LOCAL_MACHINE')}]
@="{quote(voice['name'] + ' (OpenSAPI)')}"
"CLSID"="{CLSID}"
"VoiceID"="{identifier}"
"SampleRate"=dword:{int(voice['sample_rate']):08x}
"Port"=dword:{config['port']:08x}
"LanguageID"=dword:{language:08x}
"RouteLanguages"=dword:00000001

[{token.replace('HKLM', 'HKEY_LOCAL_MACHINE')}\\Attributes]
"Name"="{quote(voice['name'] + ' (OpenSAPI)')}"
"Vendor"="OpenSAPI"
"Language"="{language:x}"

'''
            self.registry(text)
            defaults = [(VOICES, 'DefaultDefaultTokenId'), (r'HKCU\SOFTWARE\Microsoft\Speech\Voices', 'DefaultTokenId')] if config['voices'] else []
            for key, name in defaults:
                self.remember_value(key, name)
                self.execute('reg.exe', 'add', key, '/v', name, '/t', 'REG_SZ', '/d',
                             FULL_TOKEN + config['voice'], '/f', '/reg:64')
            stage = self.manifest.with_suffix('.tmp')
            stage.write_text(json.dumps(self.state, indent=2))
            stage.replace(self.manifest)
        except BaseException:
            self.rollback()
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
            if value is None:
                self.execute('reg.exe', 'delete', key, '/v', name, '/f', '/reg:64', check=False)
            else:
                self.execute('reg.exe', 'add', key, '/v', name, '/t', value['type'],
                             '/d', value['data'], '/f', '/reg:64')
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
            if not path.parent.resolve().is_relative_to(base.resolve()):
                raise RuntimeError('Installation record contains a path outside this prefix')
            if path.exists() and record['sha256'] and digest(path) != record['sha256']:
                raise RuntimeError(f'{path} was modified after installation; manual recovery required')
        for key, backup in self.state['keys'].items():
            self.execute('reg.exe', 'delete', key, '/f', '/reg:64', check=False)
            if backup:
                self.execute('regedit.exe', '/S', self.windows(self.directory / backup))
        for item in self.state['values']:
            if item['value'] is None:
                self.execute('reg.exe', 'delete', item['key'], '/v', item['name'], '/f', '/reg:64', check=False)
            else:
                self.execute('reg.exe', 'add', item['key'], '/v', item['name'], '/t', item['value']['type'],
                             '/d', item['value']['data'], '/f', '/reg:64')
        for relative, record in self.state['files'].items():
            path = base / relative
            if record['backup']:
                atomic_copy(self.backups / record['backup'], path)
            else:
                path.unlink(missing_ok=True)
        self.manifest.unlink(missing_ok=True)

    def uninstall(self):
        if not self.manifest.exists():
            raise ValueError('No OpenSAPI installation record was found in this prefix')
        self.restore()
