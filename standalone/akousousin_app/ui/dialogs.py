# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Confirmation, document and error dialogs. Used only where a decision is needed."""
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from .widgets import text


translate = QCoreApplication.translate


def _dialog(parent, title):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(22, 20, 22, 18)
    layout.setSpacing(14)
    return dialog, layout


def confirm(parent, title, message, action, *, details=None):
    """Ask before doing something with consequences. Cancel is the default."""
    dialog, layout = _dialog(parent, title)
    layout.addWidget(text(title, 'h2'))
    if details or len(message) > 600:
        view = QPlainTextEdit(details or message)
        view.setReadOnly(True)
        view.setAccessibleName(title)
        if details:
            layout.addWidget(text(message))
        layout.addWidget(view)
        dialog.resize(640, 460)
    else:
        layout.addWidget(text(message))
        dialog.setMinimumWidth(460)
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.button(QDialogButtonBox.Ok).setText(action)
    box.button(QDialogButtonBox.Ok).setProperty('kind', 'primary')
    box.button(QDialogButtonBox.Cancel).setText(translate('Dialogs', 'Cancel'))
    box.button(QDialogButtonBox.Cancel).setDefault(True)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    layout.addWidget(box)
    return dialog.exec() == QDialog.Accepted


def document(parent, title, content):
    dialog, layout = _dialog(parent, title)
    view = QPlainTextEdit(content)
    view.setReadOnly(True)
    view.setAccessibleName(title)
    layout.addWidget(view)
    close = QPushButton(translate('Dialogs', 'Close'))
    close.clicked.connect(dialog.accept)
    buttons = QHBoxLayout()
    buttons.addStretch(1)
    buttons.addWidget(close)
    layout.addLayout(buttons)
    dialog.resize(660, 480)
    dialog.exec()


def error(parent, problem):
    """Show a failure with copyable details and, when known, a recovery command."""
    title = getattr(problem, 'title', None) or translate('Dialogs', 'Something went wrong')
    dialog, layout = _dialog(parent, title)
    layout.addWidget(text(title, 'h2'))
    layout.addWidget(text(str(problem)))
    details = getattr(problem, 'details', '') or ''
    if details:
        view = QPlainTextEdit(details)
        view.setReadOnly(True)
        view.setAccessibleName(translate('Dialogs', 'Details'))
        layout.addWidget(view)
    buttons = QHBoxLayout()
    command = getattr(problem, 'command', '')
    if command:
        copy_command = QPushButton(translate('Dialogs', 'Copy command'))
        copy_command.clicked.connect(lambda: QApplication.clipboard().setText(command))
        buttons.addWidget(copy_command)
    copy = QPushButton(translate('Dialogs', 'Copy details'))
    copy.clicked.connect(lambda: QApplication.clipboard().setText('\n'.join(filter(None, (str(problem), details)))))
    buttons.addWidget(copy)
    buttons.addStretch(1)
    close = QPushButton(translate('Dialogs', 'Close'))
    close.setDefault(True)
    close.clicked.connect(dialog.accept)
    buttons.addWidget(close)
    layout.addLayout(buttons)
    dialog.setMinimumWidth(520)
    dialog.exec()
