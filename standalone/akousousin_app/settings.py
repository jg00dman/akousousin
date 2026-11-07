# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Persistent user preferences. Written atomically; no Wine files are touched here."""
import json
import locale
import os
from pathlib import Path

DEFAULTS = {'version': 1, 'voice': 'en_US-ljspeech-medium', 'speed': 1.0, 'volume': 0.8,
            'noise_scale': 0.667, 'noise_w_scale': 0.8, 'book_language': '',
            'language_voices': {}, 'voices': {}, 'wine_prefix': '', 'wine': '', 'port': 5000,
            'idle_timeout': 300, 'stt_model': 'small', 'stt_language': '',
            'stt_source': '', 'stt_beep': True, 'stt_mode': 'toggle',
            'stt_idle_timeout': 300, 'stt_threshold': 250, 'update_weekly': True, 'update_betas': True}


def config_path():
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) if os.name == 'nt' else Path(
        os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    return base / 'Akousousin/settings.json'


def data_path():
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) if os.name == 'nt' else Path(
        os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    return base / 'Akousousin'


def load(path):
    value = json.loads(json.dumps(DEFAULTS))
    stored = json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else {}
    value.update(stored)
    value.pop('runtime', None)
    if 'update_betas' not in stored:
        from packaging.version import Version
        from . import __version__
        value['update_betas'] = Version(__version__).is_prerelease
    validate(value)
    return value


def validate(value):
    for key in ("update_weekly", "update_betas"):
        if not isinstance(value.get(key, DEFAULTS[key]), bool):
            raise ValueError("Invalid update preference: " + key)
    if value.get('stt_mode', 'toggle') not in ('toggle', 'push-to-talk'):
        raise ValueError('Invalid dictation activation mode')
    for key, low, high in [('stt_idle_timeout', 0, 86400), ('stt_threshold', 1, 10000)]:
        number = value.get(key, DEFAULTS[key])
        if isinstance(number, bool) or not isinstance(number, int) or not low <= number <= high:
            raise ValueError('Invalid dictation preference: ' + key)
    if value.get('stt_model', 'small') not in ('small', 'turbo'):
        raise ValueError('Invalid recognition model')
    if not isinstance(value.get('stt_beep', True), bool):
        raise ValueError('Invalid ready sound preference')
    for key in ('stt_language', 'stt_source'):
        if not isinstance(value.get(key, ''), str):
            raise ValueError('Invalid voice input preference')
    for key, low, high in [('speed', .5, 2), ('volume', 0, 1), ('noise_scale', 0, 2), ('noise_w_scale', 0, 2)]:
        number = value[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not low <= number <= high:
            raise ValueError(f'Invalid {key}')
    timeout = value['idle_timeout']
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 0 <= timeout <= 86400:
        raise ValueError('Idle timeout must be 0–86400 seconds (0 disables it)')
    if not isinstance(value['port'], int) or not 1024 <= value['port'] <= 65535:
        raise ValueError('Port must be between 1024 and 65535')
    if not isinstance(value['voices'], dict) or not isinstance(value['language_voices'], dict):
        raise ValueError('Invalid voice preferences')


def save(path, value):
    validate(value)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def lcid(language):
    matches = [key for key, value in locale.windows_locale.items() if value.lower() == language.lower()]
    return min(matches) if matches else 0


def language_for_lcid(value):
    return locale.windows_locale.get(value, '')


def register(path, prefix, wine):
    value = load(path)
    entry = {'prefix': str(prefix) if prefix else '', 'wine': wine or ''}
    value['registrations'] = [r for r in value.get('registrations', []) if r['prefix'] != entry['prefix']]
    value['registrations'].append(entry)
    save(path, value)


def select_voice(path, identifier):
    value = load(path)
    voice = value['voices'][identifier]
    value['voice'] = identifier
    value['language_voices'][voice['language']] = identifier
    save(path, value)
    # Updating a default needs no DLL replacement. Applications may cache their
    # SAPI voice until restarted, just as they do with Windows voice settings.
    from .install import Installer, VOICES, FULL_TOKEN
    pending = []
    for entry in value.get('registrations', []):
        installer = Installer(Path(__file__).parent, entry['prefix'] or None, entry['wine'] or None)
        token = FULL_TOKEN + identifier
        if installer.execute('reg.exe', 'query', token, '/reg:64', check=False).returncode:
            pending.append(entry['prefix'] or 'Windows')
            continue
        for key, item in ((VOICES, 'DefaultDefaultTokenId'),
                          (r'HKCU\SOFTWARE\Microsoft\Speech\Voices', 'DefaultTokenId')):
            installer.execute('reg.exe', 'add', key, '/v', item, '/t', 'REG_SZ', '/d', token, '/f', '/reg:64')
    return pending
