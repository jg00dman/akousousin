"""Persistent user preferences. Written atomically; no Wine files are touched here."""
import json
import locale
import os
from pathlib import Path

DEFAULTS = {'version': 1, 'voice': 'en_US-ljspeech-medium', 'speed': 1.0, 'volume': 0.8,
            'noise_scale': 0.667, 'noise_w_scale': 0.8, 'book_language': '',
            'language_voices': {}, 'voices': {}, 'wine_prefix': '', 'wine': '', 'port': 5000}


def config_path():
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) if os.name == 'nt' else Path(
        os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    return base / 'OpenSAPI/settings.json'


def data_path():
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) if os.name == 'nt' else Path(
        os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    return base / 'OpenSAPI'


def load(path):
    value = json.loads(json.dumps(DEFAULTS))
    if Path(path).exists():
        value.update(json.loads(Path(path).read_text(encoding='utf-8')))
    validate(value)
    return value


def validate(value):
    for key, low, high in [('speed', .5, 2), ('volume', 0, 1), ('noise_scale', 0, 2), ('noise_w_scale', 0, 2)]:
        number = value[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not low <= number <= high:
            raise ValueError(f'Invalid {key}')
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
