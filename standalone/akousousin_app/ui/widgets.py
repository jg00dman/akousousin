# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Small building blocks used by every page.

They take text that is already translated, so translatable strings stay at
the call sites where pyside6-lupdate can find them.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QRadioButton, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from . import theme


def text(value='', role=None, *, wrap=True, rich=False, select=False):
    label = QLabel(value)
    label.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    label.setWordWrap(wrap)
    if role:
        label.setProperty('role', role)
    if rich:
        label.setOpenExternalLinks(True)
        label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        label.setFocusPolicy(Qt.StrongFocus)
    elif select:
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
    return label


def link(caption, url):
    """A keyboard-reachable web link in the accent colour."""
    p = theme.current()
    label = text(f'<a href="{url}" style="color: {p.accent_text}">{caption}</a>', rich=True, wrap=False)
    label.setStyleSheet('font-size: 14px')
    label.setAccessibleName(caption)
    return label


def spread(left, *right, spacing=10):
    """``left`` takes the free space; ``right`` sits at the far end."""
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    if isinstance(left, QWidget):
        layout.addWidget(left, 1)
    else:
        layout.addLayout(left, 1)
    for widget in right:
        layout.addWidget(widget, 0, Qt.AlignVCenter)
    return layout


def restyle(widget, **properties):
    for name, value in properties.items():
        widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def button(caption, callback=None, *, kind=None, icon=None, accessible=None):
    widget = QPushButton(caption)
    if kind:
        widget.setProperty('kind', kind)
    if icon:
        p = theme.current()
        widget.setIcon(theme.icon(icon, '#FFFFFF' if kind in ('primary', 'round') else p.accent_text,
                                  30 if kind == 'round' else 18))
        if kind == 'round':
            widget.setIconSize(widget.iconSize() * 1.6)
    if accessible:
        widget.setAccessibleName(accessible)
    if callback:
        widget.clicked.connect(lambda checked=False: callback())
    widget.setCursor(Qt.PointingHandCursor)
    return widget


def set_icon(widget, name, kind=None):
    widget.setIcon(theme.icon(name, '#FFFFFF' if kind in ('primary', 'round') else theme.current().accent_text, 18))


def row(*widgets, spacing=10, stretch=True, wrap_alignment=Qt.AlignVCenter):
    layout = QHBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        if widget is None:
            continue
        if isinstance(widget, int):
            layout.addSpacing(widget)
        elif hasattr(widget, 'addWidget') and not isinstance(widget, QWidget):
            layout.addLayout(widget)
        else:
            # Wrapping text takes the free space instead of squeezing into a column.
            grow = 1 if isinstance(widget, QLabel) and widget.wordWrap() and widget.pixmap().isNull() else 0
            layout.addWidget(widget, grow, wrap_alignment)
    if stretch:
        layout.addStretch(1)
    return layout


class Rule(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName('rule')
        self.setFrameShape(QFrame.NoFrame)


class Card(QFrame):
    """A white panel with an optional heading; ``body`` is its vertical layout."""
    def __init__(self, title=None, subtitle=None, *, icon=None, padding=22, spacing=14):
        super().__init__()
        self.setObjectName('card')
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding - 2, padding, padding - 2)
        self.body.setSpacing(spacing)
        self.heading = None
        if title:
            self.heading = text(title, 'h2')
            if icon:
                image = QLabel()
                image.setPixmap(theme.pixmap(icon, 20, theme.current().accent_text))
                self.body.addLayout(row(image, self.heading, spacing=10))
            else:
                self.body.addWidget(self.heading)
            self.setAccessibleName(title)
        if subtitle:
            self.body.addWidget(text(subtitle, 'muted'))

    def add(self, item):
        if isinstance(item, QWidget):
            self.body.addWidget(item)
        else:
            self.body.addLayout(item)
        return item


def dot_pixmap(color, size=10):
    image = QPixmap(size * 2, size * 2)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size * 2, size * 2)
    painter.end()
    image.setDevicePixelRatio(2)
    return image


def dot(color, size=10):
    label = QLabel()
    label.setPixmap(dot_pixmap(color, size))
    return label


class StatusLine(QWidget):
    """A coloured dot followed by text; the dot is decoration only."""
    def __init__(self, value=''):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.dot = QLabel()
        self.label = text(value)
        self.label.setStyleSheet('font-size: 15px')
        layout.addWidget(self.dot, 0, Qt.AlignVCenter)
        layout.addWidget(self.label, 1)
        self.set(value, 'ok')

    def set(self, value, tone='ok'):
        p = theme.current()
        colour = {'ok': p.ok, 'caution': p.caution, 'off': p.muted, 'danger': p.danger}[tone]
        self.dot.setPixmap(dot_pixmap(colour))
        self.label.setText(value)


class Keys(QWidget):
    """Keyboard keys drawn as key caps, read by screen readers as one phrase."""
    def __init__(self, keys=()):
        super().__init__()
        self.layout_ = QHBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(4)
        self.set(keys)

    def set(self, keys):
        while self.layout_.count():
            item = self.layout_.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for key in keys:
            cap = text(key, 'key', wrap=False)
            cap.setAccessibleName('')
            self.layout_.addWidget(cap)
        self.setAccessibleName('+'.join(keys))
        self.setVisible(bool(keys))


class SettingRow(QWidget):
    """A title and explanation on the left, controls on the right."""
    def __init__(self, title, explanation='', *controls, first=False):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        if not first:
            outer.addWidget(Rule())
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(20)
        words = QVBoxLayout()
        words.setSpacing(2)
        self.title = text(title, 'h3') if title else None
        if self.title:
            words.addWidget(self.title)
        self.explanation = text(explanation, 'muted') if explanation else None
        if self.explanation:
            words.addWidget(self.explanation)
        layout.addLayout(words, 1)
        self.controls = QHBoxLayout()
        self.controls.setSpacing(10)
        for control in controls:
            if isinstance(control, QWidget):
                self.controls.addWidget(control, 0, Qt.AlignVCenter)
                if self.title and not control.accessibleName() and not isinstance(control, (QPushButton, QLabel)):
                    control.setAccessibleName(title)
            else:
                self.controls.addLayout(control)
        layout.addLayout(self.controls)
        outer.addLayout(layout)


def labelled(caption, widget, help_text=''):
    """A field caption above a control, with optional help underneath."""
    box = QVBoxLayout()
    box.setSpacing(6)
    label = text(caption, 'h3')
    label.setBuddy(widget)
    widget.setAccessibleName(caption)
    box.addWidget(label)
    box.addWidget(widget)
    if help_text:
        help_label = text(help_text, 'small')
        widget.setAccessibleDescription(help_text)
        box.addWidget(help_label)
    return box


def combo(choices=(), current=None):
    box = QComboBox()
    box.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    box.setMinimumContentsLength(14)
    box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    fill(box, choices, current)
    return box


def fill(box, choices, current=None):
    """Replace a combo box's items without emitting change signals."""
    box.blockSignals(True)
    box.clear()
    for key, caption in choices:
        box.addItem(caption, key)
    index = box.findData(current)
    if index < 0 and current not in (None, ''):
        box.addItem(str(current), current)
        index = box.count() - 1
    box.setCurrentIndex(max(0, index))
    box.blockSignals(False)


class Choice(QFrame):
    """A radio button presented as a selectable card with a second line."""
    def __init__(self, title, detail, group, key):
        super().__init__()
        self.setObjectName('choice')
        self.key = key
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        self.radio = QRadioButton(title)
        self.radio.setStyleSheet('font-weight: 600')
        self.detail = text(detail, 'small')
        self.radio.setAccessibleDescription(detail)
        words = QVBoxLayout()
        words.setSpacing(0)
        words.addWidget(self.radio)
        words.addWidget(self.detail)
        layout.addLayout(words, 1)
        group.addButton(self.radio)
        self.radio.toggled.connect(lambda on: restyle(self, checked='true' if on else 'false'))

    def mousePressEvent(self, event):
        self.radio.click()

    def set_detail(self, detail):
        self.detail.setText(detail)
        self.radio.setAccessibleDescription(detail)


class Choices(QWidget):
    """A wrapping row of Choice cards; emits ``chosen`` with the key."""
    chosen = Signal(object)

    def __init__(self, options, current=None, accessible=''):
        super().__init__()
        self.group = QButtonGroup(self)
        self.items = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for key, title, detail in options:
            choice = Choice(title, detail, self.group, key)
            self.items[key] = choice
            layout.addWidget(choice, 1)
            choice.radio.clicked.connect(lambda checked=False, k=key: self.chosen.emit(k))
        self.setAccessibleName(accessible)
        self.select(current)

    def select(self, key):
        choice = self.items.get(key)
        if choice:
            choice.radio.blockSignals(True)
            choice.radio.setChecked(True)
            choice.radio.blockSignals(False)
            restyle(choice, checked='true')
            for other in self.items.values():
                if other is not choice:
                    restyle(other, checked='false')


class ValueSlider(QWidget):
    """A slider with its value shown as text; emits ``committed`` on release."""
    committed = Signal(float)

    def __init__(self, caption, low, high, step, value, formatter):
        super().__init__()
        self.low, self.step, self.formatter = low, step, formatter
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        top = QHBoxLayout()
        self.caption = text(caption, 'h3')
        self.value_label = text('', 'muted', wrap=False)
        top.addWidget(self.caption)
        top.addStretch(1)
        top.addWidget(self.value_label)
        layout.addLayout(top)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, round((high - low) / step))
        self.slider.setPageStep(max(1, round(.25 / step)) if step < .25 else 1)
        self.slider.setAccessibleName(caption)
        layout.addWidget(self.slider)
        self.slider.valueChanged.connect(self._show)
        self.slider.sliderReleased.connect(self._commit)
        self.slider.valueChanged.connect(self._maybe_commit)
        self.set(value)

    def value(self):
        return round(self.low + self.slider.value() * self.step, 4)

    def set(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(round((value - self.low) / self.step))
        self.slider.blockSignals(False)
        self._show()

    def _show(self, *_):
        shown = self.formatter(self.value())
        self.value_label.setText(shown)
        self.slider.setAccessibleDescription(shown)

    def _maybe_commit(self, *_):
        if not self.slider.isSliderDown():
            self._commit()

    def _commit(self):
        self.committed.emit(self.value())
