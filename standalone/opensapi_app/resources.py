"""Locate read-only package data and copy runtime/model data needed after AppImage exit."""
import os
from pathlib import Path
import shutil
import sys
import tempfile

from . import settings


def root():
    if os.environ.get('OPENSAPI_RESOURCES'):
        return Path(os.environ['OPENSAPI_RESOURCES'])
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / 'resources'
    return Path(__file__).resolve().parents[1] / 'resources'


def bootstrap(path):
    config = settings.load(path)
    package = root()
    voice = 'en_US-ljspeech-medium'
    bundled = package / 'voices' / (voice + '.onnx')
    if voice not in config['voices'] and bundled.is_file():
        target = settings.data_path() / 'voices' / voice
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
                shutil.copytree(package / 'voices', Path(temporary) / voice)
                (Path(temporary) / voice).rename(target)
        config['voices'][voice] = {'path': str(target / (voice + '.onnx')), 'sample_rate': 22050,
                                   'language': 'en_US', 'name': 'LJSpeech', 'quality': 'medium'}
        config['language_voices'].setdefault('en_US', voice)
        settings.save(path, config)
    return config
