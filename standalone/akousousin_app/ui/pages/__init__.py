# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Sidebar destinations, in order. Adding a page means adding one file and one line here."""
from .about import AboutPage
from .advanced import AdvancedPage
from .apps import AppsPage
from .dictation import DictationPage
from .home import HomePage
from .privacy import PrivacyPage
from .shortcuts import ShortcutsPage
from .voices import VoicesPage

PAGES = (HomePage, VoicesPage, DictationPage, ShortcutsPage, AppsPage, AdvancedPage, PrivacyPage, AboutPage)
