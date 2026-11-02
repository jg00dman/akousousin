#!/usr/bin/env python3
"""Fetch immutable voice and corresponding GPL sources; package outside Wine."""
import ast
import hashlib
import platform
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import sys
import urllib.request

ROOT = Path(__file__).resolve().parent
OUT = Path('backend-dist')
OUT.mkdir(exist_ok=True)
BUNDLE = OUT / 'opensapi-piper'
BUNDLE.mkdir(exist_ok=True)
voice = json.loads((ROOT / 'voice.json').read_text())


def fetch(url, destination, digest=None):
    with urllib.request.urlopen(url, timeout=120) as response, destination.open('wb') as out:
        shutil.copyfileobj(response, out)
    actual = hashlib.file_digest(destination.open('rb'), 'sha256').hexdigest()
    if digest and actual != digest:
        raise RuntimeError(f'Checksum mismatch: {destination}')
    return actual


modeldir = BUNDLE / 'voices'
modeldir.mkdir(exist_ok=True)
base = f"{voice['repository']}/resolve/{voice['revision']}/{voice['path']}"
model = modeldir / (voice['name'] + '.onnx')
fetch(base + '/' + model.name, model, voice['model_sha256'])
fetch(base + '/' + model.name + '.json', Path(str(model) + '.json'))
fetch(base + '/MODEL_CARD', modeldir / 'MODEL_CARD')
fetch(f"{voice['repository']}/raw/{voice['revision']}/README.md", modeldir / 'UPSTREAM-README.md')
shutil.copy(ROOT / 'voice.json', modeldir)
shutil.copy(ROOT / 'README.md', BUNDLE)
# Preserve dependency notices and licence texts shipped by wheel publishers.
notices = BUNDLE / 'licenses'
notices.mkdir(exist_ok=True)
for dist in importlib.metadata.distributions():
    for file in dist.files or []:
        if any(part.lower() in ('licenses', 'license', 'license.txt', 'copying') for part in file.parts):
            source = Path(dist.locate_file(file))
            if source.is_file():
                target = notices / dist.metadata['Name'] / str(file)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(source, target)
shutil.copy(ROOT / 'LICENSE', notices / 'OpenSAPI-backend-GPL-3.0.txt')
source = OUT / 'sources'
source.mkdir(exist_ok=True)
fetch('https://github.com/OHF-Voice/piper1-gpl/archive/refs/tags/v1.8.0.tar.gz', source / 'piper-1.8.0.tar.gz')
# Exact eSpeak revision selected by Piper 1.8.0's CMakeLists.txt.
fetch('https://github.com/espeak-ng/espeak-ng/archive/724808c.tar.gz', source / 'espeak-ng-724808c.tar.gz')
shutil.copytree(ROOT, source / 'opensapi-backend', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.egg-info', 'build'))
subprocess.run([sys.executable, '-m', 'pip', 'freeze'],
               stdout=(source / 'python-requirements.txt').open('w'), check=True)
subprocess.run(['pyinstaller', '--noconfirm', '--clean', '--onedir', '--name', 'opensapi-piper',
                '--distpath', str(OUT / 'frozen'), '--workpath', 'build/backend-freeze',
                '--specpath', 'build', '--paths', str(ROOT), '--exclude-module', 'readline',
                '--collect-all', 'piper',
                '--collect-all', 'onnxruntime', '--collect-all', 'numpy',
                str(ROOT / 'entrypoint.py')], check=True)
# Preserve PSF terms for the embedded interpreter, and Debian/Ubuntu notices
# for system libraries collected by PyInstaller (OpenSSL, libffi, liblzma, etc.).
fetch(f'https://raw.githubusercontent.com/python/cpython/v{platform.python_version()}/LICENSE',
      notices / 'Python-LICENSE.txt')
analysis = ast.literal_eval(Path('build/backend-freeze/opensapi-piper/Analysis-00.toc').read_text())
def system_notices(value):
    if isinstance(value, (tuple, list)):
        if len(value) == 3 and isinstance(value[1], str) and value[1].startswith(('/usr/lib/', '/lib/')):
            path = value[1]
            result = subprocess.run(['dpkg-query', '-S', path], capture_output=True, text=True)
            if result.returncode and path.startswith('/lib/'):
                result = subprocess.run(['dpkg-query', '-S', '/usr' + path], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                package = line.split(': ')[0]
                copyright = Path('/usr/share/doc') / package.split(':')[0] / 'copyright'
                if copyright.is_file():
                    target = notices / 'system' / package / 'copyright'
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(copyright, target)
        for item in value:
            system_notices(item)
system_notices(analysis)
for path in (OUT / 'frozen/opensapi-piper').iterdir():
    target = BUNDLE / path.name
    if path.is_dir():
        shutil.copytree(path, target, dirs_exist_ok=True)
    else:
        shutil.copy2(path, target)
with tarfile.open(OUT / 'opensapi-piper-linux-x86_64.tar.xz', 'w:xz') as archive:
    archive.add(BUNDLE, arcname=BUNDLE.name)
with tarfile.open(OUT / 'opensapi-piper-sources.tar.xz', 'w:xz') as archive:
    archive.add(source, arcname='sources')
for archive in sorted(OUT.glob('*.tar.xz')):
    with (OUT / 'SHA256SUMS').open('a') as checksums:
        checksums.write(hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest() + '  ' + archive.name + '\n')
