# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Monochrome tray icons that the desktop recolours to suit its panel.

A tray icon sent as a picture keeps the colours it was drawn with. Akousousin
bundles its own Qt, which does not know the desktop's colour scheme, so the
logo lines came out dark on a dark panel. Icons installed in the user's icon
theme and sent by name are drawn by the desktop instead: Plasma (and GNOME's
AppIndicator extension) recolour these symbolic SVGs, which use the Breeze
``ColorScheme-Text`` / ``currentColor`` convention, to match the panel.

The ready icon is the still logo; the reading animation is a set of frames.
"""
import math
import os
from pathlib import Path

BARS = ((4, 10, 14), (8, 7, 17), (12, 4, 20), (16, 7, 17), (20, 10, 14))  # x, top, bottom on a 24 grid
FRAMES = 12
PREFIX = 'akousousin-tray-'
READY = PREFIX + 'ready-symbolic'


def reading(frame):
    return f'{PREFIX}reading-{frame:02d}-symbolic'


def names():
    return [READY, *(reading(frame) for frame in range(FRAMES))]


def directory():
    base = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    return base / 'icons/hicolor/scalable/status'


def svg(phase=None):
    """The logo lines; with a phase (0–1) they rise and fall as in the drawn icon."""
    lines = []
    for index, (x, top, bottom) in enumerate(BARS):
        middle, half = (top + bottom) / 2, (bottom - top) / 2
        if phase is not None:
            wave = .5 - .5 * math.cos(2 * math.pi * (phase - index * .125))
            half *= 1 - .55 * wave
        lines.append(f'M{x} {middle - half:.2f}V{middle + half:.2f}')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24">'
            '<style id="current-color-scheme" type="text/css">.ColorScheme-Text{color:#232629}</style>'
            '<path class="ColorScheme-Text" fill="none" stroke="currentColor" stroke-width="2.1" '
            f'stroke-linecap="round" d="{"".join(lines)}"/></svg>\n')


def contents():
    return {READY: svg(), **{reading(frame): svg(frame / FRAMES) for frame in range(FRAMES)}}


def install():
    """Write the icons if they are missing or out of date. Returns their directory."""
    target = directory()
    target.mkdir(parents=True, exist_ok=True)
    for name, text in contents().items():
        path = target / (name + '.svg')
        try:
            if path.read_text(encoding='utf-8') == text:
                continue
        except OSError:
            pass
        temporary = path.with_name('.' + path.name + '.tmp')
        temporary.write_text(text, encoding='utf-8')
        temporary.replace(path)
    return target


def remove():
    for name in names():
        (directory() / (name + '.svg')).unlink(missing_ok=True)
