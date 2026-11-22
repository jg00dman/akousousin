# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Colours, the window style sheet and line icons.

Light and dark palettes follow the desktop colour scheme. Every text colour
meets 4.5:1 against the surface it is drawn on.
"""
from dataclasses import dataclass
import os

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    ground: str
    sidebar: str
    card: str
    border: str
    text: str
    muted: str
    accent: str        # filled buttons and selection (white text on it)
    accent_text: str   # links and accent-coloured text on the card colour
    accent_soft: str   # selected rows
    ok: str
    caution: str
    danger: str
    field: str


LIGHT = Palette('#F3F4F6', '#E8EAED', '#FFFFFF', '#D3D8DE', '#1F2328', '#525961',
                '#1E7046', '#1E7046', '#E4F1E9', '#1E7046', '#9A4E14', '#A1301F', '#FFFFFF')
DARK = Palette('#1C1F22', '#24282C', '#2B3035', '#454C53', '#ECEEF0', '#B3B9BF',
               '#1E7046', '#7FD1A5', '#23402F', '#7FD1A5', '#F0B37E', '#F2998C', '#22262A')


def current():
    app = QApplication.instance()
    if app is None:
        return LIGHT
    return DARK if app.palette().window().color().lightness() < 128 else LIGHT


def assets(p):
    """Small SVG images the style sheet needs (combo chevron, check mark)."""
    import tempfile
    from pathlib import Path
    folder = Path(tempfile.gettempdir()) / f'akousousin-theme-{os.getuid() if hasattr(os, "getuid") else 0}'
    folder.mkdir(exist_ok=True)
    images = {
        'chevron': f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{p.muted}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
        'check': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
    }
    paths = {}
    for name, svg in images.items():
        file = folder / f'{name}-{p.muted.strip("#")}.svg'
        if not file.exists():
            file.write_text(svg, encoding='utf-8')
        paths[name] = file.as_posix()
    return paths


def style_sheet(p=None):
    p = p or current()
    image = assets(p)
    return f"""
QMainWindow, QWidget#ground {{ background: {p.ground}; color: {p.text}; }}
QWidget#page, QScrollArea#pageScroll, QScrollArea#pageScroll > QWidget > QWidget {{ background: {p.ground}; }}
QScrollArea#pageScroll {{ border: 0; }}
QListWidget#nav {{ background: {p.sidebar}; border: 0; border-right: 1px solid {p.border}; padding: 8px 10px; font-size: 15px; outline: 0; }}
QListWidget#nav::item {{ color: {p.text}; min-height: 44px; padding: 0 10px; border-radius: 8px; margin: 2px 0; }}
QListWidget#nav::item:selected {{ background: {p.card}; color: {p.accent_text}; font-weight: 600; }}
QListWidget#nav::item:hover:!selected {{ background: {p.border}; }}
QWidget#brand {{ background: {p.sidebar}; }}
QFrame#card {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 12px; }}
QFrame#card QLabel, QFrame#card QCheckBox, QFrame#card QRadioButton {{ background: transparent; }}
QFrame#rule {{ background: {p.border}; max-height: 1px; min-height: 1px; border: 0; }}
QLabel {{ color: {p.text}; }}
QLabel[role="h1"] {{ font-size: 26px; font-weight: 700; }}
QLabel[role="h2"] {{ font-size: 17px; font-weight: 600; }}
QLabel[role="h3"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="title"] {{ font-size: 24px; font-weight: 700; }}
QLabel[role="muted"] {{ color: {p.muted}; font-size: 14px; }}
QLabel[role="small"] {{ color: {p.muted}; font-size: 13px; }}
QLabel[role="ok"] {{ color: {p.ok}; font-weight: 600; font-size: 14px; }}
QLabel[role="caution"] {{ color: {p.caution}; font-weight: 600; font-size: 14px; }}
QLabel[role="danger"] {{ color: {p.danger}; font-size: 14px; }}
QLabel[role="verse"] {{ font-size: 18px; }}
QLabel[role="key"] {{ background: {p.field}; border: 1px solid {p.border}; border-bottom-width: 2px; border-radius: 5px; padding: 1px 7px; font-size: 13px; }}
QPushButton {{ min-height: 40px; padding: 0 16px; border-radius: 8px; font-size: 15px; font-weight: 600;
              background: {p.card}; color: {p.text}; border: 1px solid {p.border}; }}
QPushButton:hover {{ border-color: {p.muted}; }}
QPushButton:disabled {{ color: {p.muted}; }}
QPushButton[kind="primary"] {{ background: {p.accent}; color: #FFFFFF; border-color: {p.accent}; }}
QPushButton[kind="primary"]:disabled {{ background: {p.border}; border-color: {p.border}; color: {p.muted}; }}
QPushButton[kind="danger"] {{ color: {p.danger}; }}
QPushButton[kind="link"] {{ border: 0; background: transparent; color: {p.accent_text}; padding: 0 4px; font-weight: 400; text-decoration: underline; min-height: 32px; }}
QPushButton[kind="round"] {{ min-width: 72px; max-width: 72px; min-height: 72px; max-height: 72px; border-radius: 36px; padding: 0;
                             background: {p.accent}; border: 0; }}
QPushButton:focus, QComboBox:focus, QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QSlider:focus,
QCheckBox:focus, QRadioButton:focus, QTreeView:focus {{ outline: 0; border: 2px solid {p.accent_text}; }}
QListWidget#nav::item:selected:focus {{ border: 2px solid {p.accent_text}; }}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{ background: {p.field}; color: {p.text}; border: 1px solid {p.border};
              border-radius: 8px; padding: 6px 10px; font-size: 15px; min-height: 28px; }}
QComboBox::drop-down {{ border: 0; width: 30px; }}
QComboBox::down-arrow {{ image: url({image['chevron']}); width: 16px; height: 16px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: 0; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 18px; height: 18px; border: 2px solid {p.muted}; background: {p.field}; }}
QCheckBox::indicator {{ border-radius: 5px; }}
QRadioButton::indicator {{ border-radius: 11px; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; image: url({image['check']}); }}
QRadioButton::indicator:checked {{ background: {p.field}; border: 6px solid {p.accent}; width: 10px; height: 10px; }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: {p.border}; }}
QComboBox QAbstractItemView {{ background: {p.field}; color: {p.text}; selection-background-color: {p.accent}; selection-color: #FFFFFF; }}
QPlainTextEdit#transcript {{ border-style: dashed; }}
QCheckBox, QRadioButton {{ font-size: 15px; spacing: 10px; min-height: 32px; }}
QFrame#choice {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 10px; }}
QFrame#choice[checked="true"] {{ background: {p.accent_soft}; border: 2px solid {p.accent}; }}
QTreeView {{ background: {p.card}; color: {p.text}; border: 1px solid {p.border}; border-radius: 12px; padding: 6px; font-size: 15px; }}
QTreeView::item {{ min-height: 40px; padding: 2px 4px; border-radius: 6px; }}
QTreeView::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
QHeaderView::section {{ background: {p.card}; color: {p.muted}; border: 0; border-bottom: 1px solid {p.border}; padding: 6px; font-size: 13px; font-weight: 600; }}
QSlider::groove:horizontal {{ height: 6px; background: {p.border}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 3px; }}
QSlider {{ min-height: 26px; }}
QSlider::handle:horizontal {{ background: {p.card}; border: 2px solid {p.accent}; width: 16px; height: 16px; margin: -7px 0; border-radius: 10px; }}
QLabel#status {{ background: {p.sidebar}; color: {p.muted}; border-top: 1px solid {p.border}; padding: 8px 20px; font-size: 13px; }}
QToolTip {{ color: {p.text}; background: {p.card}; border: 1px solid {p.border}; }}
"""


# Line icons on a 24 px grid, matching the agreed mockups.
PATHS = {
    'home': '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20h14V9.5"/>',
    'voices': '<path d="M4 10v4"/><path d="M8 7v10"/><path d="M12 4v16"/><path d="M16 7v10"/><path d="M20 10v4"/>',
    'mic': '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/>',
    'keys': '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 10h1M10 10h1M14 10h1M7 14h10"/>',
    'apps': '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/>'
            '<rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    'sliders': '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/>'
               '<circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h0"/>',
    'play': '<path d="M8 5.5v13l10-6.5z"/>',
    'stop': '<rect x="7" y="7" width="10" height="10" rx="1.5"/>',
    'shield': '<path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6z"/><path d="m9 12 2 2 4-4"/>',
    'search': '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    'check': '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    'copy': '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
    'star': '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
    'download': '<path d="M12 4v11"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/>',
}


def pixmap(name, size=20, color=None, ratio=None):
    color = color or current().text
    ratio = ratio or (QApplication.instance().devicePixelRatio() if QApplication.instance() else 1)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>')
    image = QPixmap(int(size * ratio), int(size * ratio))
    image.fill(Qt.transparent)
    painter = QPainter(image)
    QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(0, 0, size * ratio, size * ratio))
    painter.end()
    image.setDevicePixelRatio(ratio)
    return image


def icon(name, color=None, size=20):
    return QIcon(pixmap(name, size, color))
