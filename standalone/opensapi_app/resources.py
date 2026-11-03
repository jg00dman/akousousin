"""Locate read-only package data and copy runtime/model data needed after AppImage exit."""
import json
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


def persistent_runtime(path):
    if not getattr(sys, 'frozen', False):
        return None
    info = json.loads((root() / 'build.json').read_text())
    target = settings.data_path() / 'runtimes' / info['build']
    executable = target / Path(sys.executable).name
    if not executable.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
            shutil.copytree(Path(sys.executable).parent, Path(temporary) / 'runtime',
                            ignore=lambda directory, names: ['resources']
                            if Path(directory) == Path(sys.executable).parent else [])
            (Path(temporary) / 'runtime').rename(target)
    config = settings.load(path)
    config['runtime'] = str(executable)
    settings.save(path, config)
    return executable
