#!/usr/bin/env python3
"""Build the current command-line recognition snapshot for Linux testing."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--small-model', type=Path, required=True)
    args = parser.parse_args()
    for name in ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt'):
        if not (args.small_model / name).is_file():
            parser.error('Small model directory is incomplete: ' + name)
    out = ROOT / 'recognition-dist'
    build = ROOT / 'build/recognition'
    out.mkdir(exist_ok=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    name = 'Akousousin-Whisper-' + commit[:8] + '-Linux-x86_64'
    package = build / name
    if package.exists():
        shutil.rmtree(package)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', '--onedir',
                    '--name', 'whisper-engine', '--distpath', str(build / 'frozen'),
                    '--workpath', str(build / 'freeze'), '--specpath', str(build),
                    '--paths', str(ROOT / 'backend'), '--exclude-module', 'piper',
                    '--exclude-module', 'tkinter', '--exclude-module', 'readline',
                    '--collect-all', 'faster_whisper', '--collect-all', 'ctranslate2',
                    '--collect-all', 'onnxruntime', '--collect-all', 'numpy',
                    '--collect-all', 'tokenizers', '--collect-all', 'av',
                    str(ROOT / 'recognition/entrypoint.py')], check=True)
    shutil.copytree(build / 'frozen/whisper-engine', package / 'engine')
    models = package / 'models/small'
    models.mkdir(parents=True)
    for file in args.small_model.iterdir():
        if file.is_file():
            shutil.copy2(file, models / file.name)
    launcher = package / 'akousousin-whisper'
    launcher.write_text('#!/bin/sh\nset -eu\n'
                        'base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
                        'exec "$base/engine/whisper-engine" --models "$base/models" "$@"\n')
    launcher.chmod(0o755)
    shutil.copy2(ROOT / 'recognition/TESTING.md', package / 'TESTING.md')
    shutil.copy2(ROOT / 'backend/WHISPER-VALIDATION.md', package / 'VALIDATION.md')
    licenses = package / 'licenses'
    licenses.mkdir()
    shutil.copy2(ROOT / 'backend/LICENSE', licenses / 'Akousousin-GPL-3.0.txt')
    shutil.copy2(ROOT / 'recognition/Whisper-LICENSE', licenses / 'Whisper-MIT.txt')
    shutil.copy2(ROOT / 'recognition/Python-LICENSE.txt', licenses / 'Python-LICENSE.txt')
    for dist in importlib.metadata.distributions():
        for file in dist.files or []:
            if any(word in str(file).lower() for word in ('license', 'licence', 'copying', 'notice')):
                source = Path(dist.locate_file(file))
                if source.is_file() and source.suffix not in ('.py', '.pyc'):
                    target = licenses / dist.metadata['Name'] / str(file)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    versions = {d.metadata['Name']: d.version for d in importlib.metadata.distributions()}
    (package / 'build.json').write_text(json.dumps({'commit': commit, 'platform': platform.platform(),
                                                   'python': platform.python_version(), 'packages': versions}, indent=2))
    with (package / 'SHA256SUMS').open('w') as sums:
        for file in sorted(package.rglob('*')):
            if file.is_file() and file.name != 'SHA256SUMS':
                sums.write(hashlib.file_digest(file.open('rb'), 'sha256').hexdigest() + '  ' + file.relative_to(package).as_posix() + '\n')
    archive = out / (name + '.tar.gz')
    with tarfile.open(archive, 'w:gz', compresslevel=3) as tar:
        tar.add(package, arcname=name)
    subprocess.run(['git', 'archive', '--format=tar.gz', '--output', str(out / (name + '-source.tar.gz')), commit], cwd=ROOT, check=True)
    with (out / 'SHA256SUMS').open('w') as sums:
        for file in sorted(out.glob('*.tar.gz')):
            sums.write(hashlib.file_digest(file.open('rb'), 'sha256').hexdigest() + '  ' + file.name + '\n')
    print(archive)


if __name__ == '__main__':
    main()
