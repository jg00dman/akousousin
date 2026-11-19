# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Build pinned clipboard readers and bundle their private dependency closures."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

PROJECTS = (
    ('wl-clipboard', 'bugaevc/wl-clipboard', '3eb912c274042cd5deed6b478b39908a12f37498', 'wl-paste', 'GPL-3.0-or-later'),
    ('xclip', 'astrand/xclip', '9aa7090c3b8b437c6489edca32ae43d82e0c1281', 'xclip', 'GPL-2.0-or-later'),
)
GLIBC = {'libc.so.6', 'libm.so.6', 'libpthread.so.0', 'librt.so.1', 'libdl.so.2', 'libresolv.so.2'}


def bundle(package, cache, build, notices, fetch):
    root = package / 'resources/helpers'
    root.mkdir(parents=True, exist_ok=True)
    work = build / 'clipboard-builds'
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    records, libraries = [], []
    for name, repository, commit, binary, licence in PROJECTS:
        archive = cache / f'{name}-{commit}.tar.gz'
        url = f'https://github.com/{repository}/archive/{commit}.tar.gz'
        digest = fetch(url, archive)
        checkout = work / name
        checkout.mkdir()
        with tarfile.open(archive) as source:
            source.extractall(checkout, filter='data')
        source = next(checkout.iterdir())
        if name == 'wl-clipboard':
            for dependency in ('wayland-protocols', 'autotools-dev'):
                target = notices / 'clipboard' / dependency
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path('/usr/share/doc') / dependency / 'copyright', target / 'copyright')
            commands = [['meson', 'setup', 'build', '--buildtype=release', '--wrap-mode=nofallback'],
                        ['ninja', '-C', 'build', 'src/wl-paste']]
            executable = source / 'build/src/wl-paste'
        else:
            for file in ('config.guess', 'config.sub'):
                shutil.copy2(Path('/usr/share/misc') / file, source / file)
                shutil.copy2(source / file, auxiliary / file)
            commands = [['autoconf'], ['./configure'], ['make', '-j2']]
            executable = source / 'xclip'
        for command in commands:
            subprocess.run(command, cwd=source, check=True)
        destination = root / binary
        (destination / 'bin').mkdir(parents=True)
        (destination / 'lib').mkdir()
        shutil.copy2(executable, destination / 'bin' / binary)
        (destination / 'bin' / binary).chmod(0o755)
        linked = subprocess.check_output(['ldd', str(executable)], text=True)
        if 'not found' in linked:
            raise RuntimeError('Missing clipboard helper dependency: ' + linked)
        dependencies = []
        for soname, path in re.findall(r'^\s*(\S+)\s+=>\s+(/\S+)\s+\(', linked, re.M):
            if soname in GLIBC or soname.startswith('ld-linux'):
                continue
            file = Path(path).resolve()
            shutil.copy2(file, destination / 'lib' / soname)
            libraries.append(str(file))
            dependencies.append({'soname':soname, 'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
        notice = notices / 'clipboard' / name
        notice.mkdir(parents=True)
        shutil.copy2(source / 'COPYING', notice / 'COPYING')
        records.append({'project':name, 'binary':binary, 'commit':commit, 'source':url,
                        'source_sha256':digest, 'licence':licence, 'commands':commands,
                        'libraries':dependencies})
    provenance = json.dumps(records, indent=2)
    (root / 'provenance.json').write_text(provenance)
    return libraries
