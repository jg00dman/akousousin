# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
from PySide6.QtCore import QLibraryInfo, QLocale, QObject, QTranslator, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from . import resources, runtime
from .desktop_identity import APP_ID


def application():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName('Akousousin')
    app.setDesktopFileName(APP_ID)
    install_translators(app)
    install_link_handler(app)
    return app


class LinkHandler(QObject):
    @Slot(QUrl)
    def open(self, url):
        runtime.open_external(url.toString())


def install_link_handler(app):
    """Send every web link, including those in labels, to the desktop's browser."""
    if not hasattr(app, 'link_handler'):
        app.link_handler = LinkHandler(app)
        for scheme in ('http', 'https'):
            QDesktopServices.setUrlHandler(scheme, app.link_handler, 'open')


def install_translators(app):
    """Load Qt's and Akousousin's translations for the system language, once."""
    if not hasattr(app, 'translators'):
        app.translators = []
        for domain, directory in (
            ('qtbase', QLibraryInfo.path(QLibraryInfo.TranslationsPath)),
            ('akousousin', str(resources.root() / 'translations')),
        ):
            translator = QTranslator(app)
            if translator.load(QLocale(), domain, '_', directory):
                app.installTranslator(translator)
                app.translators.append(translator)
