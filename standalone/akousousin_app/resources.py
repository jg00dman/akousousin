# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Locate read-only package data and copy runtime/model data needed after AppImage exit."""
import os
import json
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile

from . import settings

STARTER = 'en_US-ljspeech-medium'


def register_voice(path, key, voice):
    """Merge a completed download into current preferences, preserving user choices."""
    config = settings.load(path)
    first = not config['voices']
    config['voices'][key] = voice
    config['removed_voices'] = [item for item in config.get('removed_voices', []) if item != key]
    config['language_voices'].setdefault(voice['language'], key)
    if first:
        config['voice'] = key
    settings.save(path, config)
    return config


def download_starter(path):
    """Explicit first-use download; ordinary startup and updates never use the network."""
    config = bootstrap(path)
    if STARTER not in config['voices']:
        from . import catalogue
        entry = catalogue.catalogue(root())[STARTER]
        voice = catalogue.install(entry, settings.data_path() / 'voices')
        config = register_voice(path, STARTER, voice)
    if os.name != 'nt' and config.get('speechd_setup_pending'):
        from .speech_dispatcher import complete_pending_setup
        complete_pending_setup(path)
        config = settings.load(path)
    return config


def root():
    if os.environ.get('AKOUSOUSIN_RESOURCES'):
        return Path(os.environ['AKOUSOUSIN_RESOURCES'])
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / 'resources'
    return Path(__file__).resolve().parents[1] / 'resources'


def bootstrap(path):
    config = settings.load(path)
    package = root()
    voice = STARTER
    bundled = package / 'voices' / (voice + '.onnx')
    if voice not in config['voices'] and voice not in config.get('removed_voices', []) and bundled.is_file():
        target = settings.data_path() / 'voices' / voice
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
                shutil.copytree(package / 'voices', Path(temporary) / voice)
                (Path(temporary) / voice).rename(target)
    target = settings.data_path() / 'voices' / voice
    if voice not in config['voices'] and voice not in config.get('removed_voices', []) and (target / (voice + '.onnx')).is_file():
        # Reuse an existing verified download even if preferences were recreated.
        try:
            receipt = json.loads((target / 'provenance.json').read_text(encoding='utf-8'))
            with (target / (voice + '.onnx')).open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != receipt['model_sha256']:
                raise ValueError('Cached starter voice checksum differs')
            cfg = json.loads((target / (voice + '.onnx.json')).read_text(encoding='utf-8'))
            config = register_voice(path, voice, {'path': str(target / (voice + '.onnx')),
                'sample_rate': cfg['audio']['sample_rate'], 'language': 'en_US',
                'name': 'LJSpeech', 'quality': 'medium'})
        except (OSError, KeyError, ValueError):
            pass
    stored = json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else {}
    if not Path(path).exists() or any(key not in stored for key in ('update_weekly', 'update_betas')):
        settings.save(path, config)
    return config


def remove_voice(path, key):
    """Remove a library entry; delete only its managed download, never imports."""
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]+', key):
        raise ValueError('Invalid voice identifier')
    config = settings.load(path)
    voice = config['voices'].get(key)
    if voice is None:
        raise ValueError('Select an installed voice')
    cached = settings.data_path() / 'voices' / key
    managed = (not cached.is_symlink() and cached.is_dir()
               and cached.resolve().is_relative_to(settings.data_path().resolve())
               and Path(voice['path']).parent.resolve() == cached.resolve()
               and (cached / 'provenance.json').is_file())
    # Stage deletion so a failed settings save leaves the original usable.
    with tempfile.TemporaryDirectory(prefix='.remove-', dir=cached.parent if managed else None) as folder:
        staged = Path(folder) / 'voice'
        if managed:
            cached.rename(staged)
        try:
            del config['voices'][key]
            config['language_voices'] = {language: selected for language, selected in config['language_voices'].items()
                                         if selected != key}
            if config['voice'] == key:
                config['voice'] = next(iter(sorted(config['voices'])), settings.DEFAULTS['voice'])
            config['removed_voices'] = sorted(set(config.get('removed_voices', [])) | {key})
            settings.save(path, config)
        except BaseException:
            if managed:
                staged.rename(cached)
            raise
    return config
