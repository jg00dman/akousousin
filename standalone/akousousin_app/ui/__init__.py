# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The Akousousin control panel.

Structure (see standalone/UI-ARCHITECTURE.md):

* ``state.AppState`` owns settings and live status and is the only poller.
* ``tasks.Tasks`` runs blocking work off the GUI thread; results come back as
  signals, never by touching widgets from a worker.
* ``pages/`` holds one ``Page`` subclass per sidebar destination. Pages talk to
  ``AppState`` and ``Tasks`` only, never to each other.
* ``window.MainWindow`` is the sidebar, the page stack and the status line.
"""
