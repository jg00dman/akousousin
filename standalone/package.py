#!/usr/bin/env python3
"""Build the independent panel/service. Reuse a published Wine SAPI DLL, never compile Wine."""
import ast
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

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'standalone-dist'
BUILD = ROOT / 'build/standalone-package'
RESOURCE = BUILD / 'resources'
SOURCE = OUT / 'sources'
CACHE = BUILD / 'downloads'
for directory in (OUT, RESOURCE, SOURCE, CACHE):
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
# Program-only distribution: catalogue metadata is included, never model weights.
# Users import a local voice or download from upstream after licence review.

# The user explicitly approved this one reviewed starter voice for redistribution.
# Catalogue downloads preserve its upstream model card and MIT/public-domain provenance.
from akousousin_app import catalogue, __version__
from akousousin_app.desktop_identity import APP_ID
with tempfile.TemporaryDirectory(dir=BUILD) as temporary:
    entry = catalogue.catalogue(ROOT / 'standalone/resources')['en_US-ljspeech-medium']
    voice = catalogue.install(entry, Path(temporary), reviewed=True)
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
    fetch(published + 'wine-source-11.21-logos.tar.xz', SOURCE / 'wine-compat-matching-source.tar.xz',
          '614fbe45f5afca787810348f3fc848c6b8736bc8db7d74a321356260da7ba565')
    (compat / 'provenance.json').write_text(json.dumps({'version': '11.21', 'source_commit':
         '3b19eb0e45ac5f57301073fc9e721cac7829dc93', 'release': 'wine-compat-11.21-3b19eb0e45ac'}, indent=2))

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
                                               'commit': commit, 'version': __version__}, indent=2))
recognition_options = []
if importlib.util.find_spec('faster_whisper') is not None:
    for dependency in ('faster_whisper', 'ctranslate2', 'tokenizers', 'av'):
        recognition_options += ['--collect-all', dependency]
subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', '--onedir', '--name', 'akousousin',
                '--distpath', str(BUILD / 'frozen'), '--workpath', str(BUILD / 'freeze'), '--specpath', str(BUILD),
                '--paths', str(ROOT / 'standalone'), '--paths', str(ROOT / 'backend'),
                '--exclude-module', 'readline', '--collect-all', 'piper', '--collect-all', 'numpy',
                '--collect-all', 'onnxruntime', *recognition_options, str(ROOT / 'standalone/entrypoint.py')], check=True)

PACKAGE = BUILD / 'Akousousin'
shutil.copytree(BUILD / 'frozen/akousousin', PACKAGE, dirs_exist_ok=True)
shutil.copytree(RESOURCE, PACKAGE / 'resources', dirs_exist_ok=True)
shutil.copy(ROOT / 'standalone/SPEECH-DISPATCHER.md', PACKAGE / 'SPEECH-DISPATCHER.md')
notices = PACKAGE / 'licenses'
notices.mkdir(exist_ok=True)
shutil.copy(ROOT / 'LICENSE', notices / 'Engine-LGPL-2.1.txt')
shutil.copy(ROOT / 'backend/LICENSE', notices / 'Panel-and-service-GPL-3.0.txt')
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
# Piper also ships optional Arabic/Hebrew preprocessing models; keep all neural
# weights external in this beta, including those auxiliary language resources.
for optional in ('piper/tashkeel/model.onnx', 'piper/hebrew/nakdimon.onnx'):
    (PACKAGE / '_internal' / optional).unlink(missing_ok=True)
models = [file.relative_to(PACKAGE).as_posix() for file in PACKAGE.rglob('*.onnx')
          if file.relative_to(PACKAGE).as_posix() != '_internal/faster_whisper/assets/silero_vad_v6.onnx']
if models != ['resources/voices/en_US-ljspeech-medium.onnx']:
    raise RuntimeError('Only the explicitly approved LJSpeech starter voice may be bundled')
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
    # Corresponding sources for our DLL/panel and the separately bundled GPL backend.
    subprocess.run(['git', 'archive', '--format=tar.gz', '--output', str(SOURCE / 'akousousin-source.tar.gz'), 'HEAD'], check=True)
    fetch('https://github.com/OHF-Voice/piper1-gpl/archive/refs/tags/v1.8.0.tar.gz', SOURCE / 'piper-1.8.0.tar.gz')
    fetch('https://github.com/espeak-ng/espeak-ng/archive/724808c.tar.gz', SOURCE / 'espeak-ng.tar.gz')
    # Matching LGPL Qt/PySide sources for the tray and local IPC libraries.
    for module in ('qtbase', 'qtsvg', 'qtwayland', 'qtdeclarative', 'qtshadertools', 'qttools', 'qtimageformats'):
        fetch(f'https://github.com/qt/{module}/archive/refs/tags/v6.8.3.tar.gz', SOURCE / f'{module}-6.8.3.tar.gz')
    fetch('https://github.com/pyside/pyside-setup/archive/refs/tags/v6.8.3.tar.gz', SOURCE / 'pyside-setup-6.8.3.tar.gz')
    with tarfile.open(OUT / 'Akousousin-corresponding-sources.tar.gz', 'w:gz') as archive:
        archive.add(SOURCE, arcname='sources')

with (OUT / 'SHA256SUMS').open('w', encoding='ascii', newline='\n') as sums:
    for file in sorted(OUT.iterdir()):
        if file.suffix in ('.AppImage', '.zip', '.gz'):
            sums.write(hashlib.file_digest(file.open('rb'), 'sha256').hexdigest() + '  ' + file.name + '\n')
