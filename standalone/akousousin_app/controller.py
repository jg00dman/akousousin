# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Shared controller, tray and application sessions; all resources remain in the package."""
import json
import os
import subprocess
import threading
import time

import psutil

from . import resources, runtime, settings
from .service import Service


class Sessions:
    def __init__(self, path):
        self.path = path
        self.service = Service(path)
        self.owners = {}
        self.panels = []
        self.independent = False
        self.on_demand = False
        self.closed = False
        self.error = None
        self.lock = threading.RLock()
        from .dictation import Dictation
        self.input = Dictation(path, speaking=self.speaking)
        self.desktop = None
        self.input_owned = False
        self._speech_check = 0
        self._speaking = False

    def speaking(self):
        now = time.monotonic()
        if now >= self._speech_check:
            self._speech_check = now + .15
            health = self.service.health(settings.load(self.path)['port'])
            self._speaking = bool(health and health.get('speaking', False))
        return self._speaking

    def input_request(self, request):
        operation = request['command']
        if operation == 'stt-prepare':
            self.input_owned = True
            self.input.prepare()
        elif operation == 'stt-start':
            seconds = request.get('seconds')
            if seconds is not None and (isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 30):
                raise ValueError('Recording test must be 1–30 seconds')
            self.input_owned = True
            self.input.start(seconds=seconds)
        elif operation == 'stt-finish':
            if self.desktop:
                self.desktop.start_requested = False
            self.input.finish()
        elif operation == 'stt-cancel':
            if self.desktop:
                self.desktop.start_requested = False
            self.input.cancel()
        elif operation == 'stt-unload':
            if self.desktop:
                self.desktop.start_requested = False
            self.input.unload()
            self.input_owned = self.desktop is not None
        elif operation == 'stt-desktop-enable':
            if self.desktop:
                self.desktop.close()
            from .desktop_input import Desktop
            identity = runtime.name(self.path).split('/')[-1].replace('-', '_')
            self.desktop = Desktop(self.input, lambda: settings.load(self.path), runtime.directory(), identity)
            self.input.insert = self.desktop.insert
            self.input_owned = True
            self.desktop.start(listen=request.get('listen', False))
        elif operation == 'stt-toggle':
            if self.input.status()['busy']:
                self.input.finish()
            elif self.desktop and self.desktop.start_requested:
                self.desktop.close()
                self.desktop = None
            elif not self.desktop or not self.desktop.enabled:
                self.input_request({'command': 'stt-desktop-enable', 'listen': True})
            else:
                self.desktop.trigger()
        elif operation == 'stt-desktop-disable':
            if self.desktop:
                self.desktop.close()
                self.desktop = None
            self.input.insert = None
            self.input.cancel()
        elif operation != 'stt-status':
            raise ValueError('Unknown voice input command')
        result = self.input.status()
        result['desktop'] = {'enabled': bool(self.desktop and self.desktop.enabled),
                             'state': self.desktop.status if self.desktop else 'Desktop dictation is disabled'}
        return result

    def request(self, request):
        with self.lock:
            operation = request['command']
            self.panels = [panel for panel in self.panels if panel.poll() is None]
            if self.closed and operation not in ('quit', 'status', 'stt-status'):
                raise RuntimeError('Akousousin is shutting down')
            if operation.startswith('stt-'):
                return self.input_request(request)
            if operation in ('start', 'acquire', 'stop', 'wake'):
                self.error = None
            port = settings.load(self.path)['port']
            if operation == 'acquire':
                owner = psutil.Process(int(request['pid']))
                self.service.start(port)
                self.owners[request['session']] = (owner.pid, owner.create_time())
            elif operation == 'release':
                previous = self.owners.pop(request['session'], None)
                if previous and not self.owners and not self.independent and not self.on_demand and not self.input_owned and not self.panels:
                    self.quit()
            elif operation == 'wake':
                self.service.start(port)
                self.on_demand = True
            elif operation == 'start':
                self.service.start(port)
                self.independent = True
            elif operation == 'stop':
                self.service.stop(port)
            elif operation == 'quit':
                self.quit(update_pid=request.get('update_pid'))
            elif operation == 'configure':
                self.independent |= request.get('independent', False)
                self.panels = [panel for panel in self.panels if panel.poll() is None]
                self.panels.append(subprocess.Popen(runtime.command('--panel', '--settings', str(self.path)), env=runtime.environment()))
            elif operation == 'voice':
                pending = settings.select_voice(self.path, request['voice'])
                return {'pending_registration': pending}
            elif operation != 'status':
                raise ValueError('Unknown Akousousin command')
            return {'sessions': len(self.owners), 'running': bool(self.service.health(port)),
                    'independent': self.independent, 'closed': self.closed,
                    'panels': [panel.pid for panel in self.panels]}

    def reap(self):
        with self.lock:
            self.input.expire()
            dead = []
            for session, (pid, created) in self.owners.items():
                try:
                    process = psutil.Process(pid)
                    if process.create_time() != created or not process.is_running():
                        dead.append(session)
                except psutil.Error:
                    dead.append(session)
            for session in dead:
                self.request({'command': 'release', 'session': session})

    def quit(self, update_pid=None):
        import logging
        self.closed = True
        cleanup = [self.input.close]
        if self.desktop:
            desktop, self.desktop = self.desktop, None
            cleanup.append(desktop.close)
        cleanup.append(lambda: self.service.stop(settings.load(self.path)['port']))
        for action in cleanup:
            try:
                action()
            except Exception:
                logging.exception('Shutdown cleanup failed')
        for panel in self.panels:
            if panel.poll() is not None:
                continue
            # Only descendants of a panel launched by this controller are owned.
            try:
                children = psutil.Process(panel.pid).children(recursive=True)
            except psutil.Error:
                children = []
            # The updater must finish replacement before its panel exits. Only
            # that owned panel tree is detached; ordinary Quit preserves none.
            if isinstance(update_pid, int) and not isinstance(update_pid, bool) and update_pid in {panel.pid, *(child.pid for child in children)}:
                continue
            for child in children:
                try:
                    child.terminate()
                except psutil.Error:
                    pass
            panel.terminate()
            try:
                panel.wait(timeout=2)
            except subprocess.TimeoutExpired:
                panel.kill(); panel.wait(timeout=2)
            _, alive = psutil.wait_procs(children, timeout=2)
            for child in alive:
                try:
                    child.kill()
                except psutil.Error:
                    pass
            psutil.wait_procs(alive, timeout=2)
        self.panels.clear()


def run(path):
    from PySide6.QtCore import QCoreApplication, QLockFile, QObject, QTimer, Signal
    from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPen, QPixmap
    from PySide6.QtNetwork import QLocalServer
    from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon
    from shiboken6 import isValid
    graphical = os.name == 'nt' or bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
    if graphical and os.name != 'nt':
        # Install before Qt/portal startup so the desktop service can discover it
        # before the user enables shortcuts. Failures must not prevent TTS use.
        from .desktop_identity import ensure_desktop_entry
        try:
            ensure_desktop_entry()
        except (OSError, ValueError, RuntimeError):
            import logging
            logging.exception('Could not prepare desktop identity')
    app = QApplication([]) if graphical else QCoreApplication([])
    app.setApplicationName('Akousousin')
    if graphical:
        from .desktop_identity import APP_ID
        app.setDesktopFileName(APP_ID)
    if graphical:
        app.setQuitOnLastWindowClosed(False)
        app.setWindowIcon(QIcon(str(resources.root() / 'akousousin.png')))
    lock = QLockFile(str(runtime.directory() / (os.path.basename(runtime.name(path)) + '.lock')))
    if not lock.tryLock(10000):
        return
    QLocalServer.removeServer(runtime.name(path))
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)
    if not server.listen(runtime.name(path)):
        raise RuntimeError(server.errorString())
    state = Sessions(path)

    class Events(QObject):
        result = Signal(object, object)
    events = Events()
    connections = set()

    def finish(socket, response):
        if socket and isValid(socket):
            socket.write(json.dumps(response).encode() + b'\n')
            socket.flush()
            socket.disconnectFromServer()
            connections.discard(socket)
        elif 'error' in response and graphical:
            QMessageBox.warning(None, 'Akousousin', response['error'])
        elif response.get('pending_registration') and graphical:
            QMessageBox.information(None, 'Akousousin', 'Default saved. Apply voice registration in Configure → Settings.')
        if state.closed:
            # Reject new clients immediately, before potentially slow backend
            # cleanup. A restarting caller must connect to a fresh controller.
            server.close()
            QTimer.singleShot(250, app.quit)

    events.result.connect(finish)

    def submit(request, socket=None):
        def work():
            try:
                result = state.request(request)
            except Exception as error:
                state.error = str(error)
                result = {'error': str(error)}
            events.result.emit(socket, result)
        threading.Thread(target=work, daemon=True).start()

    def accept():
        socket = server.nextPendingConnection()
        connections.add(socket)
        socket.disconnected.connect(lambda: connections.discard(socket))
        socket.disconnected.connect(socket.deleteLater)
        buffer = bytearray()
        def read():
            buffer.extend(bytes(socket.readAll()))
            if len(buffer) > 8192:
                socket.abort()
                connections.discard(socket)
            elif b'\n' in buffer:
                socket.readyRead.disconnect(read)
                try:
                    submit(json.loads(buffer.split(b'\n', 1)[0]), socket)
                except ValueError:
                    finish(socket, {'error': 'Invalid request'})
        socket.readyRead.connect(read)
        read()
    server.newConnection.connect(accept)
    tray = QSystemTrayIcon() if graphical else None
    if tray:
        tray.setToolTip('Akousousin — Neural Voice Engine')
        tray.setIcon(QIcon(str(resources.root() / 'akousousin.png')))
        menu = QMenu()
        toggle = menu.addAction('Start Speech')
        toggle.triggered.connect(lambda: submit({'command': 'stop' if toggle.text() == 'Stop Speech' else 'start'}))
        dictation_toggle = menu.addAction('Start Dictation')
        dictation_toggle.triggered.connect(lambda: submit({'command': 'stt-toggle'}))
        voices = menu.addMenu('Default Voice')
        def populate():
            voices.clear()
            config = settings.load(path)
            from .languages import label
            groups = {}
            for identifier, voice in sorted(config['voices'].items(), key=lambda item: (label(item[1]['language']), item[1]['name'])):
                group = groups.setdefault(voice['language'], None)
                if group is None:
                    group = groups[voice['language']] = voices.addMenu(label(voice['language']))
                action = group.addAction(voice['name'])
                action.setCheckable(True)
                action.setChecked(identifier == config['voice'])
                action.triggered.connect(lambda checked=False, key=identifier: submit({'command': 'voice', 'voice': key}))
        voices.aboutToShow.connect(populate)
        menu.addAction('Configure', lambda: submit({'command': 'configure'}))
        def quit_requested():
            if (state.owners or state.service.health(settings.load(path)['port'])) and QMessageBox.question(None, 'Quit Akousousin?',
                    'Speech is in use. Quit and stop Piper, interrupting speech?') != QMessageBox.Yes:
                return
            submit({'command': 'quit'})
        menu.addAction('Quit', quit_requested)
        tray.setContextMenu(menu)
        def activate_tray(reason):
            if reason == QSystemTrayIcon.Trigger:
                menu.popup(QCursor.pos())
            elif reason == QSystemTrayIcon.DoubleClick:
                submit({'command': 'configure'})
        tray.activated.connect(activate_tray)
        tray.show()

    def tick():
        # Reaping can stop inference, so never run it in Qt's GUI thread.
        if not getattr(tick, 'busy', False):
            tick.busy = True
            def reap():
                try:
                    state.reap()
                finally:
                    tick.busy = False
            threading.Thread(target=reap, daemon=True).start()
        if state.closed and not connections:
            QTimer.singleShot(500, app.quit)
        if tray:
            config = settings.load(path)
            health = state.service.health(config['port'])
            running = bool(health and health.get('ready'))
            status = 'Idle' if running and health.get('model_loaded') is False else 'Running' if running else 'Stopped'
            if state.service.process is not None and state.service.process.poll() is None and not running:
                status = 'Starting'
            if state.service.process is not None and state.service.process.poll() not in (None, 0) and not running:
                status = 'Error'
            if state.error and not running:
                status = 'Error'
            input_status = state.input.status()
            color = {'Idle': '#737b80', 'Running': '#20a45b', 'Stopped': '#737b80', 'Starting': '#e3aa26', 'Error': '#bd3838'}[status]
            if input_status['busy']:
                color = '#e3aa26' if input_status['phase'] in ('loading', 'opening') or input_status['state'].startswith('Paused') else '#d94747' if input_status['phase'] == 'listening' else '#327bd2'
            pixmap = QPixmap(str(resources.root() / 'akousousin.png')).scaled(64, 64)
            painter = QPainter(pixmap)
            painter.setBrush(QColor(color))
            painter.setPen(QPen(QColor('white'), 3))
            painter.drawEllipse(44, 44, 18, 18)
            painter.end()
            tray.setIcon(QIcon(pixmap))
            tray.setToolTip('Akousousin · ' + status + '\nVoice input: ' + input_status['state'])
            pending_input = bool(state.desktop and state.desktop.start_requested)
            dictation_toggle.setText('Stop Dictation' if input_status['busy'] or pending_input else 'Start Dictation')
            toggle.setText('Stop Speech' if running else 'Start Speech')
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(1500)
    tick()
    try:
        app.exec()
    finally:
        # Stop accepting clients before waiting for backend process cleanup.
        server.close()
        state.quit()
        lock.unlock()
