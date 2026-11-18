# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Shared native controls for the configuration window."""
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QPushButton, QSpinBox)


def tr(source):
    return QCoreApplication.translate("Panel", source)


def label(text=""):
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(True)
    widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return widget


def group(layout, title):
    box = QGroupBox(tr(title))
    form = QFormLayout(box)
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    layout.addWidget(box)
    return form


def actions(form, *items):
    row = QHBoxLayout()
    buttons = []
    for title, callback in items:
        button = QPushButton(tr(title))
        button.clicked.connect(lambda checked=False, fn=callback: fn())
        row.addWidget(button)
        buttons.append(button)
    row.addStretch()
    form.addRow(row)
    return buttons


def field(form, title, widget):
    caption = QLabel(tr(title))
    caption.setBuddy(widget)
    widget.setAccessibleName(caption.text())
    form.addRow(caption, widget)
    return widget


def choices(form, title, values, current):
    box = QComboBox()
    for key, caption in values:
        box.addItem(caption, key)
    if box.findData(current) == -1:
        box.addItem(current, current)
    box.setCurrentIndex(box.findData(current))
    return field(form, title, box)


def number(form, title, low, high, value, step=1):
    box = QSpinBox() if isinstance(step, int) else QDoubleSpinBox()
    box.setRange(low, high)
    box.setSingleStep(step)
    box.setValue(value)
    return field(form, title, box)


def check(form, title, value):
    box = QCheckBox(tr(title))
    box.setChecked(value)
    form.addRow(box)
    return box
