#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Regenerate the application icon files from the tray artwork.

The app icon is the tray's five logo bars (ui/tray.py BARS) in white on the
v1 green. Run after changing either, and commit the results:

    python standalone/make_icons.py
"""
import io
import os
from pathlib import Path
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path[:0] = [str(Path(__file__).parent), str(Path(__file__).parents[1] / 'backend')]
from PIL import Image  # noqa: E402
from PySide6.QtCore import QByteArray, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

from akousousin_app.ui.tray import BARS, GREEN  # noqa: E402

RESOURCES = Path(__file__).parent / 'resources'
SCALE = .78  # the bars fill the tray icon; leave the rounded square a margin


def svg():
    lines = ''.join(f'<line x1="{x}" y1="{top}" x2="{x}" y2="{bottom}"/>' for x, top, bottom in BARS)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 24 24">'
            f'<rect width="24" height="24" rx="5.4" fill="{GREEN.name()}"/>'
            f'<g transform="translate(12 12) scale({SCALE}) translate(-12 -12)" stroke="#ffffff" '
            f'stroke-width="2.3" stroke-linecap="round">{lines}</g></svg>\n')


def render(text, size):
    renderer = QSvgRenderer(QByteArray(text.encode()))
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    buffer = QByteArray()
    from PySide6.QtCore import QBuffer
    device = QBuffer(buffer)
    device.open(QBuffer.WriteOnly)
    image.save(device, 'PNG')
    return Image.open(io.BytesIO(bytes(buffer))).convert('RGBA')


def main():
    QGuiApplication([])
    text = svg()
    (RESOURCES / 'akousousin.svg').write_text(text, encoding='utf-8')
    render(text, 128).save(RESOURCES / 'akousousin.png')
    sizes = (16, 20, 24, 32, 40, 48, 64, 128, 256)
    images = [render(text, size) for size in sizes]
    images[-1].save(RESOURCES / 'akousousin.ico', sizes=[(s, s) for s in sizes], append_images=images[:-1])
    print('Wrote', ', '.join(f'akousousin.{kind}' for kind in ('svg', 'png', 'ico')))


if __name__ == '__main__':
    main()
