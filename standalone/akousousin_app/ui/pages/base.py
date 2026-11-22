# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The common shape of a page: a heading, a short sentence and cards."""
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .. import dialogs
from ..widgets import text


class Page(QWidget):
    key = ''          # stable identifier used for navigation
    icon = ''

    def __init__(self, state, tasks):
        super().__init__()
        self.setObjectName('page')
        self.state, self.tasks = state, tasks
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(36, 28, 36, 28)
        self.layout_.setSpacing(18)
        header = QVBoxLayout()
        header.setSpacing(4)
        self.heading = text(self.title(), 'h1')
        header.addWidget(self.heading)
        if self.subtitle():
            header.addWidget(text(self.subtitle(), 'muted'))
        self.layout_.addLayout(header)
        self.build()
        self.layout_.addStretch(1)
        state.settings_changed.connect(self.settings_changed)
        state.status_changed.connect(self.status_changed)

    # Subclasses provide these.
    def title(self):
        raise NotImplementedError

    def subtitle(self):
        return ''

    def build(self):
        raise NotImplementedError

    def settings_changed(self, config):
        pass

    def status_changed(self, status):
        pass

    def shown(self):
        """Called each time the page becomes visible."""

    # Helpers --------------------------------------------------------------
    def add(self, item):
        if isinstance(item, QWidget):
            self.layout_.addWidget(item)
        else:
            self.layout_.addLayout(item)
        return item

    def columns(self, *groups, spacing=18):
        """Side-by-side columns of cards that stack on narrow windows."""
        from ..flow import Columns
        return self.add(Columns(groups, spacing))

    def notice(self, message):
        self.state.notice.emit(message)

    def error(self, problem):
        self.notice(str(problem).splitlines()[0] if str(problem) else '')
        dialogs.error(self, problem)

    def confirm(self, title, message, action, **options):
        return dialogs.confirm(self, title, message, action, **options)

    def run(self, work, done=None, *, key=None, failed=None, busy=None):
        """Run work in the background, showing ``busy`` while it runs."""
        if busy:
            self.notice(busy)
        started = self.tasks.run(work, done, key=key or self.key, failed=failed or self.error)
        if not started and not self.tasks.closing:
            self.notice(self.tr('Please wait for the current task to finish.'))
        return started


def hbox(*widgets, spacing=12):
    layout = QHBoxLayout()
    layout.setSpacing(spacing)
    for widget in widgets:
        layout.addWidget(widget)
    return layout
