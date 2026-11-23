# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Find Wine prefixes on this computer, so people rarely need to browse for one.

Prefixes usually live in hidden folders (~/.wine, Bottles, Lutris, PlayOnLinux)
or inside an app's own folder (OuDedetai installs Logos with its prefix in
data/wine64_bottle). A prefix is a folder with drive_c and system.reg.
"""
from pathlib import Path

# Folders that hold prefixes directly, or one level down (each child a prefix).
SINGLE = ('.wine',)
CONTAINERS = ('.local/share/wineprefixes', '.local/share/bottles/bottles',
              '.var/app/com.usebottles.bottles/data/bottles/bottles', '.PlayOnLinux/wineprefix', 'Games')
SEARCH_DEPTH = 3          # e.g. ~/LogosBible10/data/wine64_bottle
SEARCH_LIMIT = 4000       # folders looked at in the home search, so it stays quick
SKIP = {'node_modules', 'snap', 'Downloads', 'Music', 'Pictures', 'Videos', 'Documents', 'Desktop', 'Public',
        'Templates'}


def is_prefix(path):
    try:
        return (path / 'drive_c').is_dir() and (path / 'system.reg').is_file()
    except OSError:
        return False


def _children(path):
    try:
        return sorted(child for child in path.iterdir() if child.is_dir() and not child.is_symlink())
    except OSError:
        return []


def find(home=None):
    """Prefixes found, Logos first, then app folders, then the usual places."""
    home = Path(home or Path.home())
    found = []

    def add(path):
        if path not in found and is_prefix(path):
            found.append(path)

    # Visible app folders first (OuDedetai's Logos install is ~/LogosBible10/data/wine64_bottle).
    seen, queue = 0, [(child, 1) for child in _children(home) if not child.name.startswith('.') and child.name not in SKIP]
    while queue and seen < SEARCH_LIMIT:
        folder, depth = queue.pop(0)
        seen += 1
        if is_prefix(folder):
            add(folder)
            continue  # nothing useful inside drive_c
        if depth < SEARCH_DEPTH:
            queue.extend((child, depth + 1) for child in _children(folder) if not child.name.startswith('.'))
    for name in SINGLE:
        add(home / name)
    for name in CONTAINERS:
        for child in _children(home / name):
            add(child)
    # Logos is what most people register first.
    return sorted(found, key=lambda path: not any(word in str(path).lower() for word in ('logos', 'faithlife')))


def display(path, home=None):
    """~/… form for showing a path."""
    home = Path(home or Path.home())
    try:
        return '~/' + str(Path(path).relative_to(home))
    except ValueError:
        return str(path)


if __name__ == '__main__':  # pragma: no cover
    for prefix in find():
        print(display(prefix))
