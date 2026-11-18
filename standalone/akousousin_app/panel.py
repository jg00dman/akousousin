# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Native Qt control panel. Controller-owned speech survives closing the window."""
import os
from pathlib import Path
import threading

from PySide6.QtCore import Qt, QTimer, Signal, Slot, QUrl
from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent, QDesktopServices, QIcon
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLineEdit, QListWidget, QMainWindow, QPlainTextEdit, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget)

from . import appimage_install, download_status, resources, runtime, settings, updates, voice_preview
from .languages import label as language_name
from .qt_about import about
from .qt_dictation import Dictation
from .qt_integrations import Integrations
from .qt_voices import Voices
from .qt_widgets import actions, check, choices, field, group, label, number, tr
from .service import Service


class Panel(QMainWindow):
    completed = Signal(object, object, object, object, bool)
    destinations = ("Overview", "Voices", "Dictation", "App integrations", "Shortcuts", "About")

    def __init__(self, path, offer_install=True):
        super().__init__()
        self.path = Path(path)
        self.config = resources.bootstrap(path)
        self.service = Service(path)
        self.busy = self.polling = self.closed = False
        self.last_activation = 0
        self.preview_stop = threading.Event()
        self.input_cancel = threading.Event()
        self.completed.connect(self.finish, Qt.QueuedConnection)
        self.setWindowTitle(tr("Akousousin"))
        self.setWindowIcon(QIcon(str(resources.root() / 'akousousin.png')))
        area = self.screen().availableGeometry()
        self.resize(min(980, area.width()), min(740, area.height()))
        central = QWidget()
        outer = QVBoxLayout(central)
        self.setCentralWidget(central)
        body = QHBoxLayout()
        outer.addLayout(body, 1)
        self.nav = QListWidget()
        self.nav.setAccessibleName(tr("Navigation"))
        self.nav.addItems([tr(name) for name in self.destinations])
        self.nav.setSpacing(3)
        self.nav.setFixedWidth(self.nav.sizeHintForColumn(0) + 28)
        body.addWidget(self.nav)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        layouts = []
        for name in self.destinations:
            content = QWidget()
            layout = QVBoxLayout(content)
            layout.setAlignment(Qt.AlignTop)
            page = QScrollArea()
            page.setAccessibleName(tr(name))
            page.setWidgetResizable(True)
            page.setWidget(content)
            self.stack.addWidget(page)
            layouts.append(layout)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.overview(layouts[0])
        self.voices = Voices(self, layouts[1])
        self.dictation = Dictation(self, layouts[2])
        self.integrations = Integrations(self, layouts[3])
        self.shortcuts(layouts[4])
        about(self, layouts[5])
        for i in (0, 2, 3, 4, 5):
            layouts[i].addStretch()
        self.transfers = label()
        self.transfers.hide()
        outer.addWidget(self.transfers)
        self.status = QLineEdit()
        self.status.setReadOnly(True)
        self.status.setAccessibleName(tr("Operation status"))
        outer.addWidget(self.status)
        self.notice(updates.completed_update(self.path) or self.config.get('speechd_setup_warning') or tr("Ready"))
        self.nav.setCurrentRow(0)
        self.nav.setFocus()
        menu = self.menuBar().addMenu(tr("Application"))
        menu.addAction(tr("Updates…"), self.update_options)
        if updates.is_appimage():
            menu.addAction(tr("Install AppImage…"), lambda: self.offer_install(True))
        menu.addAction(tr("Close window"), self.close)
        self.summary()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(1000)
        QTimer.singleShot(0, self.poll)
        if os.name != 'nt':
            QTimer.singleShot(100, self.dictation.refresh_mics)
        if offer_install:
            QTimer.singleShot(700, self.offer_install)

    def notice(self, text):
        if self.status.text() != text:
            self.status.setText(text)
            if QAccessible.isActive() and text and text != tr("Working…"):
                QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(self.status, text))

    def error(self, error):
        self.notice(str(error))
        dialog, form = self.dialog(getattr(error, 'title', tr("Operation failed")))
        details = QPlainTextEdit(str(error))
        details.setReadOnly(True)
        form.addRow(details)
        command = getattr(error, 'command', '')
        if command:
            actions(form, ("Copy command", lambda: QApplication.clipboard().setText(command)))
        actions(form, ("Copy details", lambda: QApplication.clipboard().setText(str(error))), ("Close", dialog.accept))
        dialog.resize(580, 320)
        dialog.exec()

    def run(self, task, done=None, *, background=False, failed=None):
        if self.closed:
            return
        if not background:
            if self.busy:
                self.notice(tr("Please wait for the current operation to finish."))
                return
            self.busy = True
            self.notice(tr("Working…"))
        def work():
            try:
                value, error = task(), None
            except Exception as exc:
                value, error = None, exc
            if not self.closed:
                self.completed.emit(done, value, error, failed, background)
        threading.Thread(target=work, daemon=True).start()

    @Slot(object, object, object, object, bool)
    def finish(self, done, result, error, failed, background):
        if self.closed:
            return
        if not background:
            self.busy = False
            self.notice(tr("Ready"))
        if error:
            (failed or self.error)(error)
        elif done:
            try:
                done(result)
            except Exception as exc:
                self.error(exc)

    def dialog(self, title):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        return dialog, QFormLayout(dialog)

    def accept(self, dialog, form, button=None):
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        if button:
            box.button(QDialogButtonBox.Ok).setText(button)
            box.button(QDialogButtonBox.Cancel).setDefault(True)
        form.addRow(box)
        box.accepted.connect(dialog.accept)
        box.rejected.connect(dialog.reject)
        return dialog.exec() == QDialog.Accepted

    def confirm(self, title, text, button):
        dialog, form = self.dialog(title)
        if len(text) > 600:
            view = QPlainTextEdit(text)
            view.setReadOnly(True)
            form.addRow(view)
            dialog.resize(620, 430)
        else:
            form.addRow(label(text))
        return self.accept(dialog, form, button)

    def document(self, title, text):
        dialog, form = self.dialog(title)
        view = QPlainTextEdit(text)
        view.setAccessibleName(title)
        view.setReadOnly(True)
        form.addRow(view)
        actions(form, ("Close", dialog.accept))
        dialog.resize(620, 430)
        dialog.exec()

    def go(self, name):
        self.nav.setCurrentRow(self.destinations.index(name))
        self.nav.setFocus()

    def save(self, **changes):
        cfg = settings.load(self.path)
        cfg.update(changes)
        settings.save(self.path, cfg)
        self.config = cfg
        self.summary()
        self.notice(tr("Preferences saved."))

    def reload(self):
        self.config = settings.load(self.path)
        self.voices.reload()
        self.integrations.refresh()
        self.summary()

    def rpc(self, name, **extra):
        stop = name in ('stt-finish', 'stt-cancel', 'stt-unload', 'selection-stop')
        if name in ('stt-finish', 'stt-cancel', 'stt-unload'):
            self.input_cancel.set()
        self.run(lambda: runtime.call(self.path, dict(command=name, **extra), launch=not stop), background=stop)

    def overview(self, layout):
        form = group(layout, "Speech output")
        self.engine = label(tr("Checking speech service…"))
        self.output_config = label()
        form.addRow(self.engine)
        form.addRow(self.output_config)
        self.sample = field(form, "Sample text", QLineEdit(tr("The quick brown fox jumps over the lazy dog.")))
        self.speak, self.stop_sample, _ = actions(form, ("Speak sample", lambda: self.play(self.config['voice'])),
                ("Stop sample", lambda: self.preview_stop.set()), ("Choose a voice", lambda: self.go("Voices")))
        self.stop_sample.setEnabled(False)
        self.starter, = actions(form, ("Download starter voice (64 MB)", lambda: self.run(
            lambda: resources.download_starter(self.path), lambda _: self.reload())))
        actions(form, ("Service details…", self.service_options))
        form = group(layout, "Dictation")
        self.input_state = label(tr("Checking dictation…"))
        self.input_config = label()
        form.addRow(self.input_state)
        form.addRow(self.input_config)
        actions(form, ("Start test", self.start_test), ("Finish recording", lambda: self.rpc('stt-finish')),
                ("Configure dictation", lambda: self.go("Dictation")))
        self.test_result = field(form, "Test transcript", QPlainTextEdit())
        self.test_result.setReadOnly(True)
        self.test_result.setMaximumHeight(100)

    def start_test(self):
        if self.busy:
            return
        if not self.dictation.supported:
            self.notice(tr("Local dictation requires a recognition-enabled Linux build."))
            return
        self.input_cancel.clear()
        def start():
            current = runtime.call(self.path, {'command': 'stt-status'})
            if current['busy']:
                raise RuntimeError(tr("Finish the current recording before starting a test."))
            if not self.input_cancel.is_set():
                runtime.call(self.path, {'command': 'stt-start', 'seconds': 10})
            return current['sequence']
        def started(sequence):
            self.dictation.test_since = sequence
            self.dictation.sequence = -1
            self.test_result.clear()
        self.run(start, started)

    def summary(self):
        cfg = self.config
        voice = cfg['voices'].get(cfg['voice'])
        self.starter.setVisible(not bool(voice))
        self.speak.setEnabled(bool(voice))
        self.output_config.setText(tr("{voice} · {language} · Speed {speed}× · Volume {volume}%").format(
            voice=voice['name'], language=language_name(cfg['book_language']) if cfg['book_language'] else tr("Follow application language"),
            speed=cfg['speed'], volume=round(100*cfg['volume'])) if voice else tr("Choose or import a voice to enable speech."))
        self.input_config.setText(tr("{model} · {language} · {microphone}").format(
            model=cfg['stt_model'], language=self.dictation.lang.currentText(), microphone=self.dictation.mic.currentText()))

    def play(self, voice, sample=None):
        if self.busy:
            self.preview_stop.set()
            return
        self.preview_stop = threading.Event()
        text = self.sample.text().strip()
        if not text and not sample:
            self.notice(tr("Enter some sample text first."))
            return
        stop = self.preview_stop
        self.stop_sample.setEnabled(True)
        self.voices.preview.setText(tr("Stop sample"))
        def finished(played):
            self.voices.preview.setText(tr("Play sample"))
            self.stop_sample.setEnabled(False)
            self.notice(tr("Preview complete.") if played else tr("Preview stopped."))
        def failed(error):
            finished(False)
            self.error(error)
        self.run(lambda: voice_preview.play(self.path, text, voice, sample, stop), finished, failed=failed)

    def service_options(self):
        dialog, form = self.dialog(tr("Speech service"))
        port = number(form, "Loopback port", 1024, 65535, self.config['port'])
        idle = number(form, "Unload Piper after idle seconds (0 means never)", 0, 86400, self.config['idle_timeout'])
        form.addRow(label(tr("After changing the port, restart the service and reapply voice registration.")))
        actions(form, ("Start service", lambda: self.rpc('start')), ("Stop service", lambda: self.rpc('stop')),
                ("Open service log", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.service.log)))))
        if self.accept(dialog, form):
            self.save(port=port.value(), idle_timeout=idle.value())

    def synthesis_options(self):
        dialog, form = self.dialog(tr("Advanced synthesis"))
        noise = number(form, "Generator variation", 0., 2., self.config['noise_scale'], .05)
        width = number(form, "Phoneme variation", 0., 2., self.config['noise_w_scale'], .05)
        if self.accept(dialog, form):
            self.save(noise_scale=noise.value(), noise_w_scale=width.value())

    def shortcuts(self, layout):
        form = group(layout, "Read aloud")
        self.read_shortcuts = label()
        self.read_state = label()
        form.addRow(self.read_shortcuts)
        form.addRow(self.read_state)
        form.addRow(label(tr("Suggested keys: Ctrl+Alt+R for selected text and Ctrl+Alt+Shift+R for copied text. Confirm or change the binding in your desktop’s shortcut settings.")))
        actions(form, ("Enable reading shortcuts…", self.enable_reading), ("Disable reading shortcuts", lambda: self.rpc('selection-shortcuts-disable')))
        actions(form, ("Read selected text / Stop", lambda: self.rpc('selection-toggle')),
            ("Read copied text / Stop", lambda: self.rpc('selection-toggle', clipboard=True)), ("Stop reading", lambda: self.rpc('selection-stop')))
        from .selection import install_action
        actions(form, ("Install desktop shortcut action", lambda: self.run(lambda: install_action(self.path))))
        form = group(layout, "Desktop dictation")
        self.dict_shortcuts = label()
        form.addRow(self.dict_shortcuts)
        form.addRow(label(tr("Suggested key: Ctrl+Alt+Space. Your desktop asks for shortcut and keyboard input permission. Changing windows holds the transcript in Dictation.")))
        mode = choices(form, "Activation", [('toggle', tr("Press to start or stop")), ('push-to-talk', tr("Push to talk"))], self.config['stt_mode'])
        mode.activated.connect(lambda _: self.save(stt_mode=mode.currentData()))
        actions(form, ("Enable dictation shortcut…", lambda: self.rpc('stt-desktop-enable')),
                ("Disable dictation shortcut", lambda: self.rpc('stt-desktop-disable')))
        if 'gnome' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower():
            from .gnome_focus import install_extension
            form.addRow(label(tr("On GNOME Wayland, enable the Akousousin Focus extension so dictation can verify its destination window.")))
            actions(form, ("Set up GNOME focus support…", lambda: self.run(install_extension, self.notice)))
        if os.name == 'nt':
            for i in range(layout.count()):
                layout.itemAt(i).widget().setEnabled(False)
            layout.insertWidget(0, label(tr("Global reading and dictation shortcuts are available on Linux.")))

    def enable_reading(self):
        if self.confirm(tr("Enable reading shortcuts"), tr("Setup may select Akousousin as the Speech Dispatcher engine and briefly interrupt Orca. Continue?"), tr("Enable")):
            self.rpc('selection-shortcuts-enable')

    def poll(self):
        if self.polling or self.closed:
            return
        self.polling = True
        port = self.config['port']
        def read():
            return (self.service.health(port), runtime.call(self.path, {'command':'panel-status'}, launch=False),
                    runtime.call(self.path, {'command':'stt-status'}, launch=False), download_status.current())
        def apply(result):
            self.polling = False
            health, panel, stt, transfers = result
            current = settings.load(self.path)
            if self.config != current and not self.busy:
                self.reload()
            self.engine.setText(tr("Speech service ready") if health and health.get('ready') else tr("Speech service stopped"))
            self.dictation.update(stt or {})
            reading = (panel or {}).get('reading', {})
            self.read_shortcuts.setText(reading.get('shortcut_state', tr("Reading shortcuts disabled")))
            self.read_state.setText(reading.get('state', ''))
            self.transfers.setText('\n'.join(download_status.caption(v) for v in transfers))
            self.transfers.setVisible(bool(transfers))
            if panel and panel['activation'] != self.last_activation:
                self.last_activation = panel['activation']
                self.showNormal()
                self.raise_()
                self.activateWindow()
                if panel.get('page') == 'Updates':
                    self.update_options()
        def failed(error):
            self.polling = False
            self.engine.setText(tr("Status unavailable: {error}").format(error=error))
        self.run(read, apply, background=True, failed=failed)

    def update_options(self):
        dialog, form = self.dialog(tr("Application updates"))
        weekly = check(form, "Check weekly", self.config['update_weekly'])
        betas = check(form, "Include beta releases", self.config['update_betas'])
        def save():
            self.save(update_weekly=weekly.isChecked(), update_betas=betas.isChecked())
        weekly.clicked.connect(save)
        betas.clicked.connect(save)
        warnings = updates.registration_warnings(self.path)
        if warnings:
            form.addRow(label('\n'.join(warnings)))
        candidate = updates.available_update(self.path)
        if candidate:
            actions(form, ("Review available update…", lambda: self.confirm_update(candidate)))
        actions(form, ("Check for updates", lambda: self.run(lambda: updates.perform_check(self.path), self.confirm_update)))
        actions(form, ("Close", dialog.accept))
        dialog.exec()

    def confirm_update(self, update):
        if not update:
            self.notice(tr("No newer compatible release is available."))
            return
        if not updates.is_appimage():
            if self.confirm(tr("Update available"), tr("Open the download page for {version}?").format(version=update['version']), tr("Open download page")):
                QDesktopServices.openUrl(QUrl(updates.download_page(update)))
        elif self.confirm(tr("Install update"), tr("Install {version}? Close Wine applications first. Speech will stop and Akousousin will restart.").format(version=update['version']), tr("Install")):
            self.run(lambda: updates.install(update, self.path), lambda _: self.close())

    def offer_install(self, manual=False):
        if not updates.is_appimage() or self.busy:
            return
        if not appimage_install.needs_move():
            if manual:
                self.run(appimage_install.create_menu_entry)
            return
        target = appimage_install.recommended_path()
        replace = target.exists()
        message = tr("Move the AppImage to {path}, install its desktop entry and restart Akousousin?").format(path=target)
        if replace:
            message += ' ' + tr("This replaces the existing AppImage at that location.")
        if self.confirm(tr("Install AppImage"), message, tr("Install")):
            self.run(lambda: appimage_install.install(self.path, replace=replace), lambda _: self.close())

    def closeEvent(self, event):
        self.preview_stop.set()
        if self.busy:
            self.notice(tr("Please wait for the current operation before closing."))
            event.ignore()
            return
        self.closed = True
        self.timer.stop()
        super().closeEvent(event)
