# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The control panel window: sidebar, page stack and one status line.

Closing the window never stops speech; the controller keeps running.
"""
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from .. import resources, updates
from . import dialogs, theme
from .actions import DictationTest, Preview
from .pages import PAGES
from .state import AppState
from .tasks import Tasks
from .widgets import text

# Names other parts of Akousousin use to open a page.
ALIASES = {'updates': 'advanced', 'overview': 'home', 'app integrations': 'apps', 'voice input': 'dictation'}


class MainWindow(QMainWindow):
    def __init__(self, path, offer_install=True, poll=True):
        super().__init__()
        self.path = Path(path)
        self.quit_when_idle = False
        self.setWindowTitle('Akousousin')
        self.setWindowIcon(QIcon(str(resources.root() / 'akousousin.png')))
        self.setStyleSheet(theme.style_sheet())
        self._ground = theme.current().ground
        self.tasks = Tasks(self)
        self.state = AppState(path, self.tasks, self, poll=poll)
        self.state.preview = Preview(self.state, self.tasks)
        self.state.dictation_test = DictationTest(self.state, self.tasks)

        ground = QWidget()
        ground.setObjectName('ground')
        outer = QVBoxLayout(ground)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QHBoxLayout()
        body.setSpacing(0)
        outer.addLayout(body, 1)
        body.addWidget(self._sidebar())
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        self.pages = {}
        self.visible_page = None
        self._build_pages()
        self.nav.currentRowChanged.connect(self._show_row)
        QApplication.instance().styleHints().colorSchemeChanged.connect(lambda _: QTimer.singleShot(0, self.retheme))
        QApplication.instance().installEventFilter(self)
        self.status = QLabel()
        self.status.setObjectName('status')
        self.status.setAccessibleName(self.tr('Status'))
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(self.status)
        self.setCentralWidget(ground)

        for number in range(1, len(PAGES) + 1):
            QShortcut(QKeySequence(f'Ctrl+{number}'), self, activated=lambda n=number: self._go_row(n - 1))
        self.state.notice.connect(self.notice)
        self.state.navigate.connect(self.go)
        self.state.activated.connect(self.activate)
        self.state.status_changed.connect(self._downloads)
        self.tasks.failed.connect(lambda problem: (self.notice(str(problem).splitlines()[0]), dialogs.error(self, problem)))
        self.tasks.idle.connect(self._idle)

        area = self.screen().availableGeometry()
        self.resize(min(1180, area.width()), min(800, area.height()))
        self.setMinimumSize(QSize(min(720, area.width()), min(520, area.height())))
        self.nav.setCurrentRow(0)
        self.nav.setFocus()
        first = updates.completed_update(self.path) or self.state.config.get('speechd_setup_warning') or self.tr('Ready')
        self.notice(first)
        if offer_install:
            QTimer.singleShot(700, lambda: self.pages['advanced'].first_run())

    def _build_pages(self):
        for page_class in PAGES:
            page = page_class(self.state, self.tasks)
            scroll = QScrollArea()
            scroll.setObjectName('pageScroll')
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            scroll.setAccessibleName(page.title())
            self.stack.addWidget(scroll)
            self.pages[page.key] = page
            item = QListWidgetItem(theme.icon(page.icon, theme.current().text, 20), page.title())
            item.setData(Qt.UserRole, page.key)
            item.setSizeHint(QSize(0, 46))
            self.nav.addItem(item)

    def retheme(self):
        """Follow a light/dark switch without restarting: restyle and redraw every page."""
        if theme.current().ground == self._ground:
            return
        self._ground = theme.current().ground
        key = self.current_page().key if self.nav.currentItem() else 'home'
        self.setStyleSheet(theme.style_sheet())
        self.tile.setStyleSheet(f'background: {theme.current().accent}; border-radius: 9px')
        if self.visible_page is not None:
            self.visible_page.hidden()
            self.visible_page = None
        self.nav.blockSignals(True)
        self.nav.clear()
        while self.stack.count():
            widget = self.stack.widget(0)
            self.stack.removeWidget(widget)
            widget.deleteLater()
        self.pages = {}
        self._build_pages()
        self.nav.blockSignals(False)
        self.go(key)

    def eventFilter(self, watched, event):
        # The desktop changed its palette (light/dark) while the panel is open.
        if watched is QApplication.instance() and event.type() == QEvent.ApplicationPaletteChange:
            QTimer.singleShot(0, self.retheme)
        return False

    def _sidebar(self):
        side = QWidget()
        side.setObjectName('brand')
        side.setFixedWidth(236)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        brand = QHBoxLayout()
        brand.setContentsMargins(22, 22, 14, 14)
        brand.setSpacing(10)
        tile = self.tile = QLabel()
        tile.setFixedSize(34, 34)
        tile.setAlignment(Qt.AlignCenter)
        tile.setStyleSheet(f'background: {theme.current().accent}; border-radius: 9px')
        tile.setPixmap(theme.pixmap('voices', 20, '#FFFFFF'))
        words = QVBoxLayout()
        words.setSpacing(0)
        name = text('Akousousin', wrap=False)
        name.setStyleSheet('font-weight: 700; font-size: 16px')
        words.addWidget(name)
        words.addWidget(text(self.tr('Neural speech for Linux'), 'small', wrap=False))
        brand.addWidget(tile)
        brand.addLayout(words, 1)
        layout.addLayout(brand)
        self.nav = QListWidget()
        self.nav.setObjectName('nav')
        self.nav.setAccessibleName(self.tr('Pages'))
        self.nav.setIconSize(QSize(20, 20))
        self.nav.setStyleSheet('QListWidget#nav { border-right: 0; }')
        layout.addWidget(self.nav, 1)
        return side

    # Navigation -----------------------------------------------------------
    def _show_row(self, index):
        if self.visible_page is not None:
            self.visible_page.hidden()
        self.stack.setCurrentIndex(index)
        self.visible_page = self.pages[self.nav.item(index).data(Qt.UserRole)]
        if self.isVisible() and not self.isMinimized():
            self.visible_page.shown()

    def showEvent(self, event):
        super().showEvent(event)
        if self.visible_page is not None:
            self.visible_page.shown()

    def hideEvent(self, event):
        if self.visible_page is not None:
            self.visible_page.hidden()
        super().hideEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange and self.visible_page is not None:
            self.visible_page.hidden() if self.isMinimized() else self.visible_page.shown()
        super().changeEvent(event)

    def _go_row(self, index):
        if 0 <= index < self.nav.count():
            self.nav.setCurrentRow(index)
            self.nav.setFocus()

    def go(self, key):
        key = ALIASES.get(key.lower(), key.lower())
        for index in range(self.nav.count()):
            if self.nav.item(index).data(Qt.UserRole) == key:
                self._go_row(index)
                return

    def current_page(self):
        return self.pages[self.nav.currentItem().data(Qt.UserRole)]

    def activate(self, page):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if page:
            self.go(page)

    # Status ---------------------------------------------------------------
    def notice(self, message):
        if not message or message == self.status.text():
            return
        self.status.setText(message)
        if QAccessible.isActive():
            QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(self.status, message))

    def _downloads(self, status):
        from ..download_status import caption
        active = [caption(item) for item in status.downloads]
        if active:
            self.status.setText(' · '.join(active))

    # Closing ----------------------------------------------------------------
    def closeEvent(self, event):
        self.state.preview.stop()
        if self.tasks.busy():
            # Let installs and downloads finish; the window goes away now.
            self.quit_when_idle = True
            self.hide()
            event.ignore()
            return
        self.state.timer.stop()
        super().closeEvent(event)

    def _idle(self):
        if self.quit_when_idle:
            self.state.timer.stop()
            QApplication.instance().quit()
