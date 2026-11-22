# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Advanced: settings most people never need to change."""
import os
import subprocess
import time

from PySide6.QtCore import QDateTime, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QCheckBox, QSpinBox

from ... import __version__, appimage_install, diagnostics, runtime, settings, updates
from ..flow import Columns
from ..lang import number
from ..widgets import Card, SettingRow, StatusLine, ValueSlider, button, combo, fill, row, spread, text
from .base import Page

DEFAULT_NOISE, DEFAULT_WIDTH = settings.DEFAULTS['noise_scale'], settings.DEFAULTS['noise_w_scale']


class AdvancedPage(Page):
    key = 'advanced'
    icon = 'sliders'

    def title(self):
        return self.tr('Advanced')

    def subtitle(self):
        return self.tr('Settings most people never need to change.')

    def build(self):
        config = self.state.config

        service = Card(self.tr('Speech service'))
        self.service_status = StatusLine()
        restart = button(self.tr('Restart'), self.restart)
        service.add(SettingRow(self.tr('Status'), self.tr('Starts by itself when an app needs speech.'),
                               self.service_status, restart, first=True))
        self.idle = combo(self.idle_choices(), config['idle_timeout'])
        self.idle.activated.connect(lambda _: self.state.save(idle_timeout=self.idle.currentData()))
        service.add(SettingRow(self.tr('Free memory when idle'),
                               self.tr('Voices are unloaded after this long without speech and reload in about a second.'), self.idle))
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(config['port'])
        self.port.editingFinished.connect(self.save_port)
        service.add(SettingRow(self.tr('Local port'),
                               self.tr('Used only inside this computer. Change it if another program uses %1.').replace('%1', str(config['port'])),
                               self.port))

        dictation = Card(self.tr('Dictation performance'))
        self.threads = combo()
        self.threads.activated.connect(lambda _: self.state.save(stt_cpu_threads=self.threads.currentData()))
        dictation.add(SettingRow(self.tr('Processor threads'),
                                 self.tr('More threads can be faster but leave less for other apps.'), self.threads, first=True))
        self.memory = combo()
        self.memory.activated.connect(lambda _: self.save_memory())
        dictation.add(SettingRow(self.tr('Free memory when idle'),
                                 self.tr('The dictation model is unloaded after this long without use.'), self.memory))

        self.updates = Card(self.tr('Updates'))
        self.version = text('', 'h3')
        self.checked = text('', 'muted')
        self.check_now = button(self.tr('Check now'), self.check)
        self.install_update = button(self.tr('Get the update…'), self.install, kind='primary')
        self.updates.add(spread(self._stack(self.version, self.checked), self.check_now, self.install_update))
        self.betas = QCheckBox(self.tr('Beta releases'))
        self.betas.toggled.connect(lambda on: self.state.save(update_betas=on))
        self.updates.add(SettingRow(self.tr('Include test versions'),
                                    self.tr('Get new features earlier. They may have more problems.'), self.betas))
        self.move_image = button(self.tr('Install the AppImage…'), lambda: self.offer_install(True))
        self.updates.add(row(self.move_image))

        voice = Card(self.tr('Voice character'))
        self.expressive = ValueSlider(self.tr('Expressiveness'), 0, 2, .05, config['noise_scale'], lambda v: number(v, 2))
        self.expressive.committed.connect(lambda v: self.state.save(noise_scale=v))
        self.rhythm = ValueSlider(self.tr('Rhythm'), 0, 2, .05, config['noise_w_scale'], lambda v: number(v, 2))
        self.rhythm.committed.connect(lambda v: self.state.save(noise_w_scale=v))
        voice.add(text(self.tr('How much the voice varies its tone and timing. Lower sounds flatter and steadier.'), 'muted'))
        voice.add(self.expressive)
        voice.add(self.rhythm)
        voice.add(row(button(self.tr('Restore defaults'), self.restore_voice)))

        trouble = Card(self.tr('Troubleshooting'))
        trouble.add(row(button(self.tr('Open service log'), self.open_log), button(self.tr('Copy diagnostic report'), self.copy_report)))
        trouble.add(text(self.tr('The report contains versions, settings and recent errors — no text you have read or dictated.'), 'muted'))
        trouble.add(SettingRow(self.tr('Remove Akousousin completely'),
                               self.tr('Deletes voices, models and settings, and unregisters it from every app.'),
                               button(self.tr('Remove everything…'), self.purge, kind='danger')))

        self.add(Columns([[service, dictation, self.updates], [voice, trouble]], minimum=440))
        self.settings_changed(config)
        self.status_changed(self.state.status)

    @staticmethod
    def _stack(*widgets):
        from PySide6.QtWidgets import QVBoxLayout, QWidget
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        for widget in widgets:
            layout.addWidget(widget)
        return box

    def idle_choices(self):
        return [(0, self.tr('Never')), (60, self.tr('After 1 minute')), (300, self.tr('After 5 minutes')),
                (900, self.tr('After 15 minutes')), (1800, self.tr('After 30 minutes')), (3600, self.tr('After 1 hour'))]

    def settings_changed(self, config):
        fill(self.idle, self.idle_choices(), config['idle_timeout'])
        from akousousin_backend.recognition_config import cpu_threads
        automatic = cpu_threads()
        fill(self.threads, [(automatic, self.tr('Automatic (%1)').replace('%1', str(automatic))),
                            *((n, str(n)) for n in range(1, max(os.cpu_count() or 1, automatic) + 1) if n != automatic)],
             config['stt_cpu_threads'])
        memory = 'never' if config['stt_keep_loaded'] else config['stt_idle_timeout']
        fill(self.memory, [('never', self.tr('Never')), (900, self.tr('After 15 minutes')),
                           (3600, self.tr('After 1 hour')), (14400, self.tr('After 4 hours'))], memory)
        self.betas.blockSignals(True)
        self.betas.setChecked(config['update_betas'])
        self.betas.blockSignals(False)
        self.expressive.set(config['noise_scale'])
        self.rhythm.set(config['noise_w_scale'])
        self.refresh_updates()

    def status_changed(self, status):
        if status.speech_ready:
            loaded = status.speech.get('model_loaded', True)
            self.service_status.set(self.tr('Running') if loaded else self.tr('Running · voices unloaded to save memory'), 'ok')
        else:
            self.service_status.set(self.tr('Not running — starts when needed'), 'off')

    def refresh_updates(self):
        self.version.setText(self.tr('Akousousin %1').replace('%1', __version__))
        state = updates.update_state(self.state.path)
        checked = state.get('checked_at')
        kind = self.tr('AppImage') if updates.is_appimage() else self.tr('Installed package')
        if checked:
            when = QDateTime.fromSecsSinceEpoch(int(checked)).toString('d MMM yyyy')
            self.checked.setText(self.tr('%1 · Last checked %2').replace('%1', kind).replace('%2', when))
        else:
            self.checked.setText(kind)
        candidate = updates.available_update(self.state.path)
        self.install_update.setVisible(bool(candidate))
        if candidate:
            self.install_update.setText(self.tr('Get %1…').replace('%1', candidate['version']))
        self.move_image.setVisible(appimage_install.needs_move() if updates.is_appimage() else False)

    # Actions ----------------------------------------------------------------
    def restart(self):
        def work():
            self.state.call('stop', launch=False)
            time.sleep(.3)
            return self.state.call('start')
        self.run(work, lambda _: self.notice(self.tr('Speech service restarted.')), key='service')

    def save_port(self):
        if self.port.value() != self.state.config['port']:
            self.state.save(port=self.port.value())
            self.notice(self.tr('Port saved. Restart the service, then update registrations in Apps.'))

    def save_memory(self):
        value = self.memory.currentData()
        if value == 'never':
            self.state.save(stt_keep_loaded=True)
        else:
            self.state.save(stt_keep_loaded=False, stt_idle_timeout=value)

    def restore_voice(self):
        self.state.save(noise_scale=DEFAULT_NOISE, noise_w_scale=DEFAULT_WIDTH)

    def check(self):
        def done(candidate):
            self.refresh_updates()
            self.notice(self.tr('Akousousin %1 is available.').replace('%1', candidate['version']) if candidate
                        else self.tr('You have the latest version.'))
        self.run(lambda: updates.perform_check(self.state.path), done, key='updates', busy=self.tr('Checking for updates…'))

    def install(self):
        candidate = updates.available_update(self.state.path)
        if not candidate:
            return
        if not updates.is_appimage():
            if self.confirm(self.tr('Update available'),
                            self.tr('Open the download page for %1?').replace('%1', candidate['version']), self.tr('Open page')):
                QDesktopServices.openUrl(QUrl(updates.download_page(candidate)))
            return
        if self.confirm(self.tr('Install update'),
                        self.tr('Install %1? Close Windows apps that are speaking first. Akousousin restarts afterwards.').replace('%1', candidate['version']),
                        self.tr('Install')):
            self.run(lambda: updates.install(candidate, self.state.path), lambda _: self.window().close(),
                     key='updates', busy=self.tr('Installing the update…'))

    def offer_install(self, manual=False):
        if not updates.is_appimage():
            return
        if not appimage_install.needs_move():
            if manual:
                self.run(appimage_install.create_menu_entry, key='appimage')
            return
        target = appimage_install.recommended_path()
        replace = target.exists()
        message = self.tr('Move the AppImage to %1, add it to the application menu and restart Akousousin?').replace('%1', str(target))
        if replace:
            message += ' ' + self.tr('This replaces the AppImage already there.')
        if self.confirm(self.tr('Install the AppImage'), message, self.tr('Install')):
            self.run(lambda: appimage_install.install(self.state.path, replace=replace), lambda _: self.window().close(), key='appimage')

    def open_log(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.state.service.log)))

    def copy_report(self):
        QApplication.clipboard().setText(diagnostics.report(self.state.path, self.state.status))
        self.notice(self.tr('Diagnostic report copied. Paste it into your bug report.'))

    def purge(self):
        from ... import purge
        if not self.confirm(self.tr('Remove Akousousin completely'),
                            self.tr('This cannot be undone.'), self.tr('Remove everything'), details=purge.WARNING):
            return

        def work():
            return subprocess.run(runtime.command('--purge', '--yes', '--settings', str(self.state.path)),
                                  env=runtime.environment(), capture_output=True, text=True, timeout=300)

        def done(result):
            if result.returncode:
                self.error(RuntimeError((result.stdout + result.stderr).strip() or self.tr('Some parts could not be removed.')))
            else:
                self.notice(self.tr('Akousousin was removed.'))
                self.window().close()

        self.run(work, done, key='purge', busy=self.tr('Removing Akousousin…'))
