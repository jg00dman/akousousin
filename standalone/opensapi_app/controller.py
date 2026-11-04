"""Shared controller, tray and application sessions; all resources remain in the package."""
import json
import os
import subprocess
import threading

import psutil

from . import resources, runtime, settings
from .service import Service


class Sessions:
    def __init__(self, path):
        self.path = path
        self.service = Service(path)
        self.owners = {}
        self.independent = False
        self.closed = False
        self.error = None
        self.lock = threading.RLock()

    def request(self, request):
        with self.lock:
            operation = request['command']
            if operation in ('start', 'acquire', 'stop'):
                self.error = None
            port = settings.load(self.path)['port']
            if operation == 'acquire':
                owner = psutil.Process(int(request['pid']))
                self.service.start(port)
                self.owners[request['session']] = (owner.pid, owner.create_time())
            elif operation == 'release':
                previous = self.owners.pop(request['session'], None)
                if previous and not self.owners and not self.independent:
                    self.quit()
            elif operation == 'start':
                self.service.start(port)
                self.independent = True
            elif operation == 'stop':
                self.service.stop(port)
            elif operation == 'quit':
                self.quit()
            elif operation == 'configure':
                self.independent |= request.get('independent', False)
                subprocess.Popen(runtime.command('--panel', '--settings', str(self.path)), env=runtime.environment())
            elif operation == 'voice':
                pending = settings.select_voice(self.path, request['voice'])
                return {'pending_registration': pending}
            elif operation != 'status':
                raise ValueError('Unknown OpenSAPI command')
            return {'sessions': len(self.owners), 'running': bool(self.service.health(port)),
                    'independent': self.independent, 'closed': self.closed}

    def reap(self):
        with self.lock:
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

    def quit(self):
        self.service.stop(settings.load(self.path)['port'])
        self.closed = True


def run(path):
    from PySide6.QtCore import QCoreApplication, QLockFile, QObject, QTimer, Signal
    from PySide6.QtNetwork import QLocalServer
    from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon, QMenu
    from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
    graphical = os.name == 'nt' or bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
    app = QApplication([]) if graphical else QCoreApplication([])
    if graphical:
        app.setQuitOnLastWindowClosed(False)
        app.setWindowIcon(QIcon(str(resources.root() / 'opensapi.png')))
    lock = QLockFile(str(runtime.directory() / (os.path.basename(runtime.name(path)) + '.lock')))
    if not lock.tryLock(0):
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
        if socket:
            socket.write(json.dumps(response).encode() + b'\n')
            socket.flush()
            socket.disconnectFromServer()
            connections.discard(socket)
        elif 'error' in response and graphical:
            QMessageBox.warning(None, 'OpenSAPI', response['error'])
        elif response.get('pending_registration') and graphical:
            QMessageBox.information(None, 'OpenSAPI', 'Default saved. Apply voice registration in Configure → Settings.')
        if state.closed:
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
        tray.setToolTip('OpenSAPI')
        tray.setIcon(QIcon(str(resources.root() / 'opensapi.png')))
        menu = QMenu()
        toggle = menu.addAction('Start')
        toggle.triggered.connect(lambda: submit({'command': 'stop' if toggle.text() == 'Stop' else 'start'}))
        voices = menu.addMenu('Default voice')
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
        menu.addAction('Configure…', lambda: submit({'command': 'configure', 'independent': True}))
        def quit_requested():
            if state.owners and QMessageBox.question(None, 'Quit OpenSAPI?',
                    'Speech is in use. Quit and stop Piper, interrupting speech?') != QMessageBox.Yes:
                return
            submit({'command': 'quit'})
        menu.addAction('Quit', quit_requested)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason: submit({'command': 'configure', 'independent': True})
                               if reason == QSystemTrayIcon.DoubleClick else None)
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
            status = 'Running' if running else 'Stopped'
            if state.service.process is not None and state.service.process.poll() is None and not running:
                status = 'Starting'
            if state.service.process is not None and state.service.process.poll() not in (None, 0) and not running:
                status = 'Error'
            if state.error and not running:
                status = 'Error'
            pixmap = QPixmap(str(resources.root() / 'opensapi.png')).scaled(64, 64)
            painter = QPainter(pixmap)
            painter.setBrush(QColor({'Running': '#20a45b', 'Stopped': '#737b80', 'Starting': '#e3aa26', 'Error': '#bd3838'}[status]))
            painter.setPen(QPen(QColor('white'), 3))
            painter.drawEllipse(44, 44, 18, 18)
            painter.end()
            tray.setIcon(QIcon(pixmap))
            tray.setToolTip('OpenSAPI — ' + status)
            toggle.setText('Stop' if running else 'Start')
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(1500)
    tick()
    try:
        app.exec()
    finally:
        state.quit()
        server.close()
        lock.unlock()
