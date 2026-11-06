#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Audit original-source notices and the licence files in standalone packages."""
import argparse
import re
from pathlib import Path
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = {
    'engine/include/sapiddk.h', 'engine/include/sperror.h',
    'standalone/resources/catalogue.json', 'standalone/resources/CATALOGUE-LICENSE.md',
    'recognition/Python-LICENSE.txt', 'recognition/Whisper-LICENSE',
    'scripts/ci/type2-runtime.LICENSE',
}
SUFFIXES = {'.py', '.sh', '.c', '.h', '.md', '.yml', '.yaml', '.toml', '.json'}
SPECIAL = {'Dockerfile', 'AppRun', '.gitignore'}
NOTICE_FILES = {
    'Akousousin-GPL-3.0.txt': 'LICENSE',
    'Engine-LGPL-2.1.txt': 'LICENSES/LGPL-2.1-or-later.txt',
    'Akousousin-LICENSING.md': 'LICENSING.md',
}


def audit_source():
    gpl = (ROOT / 'LICENSE').read_bytes()
    lgpl = (ROOT / 'LICENSES/LGPL-2.1-or-later.txt').read_bytes()
    assert b'GNU GENERAL PUBLIC LICENSE' in gpl and b'Version 3, 29 June 2007' in gpl
    assert b'GNU LESSER GENERAL PUBLIC LICENSE' in lgpl and b'Version 2.1, February 1999' in lgpl
    for component in ('backend', 'standalone'):
        assert (ROOT / component / 'LICENSE').read_bytes() == gpl, component
        metadata = tomllib.loads((ROOT / component / 'pyproject.toml').read_text(encoding='utf-8'))
        assert metadata['project']['license']['text'] == 'GPL-3.0-or-later'
        assert metadata['tool']['setuptools']['license-files'] == ['LICENSE']
    files = subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines()
    count = 0
    for name in files:
        file = Path(name)
        if name in UPSTREAM or file.suffix == '.patch' or file.name == 'LICENSE':
            continue
        if file.suffix not in SUFFIXES and file.name not in SPECIAL:
            continue
        licence = 'LGPL-2.1-or-later' if file.parts[0] == 'engine' and file.suffix in ('.c', '.h') else 'GPL-3.0-or-later'
        notice = ROOT / (name + '.license') if file.suffix == '.json' else ROOT / name
        header = notice.read_text(encoding='utf-8')[:400]
        identifiers = re.findall(r'SPDX-License-Identifier:\s*([A-Za-z0-9.+-]+)', header)
        assert identifiers == [licence], (name, identifiers)
        assert 'SPDX-FileCopyrightText: 2026 John Goodman' in header, name
        if file.suffix == '.sh' or file.name == 'AppRun':
            assert (ROOT / name).read_bytes().startswith(b'#!'), name
        count += 1
    print(f'PASS: notices for {count} original sources; GPL metadata and LGPL component text')


def check_notices(read):
    for packaged, source in NOTICE_FILES.items():
        assert read(packaged) == (ROOT / source).read_bytes(), packaged


def audit_package(package):
    check_notices(lambda name: (package / 'licenses' / name).read_bytes())
    if sys.platform == 'win32':
        archive = ROOT / 'standalone-dist/Akousousin-Windows-x86_64.zip'
        with zipfile.ZipFile(archive) as output:
            check_notices(lambda name: output.read('Akousousin/licenses/' + name))
        print('PASS: Windows ZIP contains project GPL, engine LGPL and component notices')
    else:
        squash = ROOT / 'build/standalone-package/app.squashfs'
        check_notices(lambda name: subprocess.check_output([
            'unsquashfs', '-cat', str(squash), 'usr/lib/akousousin/licenses/' + name]))
        print('PASS: AppImage filesystem contains project GPL, engine LGPL and component notices')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, help='Also check the built package and ZIP/AppImage filesystem')
    arguments = parser.parse_args()
    audit_source()
    if arguments.package:
        audit_package(arguments.package)
