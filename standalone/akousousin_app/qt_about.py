# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QLabel

from . import __version__, resources
from .qt_widgets import actions, group, label, tr


def about(panel, layout):
    form = group(layout, "About Akousousin")
    form.addRow(label(tr("Akousousin · {version}").format(version=__version__)))
    form.addRow(label(tr("Akousousin takes its name from the Greek ἀκούσουσιν, “they will hear,” in John 5:25.")))
    form.addRow(label(tr("“Truly, truly, I tell you, the hour is coming and has now come when the dead will hear the voice of the Son of God, and those who hear will live.”")))
    link = QLabel('<a href="https://biblia.com/bible/bsb/john/5/25">' + tr("John 5:25, Berean Standard Bible · Read on Biblia") + '</a>')
    link.setOpenExternalLinks(True)
    link.setTextInteractionFlags(Qt.TextBrowserInteraction)
    link.setFocusPolicy(Qt.StrongFocus)
    form.addRow(link)
    form = group(layout, "Our story")
    form.addRow(label(tr("Akousousin began with an effort to make Logos Bible Software work on Linux through Wine. Support for biblical languages remains one of the project’s goals.")))
    form.addRow(label(tr("That work drew our attention to a gap in speech accessibility on Linux desktops. Akousousin grew to help people hear text read aloud and dictate in the applications they already use.")))
    form = group(layout, "Credits and licences")
    for paragraph in (
        tr("Piper, maintained by the Open Home Foundation’s voice project, provides speech synthesis (GPL-3.0-or-later)."),
        tr("OpenAI’s Whisper provides the speech recognition models (MIT)."),
        tr("SYSTRAN and the faster-whisper contributors make local dictation possible with CTranslate2 (MIT)."),
        tr("Original Akousousin code © 2026 John Goodman, GPL-3.0-or-later. SAPI engine C code and headers are LGPL-2.1-or-later and retain Wine copyright notices."),
        tr("Each voice has its own licence in Voices. The Berean Standard Bible quotation is in the public domain.")):
        form.addRow(label(paragraph))
    actions(form, ("Read full licences and notices…", lambda: notices(panel)))


def notices(panel):
    folder = resources.root().parent / 'licenses'
    if folder.is_dir():
        files = {str(p.relative_to(folder)): p for p in sorted(folder.rglob('*')) if p.is_file()}
    else:
        root = Path(__file__).resolve().parents[2]
        files = {name: root / name for name in ('LICENSING.md', 'LICENSE', 'LICENSES/LGPL-2.1-or-later.txt',
                 'recognition/Whisper-LICENSE', 'standalone/resources/CATALOGUE-LICENSE.md') if (root / name).is_file()}
    if files:
        name, ok = QInputDialog.getItem(panel, tr("Licences and notices"), tr("Document"), list(files), 0, False)
        if ok:
            panel.document(name, files[name].read_text(encoding='utf-8', errors='replace'))
    else:
        panel.notice(tr("No bundled licence directory was found."))
