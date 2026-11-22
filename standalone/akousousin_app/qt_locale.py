# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from . import resources
from .desktop_identity import APP_ID


def application():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName('Akousousin')
    app.setDesktopFileName(APP_ID)
    install_translators(app)
    return app


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
