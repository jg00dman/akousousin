#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Build the independent panel/service. Reuse a published Wine SAPI DLL, never compile Wine."""
import ast
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--bundle-starter-voice', action=argparse.BooleanOptionalAction, default=True,
                    help='Include the reviewed LJSpeech voice for offline first use (default: included; use --no-bundle-starter-voice for a lean build)')
options = parser.parse_args()

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'standalone-dist'
BUILD = ROOT / 'build/standalone-package'
RESOURCE = BUILD / 'resources'
CACHE = BUILD / 'downloads'
for stage in (RESOURCE, BUILD / 'Akousousin', BUILD / 'AppDir'):
    if stage.exists():
        shutil.rmtree(stage)
for directory in (OUT, RESOURCE, CACHE):
    directory.mkdir(parents=True, exist_ok=True)


def fetch(url, target, expected=None):
    target = Path(target)
    if not target.exists():
        with urllib.request.urlopen(url, timeout=120) as response, target.open('wb') as output:
            shutil.copyfileobj(response, output)
    sha = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
    if expected and sha != expected:
        raise RuntimeError(f'Checksum mismatch: {target.name}')
    return sha


for file in (ROOT / 'build/standalone-engine').glob('*'):
    shutil.copy2(file, RESOURCE)
shutil.copytree(ROOT / 'standalone/resources', RESOURCE, dirs_exist_ok=True)
for translation in (RESOURCE / 'translations').glob('*.ts'):
    subprocess.run(['pyside6-lrelease', str(translation), '-qm', str(translation.with_suffix('.qm'))], check=True)
# Include one reviewed voice by default. Additional voices remain on demand.

# The user explicitly approved this one reviewed starter voice for redistribution.
# Catalogue downloads preserve its upstream model card and MIT/public-domain provenance.
from akousousin_app import catalogue, __version__
from akousousin_app.desktop_identity import APP_ID
if options.bundle_starter_voice:
    with tempfile.TemporaryDirectory(dir=BUILD) as temporary:
        entry = catalogue.catalogue(ROOT / 'standalone/resources')['en_US-ljspeech-medium']
        voice = catalogue.install(entry, Path(temporary), reviewed=True, publish=False)
        shutil.copytree(Path(voice['path']).parent, RESOURCE / 'voices', dirs_exist_ok=True)

if sys.platform != 'win32':
    repository = os.environ.get('GITHUB_REPOSITORY', 'jg00dman/akousousin')
    published = f'https://github.com/{repository}/releases/download/wine-compat-11.21-3b19eb0e45ac/'
    runtime = CACHE / 'wine-runtime.tar.xz'
    fetch(published + 'wine-runtime-11.21-logos-x86_64.tar.xz', runtime,
          'e9e2559bbf34348d1cc9a5cf15530fd62b7075281959f3893fc8be897e783de1')
    compat = RESOURCE / 'compat'
    compat.mkdir(exist_ok=True)
    with tarfile.open(runtime) as archive:
        member = next(m for m in archive if m.name.endswith('/sapi.dll') and '/x86_64-windows/' in m.name)
        with archive.extractfile(member) as source, (compat / 'sapi.dll').open('wb') as target:
            shutil.copyfileobj(source, target)
    (compat / 'provenance.json').write_text(json.dumps({'version': '11.21', 'source_commit':
         '3b19eb0e45ac5f57301073fc9e721cac7829dc93', 'release': 'wine-compat-11.21-3b19eb0e45ac',
         'source': published + 'wine-source-11.21-logos.tar.xz'}, indent=2))

# Original Akousousin artwork, shared by the AppImage, Tk window and tray.
from PIL import Image, ImageDraw
icon = Image.new('RGBA', (128, 128))
draw = ImageDraw.Draw(icon)
draw.rounded_rectangle((0, 0, 127, 127), radius=24, fill='#087e82')
for x, low, high in ((30, 52, 76), (47, 36, 92), (64, 26, 102), (81, 40, 88), (98, 56, 72)):
    draw.line((x, low, x, high), fill='white', width=7)
icon.save(RESOURCE / 'akousousin.png')

commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
(RESOURCE / 'build.json').write_text(json.dumps({'build': commit[:12] + '-' + sys.platform,
                                               'commit': commit, 'version': __version__,
                                               'distribution': 'appimage' if sys.platform == 'linux' else 'windows-zip',
                                               'starter_voice': 'en_US-ljspeech-medium' if options.bundle_starter_voice else None}, indent=2))
recognition_options = []
if importlib.util.find_spec('faster_whisper') is not None:
    for dependency in ('faster_whisper', 'ctranslate2', 'tokenizers', 'av'):
        recognition_options += ['--collect-all', dependency]
subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', '--onedir', '--name', 'akousousin',
                '--distpath', str(BUILD / 'frozen'), '--workpath', str(BUILD / 'freeze'), '--specpath', str(BUILD),
                '--paths', str(ROOT / 'standalone'), '--paths', str(ROOT / 'backend'),
                '--exclude-module', 'readline', '--collect-all', 'piper', '--collect-all', 'numpy',
                '--collect-all', 'onnxruntime', '--collect-data', 'akousousin_backend', *recognition_options, str(ROOT / 'standalone/entrypoint.py')], check=True)

PACKAGE = BUILD / 'Akousousin'
shutil.copytree(BUILD / 'frozen/akousousin', PACKAGE, dirs_exist_ok=True)
shutil.copytree(RESOURCE, PACKAGE / 'resources', dirs_exist_ok=True)
shutil.copy(ROOT / 'standalone/SPEECH-DISPATCHER.md', PACKAGE / 'SPEECH-DISPATCHER.md')
notices = PACKAGE / 'licenses'
notices.mkdir(exist_ok=True)
shutil.copy(ROOT / 'recognition/Whisper-LICENSE', notices / 'Whisper-models-MIT.txt')
shutil.copy(ROOT / 'LICENSES/LGPL-2.1-or-later.txt', notices / 'Engine-LGPL-2.1.txt')
shutil.copy(ROOT / 'LICENSE', notices / 'Akousousin-GPL-3.0.txt')
shutil.copy(ROOT / 'LICENSING.md', notices / 'Akousousin-LICENSING.md')
fetch(f'https://raw.githubusercontent.com/python/cpython/v{platform.python_version()}/LICENSE',
      notices / 'Python-LICENSE.txt')
# Include all distribution licence/notice files; PyInstaller also collects package data notices.
for dist in importlib.metadata.distributions():
    for file in dist.files or []:
        lower = str(file).lower()
        if any(word in lower for word in ('license', 'licence', 'copying', 'notice')):
            source = Path(dist.locate_file(file))
            if source.is_file() and source.suffix not in ('.py', '.pyc'):
                target = notices / dist.metadata['Name'] / str(file)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
if sys.platform != 'win32':
    shutil.copytree('/usr/share/common-licenses', notices / 'common', dirs_exist_ok=True)
    analysis = ast.literal_eval((BUILD / 'freeze/akousousin/Analysis-00.toc').read_text())
    def system_notices(value):
        if isinstance(value, (tuple, list)):
            if len(value) == 3 and isinstance(value[1], str) and value[1].startswith(('/usr/lib/', '/lib/')):
                source = value[1]
                result = subprocess.run(['dpkg-query', '-S', source], capture_output=True, text=True)
                if result.returncode and source.startswith('/lib/'):
                    result = subprocess.run(['dpkg-query', '-S', '/usr' + source], capture_output=True, text=True)
                for line in result.stdout.splitlines():
                    package = line.split(': ')[0].split(':')[0]
                    copyright = Path('/usr/share/doc') / package / 'copyright'
                    if copyright.exists():
                        target = notices / 'system' / package / 'copyright'
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(copyright, target)
            for item in value:
                system_notices(item)
    system_notices(analysis)
    from bundle_clipboard import bundle as bundle_clipboard
    for library in bundle_clipboard(PACKAGE, CACHE, BUILD, notices, fetch):
        system_notices(('clipboard helper dependency', library, 'BINARY'))

# The tray uses PNG artwork, not Qt PDF rendering. Do not ship an unused
# PDF plugin and its large Chromium-derived renderer.
for file in PACKAGE.rglob('*'):
    if file.is_file() and (file.name in ('libqpdf.so', 'qpdf.dll') or
                           file.name.startswith(('libQt6Pdf', 'Qt6Pdf'))):
        file.unlink()

(PACKAGE / 'README.md').write_text((ROOT / 'standalone/README.md').read_text(encoding='utf-8').replace('../COMPATIBILITY.md', 'COMPATIBILITY.md'), encoding='utf-8')
shutil.copy(ROOT / 'COMPATIBILITY.md', PACKAGE / 'COMPATIBILITY.md')
# ONNX Runtime ships unused demonstration graphs; they are not required for inference.
for sample in (PACKAGE / '_internal/onnxruntime/datasets').glob('*.onnx'):
    sample.unlink()
# Piper also ships optional Arabic/Hebrew preprocessing models; keep these
# auxiliary language weights external, including in starter-voice builds.
for optional in ('piper/tashkeel/model.onnx', 'piper/hebrew/nakdimon.onnx'):
    (PACKAGE / '_internal' / optional).unlink(missing_ok=True)
models = [file.relative_to(PACKAGE).as_posix() for file in PACKAGE.rglob('*.onnx')
          if file.relative_to(PACKAGE).as_posix() != '_internal/faster_whisper/assets/silero_vad_v6.onnx']
expected_models = ['resources/voices/en_US-ljspeech-medium.onnx'] if options.bundle_starter_voice else []
if sorted(models) != expected_models:
    raise RuntimeError('Packaged voice weights differ from the selected build option')
print('Starter voice: ' + ('included for offline use' if options.bundle_starter_voice else 'download on demand'), flush=True)
if sys.platform == 'win32':
    with zipfile.ZipFile(OUT / 'Akousousin-Windows-x86_64.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in PACKAGE.rglob('*'):
            archive.write(file, Path('Akousousin') / file.relative_to(PACKAGE))
else:
    app = BUILD / 'AppDir'
    (app / 'usr/lib').mkdir(parents=True, exist_ok=True)
    shutil.copytree(PACKAGE, app / 'usr/lib/akousousin', dirs_exist_ok=True)
    shutil.copy(ROOT / 'standalone/AppRun', app / 'AppRun')
    (app / 'AppRun').chmod(0o755)
    (app / 'akousousin.desktop').unlink(missing_ok=True)
    (app / (APP_ID + '.desktop')).write_text('[Desktop Entry]\nType=Application\nName=Akousousin — Neural Voice Engine\nComment=Local neural speech and experimental Whisper dictation\nExec=AppRun\nIcon=akousousin\nCategories=AudioVideo;Accessibility;\nTerminal=false\n')
    (app / 'akousousin.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" rx="24" fill="#087e82"/><path d="M30 52v24m17-40v56m17-66v76m17-62v48m17-32v16" stroke="white" stroke-width="7" stroke-linecap="round"/></svg>')
    runtime = CACHE / 'appimage-runtime'
    fetch('https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64', runtime,
          '617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46')
    subprocess.run(['mksquashfs', str(app), str(BUILD / 'app.squashfs'), '-noappend', '-root-owned',
                    '-comp', 'gzip', '-processors', '4'], check=True)
    with (OUT / 'Akousousin-x86_64.AppImage').open('wb') as output:
        output.write(runtime.read_bytes())
        with (BUILD / 'app.squashfs').open('rb') as squash:
            shutil.copyfileobj(squash, output)
    (OUT / 'Akousousin-x86_64.AppImage').chmod(0o755)
    # AppDir retains its AppImage marker. The unpacked package has a separate
    # identity so it can notify about updates but never replace an AppImage.
    marker = PACKAGE / 'resources/build.json'
    build = json.loads(marker.read_text(encoding='utf-8'))
    build['distribution'] = 'linux-tar'
    marker.write_text(json.dumps(build, indent=2), encoding='utf-8')
    for script, name in [('bundle-install.sh', 'install.sh'), ('bundle-uninstall.sh', 'uninstall.sh')]:
        shutil.copy(ROOT / 'standalone' / script, PACKAGE / name)
        (PACKAGE / name).chmod(0o755)
    with tarfile.open(OUT / 'Akousousin-Linux-x86_64.tar.gz', 'w:gz') as archive:
        archive.add(PACKAGE, arcname='Akousousin')

packages = (['Akousousin-Windows-x86_64.zip'] if sys.platform == 'win32' else
            ['Akousousin-x86_64.AppImage', 'Akousousin-Linux-x86_64.tar.gz'])
with (OUT / 'SHA256SUMS').open('w', encoding='ascii', newline='\n') as sums:
    for name in packages:
        with (OUT / name).open('rb') as stream:
            sums.write(hashlib.file_digest(stream, 'sha256').hexdigest() + '  ' + name + '\n')
