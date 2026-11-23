# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Shared controller, tray and application sessions; all resources remain in the package."""
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import psutil

from . import resources, runtime, settings
from .service import Service


class Sessions:
    def __init__(self, path):
        from .desktop_preferences import DesktopPreferences
        self.desktop_preferences = DesktopPreferences(path)
        self.path = path
        self.service = Service(path)
        self.owners = {}
        self.panels = []
        self.panel_activation = 0
        self.panel_page = None
        self.independent = False
        self.on_demand = False
        self.closed = False
        self.error = None
        self.lock = threading.RLock()
        from .dictation import Dictation
        self.input = Dictation(path, speaking=self.speaking)
        from .selection_controller import Selection
        self.selection = Selection(path)
        self.desktop = None
        self.input_owned = False
        self._speech_check = 0
        self._speaking = False
        self.reading_setup = threading.Lock()
        self.generation = 0  # counts changes, so control panels can wait for the next one
        self.changes = threading.Condition()
        self.login_session = None  # the desktop login this controller serves, when known

    def bump(self):
        """Something a control panel shows may have changed; wake panels waiting for it."""
        with self.changes:
            self.generation += 1
            self.changes.notify_all()

    def wait_for_change(self, after, timeout):
        with self.changes:
            self.changes.wait_for(lambda: self.closed or after is None or self.generation != after, timeout)
            return {'generation': self.generation}

    def restore_desktop_shortcuts(self):
        """Restore opted-in sessions, never start microphone capture on launch.

        Each command takes the controller lock only for as long as it needs
        it; holding it across both would stall the tray and every request.
        """
        try:
            saved = self.desktop_preferences.load()
        except Exception as error:
            self.error = 'Could not restore desktop shortcuts: ' + str(error)
            return
        for key, command in (('dictation_enabled', 'stt-desktop-enable'),
                             ('reading_enabled', 'selection-shortcuts-enable')):
            if saved[key] and not self.closed:
                try:
                    self.request({'command': command})
                except Exception as error:
                    self.error = 'Could not restore desktop shortcuts: ' + str(error)

    def get_ready(self):
        """Load the voice and the dictation model now, if the user wants them ready.

        Runs once when the controller starts, off the GUI thread. Nothing is
        downloaded here, and a missing voice or model is simply skipped: the
        app is then ready as soon as the user has chosen one.
        """
        config = settings.load(self.path)
        if not config.get('preload', True) or self.closed:
            return
        voice = config['voices'].get(config['voice'])
        if voice and Path(voice['path']).is_file():
            # Same lock as 'acquire', so an app starting speech now cannot launch a second service.
            with self.lock:
                try:
                    if not self.closed:
                        self.service.start(config['port'])
                except Exception as error:
                    self.error = 'Could not load the voice: ' + str(error)
        if os.name == 'nt' or self.closed:
            return  # dictation is Linux-only for now
        from akousousin_backend import models
        model = config['stt_model']
        from .resources import bundled_dictation_model
        bundled = bundled_dictation_model()
        if models.installed(model) or (model == 'turbo' and models.installed('small')) or (bundled and bundled.name == model):
            try:
                self.input.prepare()
            except BlockingIOError:
                pass  # the user is already dictating, which loads it anyway
            except Exception as error:
                self.error = 'Could not load dictation: ' + str(error)

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
            self.input.prepare(download=request.get('download') is True)
        elif operation == 'stt-start':
            seconds = request.get('seconds')
            if seconds is not None and (isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 30):
                raise ValueError('Recording test must be 1–30 seconds')
            self.input_owned = True
            self.input.start(seconds=seconds)
        elif operation == 'stt-finish':
            if self.desktop:
                self.desktop.start_requested = False
            self.input.finish(cancel_insertion=True)
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
            self.desktop = Desktop(self.input, lambda: settings.load(self.path), runtime.directory(), identity, preferences=self.desktop_preferences)
            self.input.insert = self.desktop.insert
            self.input_owned = True
            self.desktop.start(listen=request.get('listen', False))
        elif operation == 'stt-toggle':
            if self.input.status()['busy']:
                self.input.finish(cancel_insertion=True)
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
            self.desktop_preferences.update(dictation_enabled=False, restore_token='')
            self.input.insert = None
            self.input.cancel()
        elif operation != 'stt-status':
            raise ValueError('Unknown voice input command')
        result = self.input.status()
        result['desktop'] = {'enabled': bool(self.desktop and self.desktop.enabled),
                             'state': self.desktop.status if self.desktop else 'Desktop dictation is disabled',
                             'keys': getattr(self.desktop, 'shortcut_description', '') if self.desktop and self.desktop.enabled else ''}
        return result

    def request(self, request):
        if request.get('command') == 'wait':
            after, timeout = request.get('after'), request.get('timeout', 25)
            if (after is not None and (isinstance(after, bool) or not isinstance(after, int))) or \
                    isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 <= timeout <= 60:
                raise ValueError('Invalid wait')
            return self.wait_for_change(after, timeout)
        if request.get('command') == 'selection-shortcuts-enable' and os.name != 'nt':
            # Checking Speech Dispatcher (and restarting it if it lacks our
            # module) can take many seconds and touches no controller state,
            # so it runs outside the lock the tray and other requests wait on.
            if self.closed:
                raise RuntimeError('Akousousin is shutting down')
            with self.reading_setup:
                self.selection.enable()
            return self.selection.status()
        with self.lock:
            operation = request['command']
            self.panels = [panel for panel in self.panels if panel.poll() is None]
            if self.closed and operation not in ('quit', 'status', 'stt-status'):
                raise RuntimeError('Akousousin is shutting down')
            if operation.startswith('stt-'):
                return self.input_request(request)
            if operation.startswith('selection-'):
                if os.name == 'nt':
                    raise RuntimeError('Selection reading is currently for Linux desktops')
                if operation == 'selection-toggle':
                    clipboard = request.get('clipboard', False)
                    if not isinstance(clipboard, bool):
                        raise ValueError('Invalid clipboard selection')
                    self.selection.toggle(clipboard)
                elif operation == 'selection-stop':
                    self.selection.stop()
                elif operation == 'selection-shortcuts-enable':
                    self.selection.enable()
                elif operation == 'selection-shortcuts-disable':
                    self.selection.disable()
                    self.desktop_preferences.update(reading_enabled=False)
                elif operation != 'selection-status':
                    raise ValueError('Unknown reading command')
                return self.selection.status()
            if operation == 'panel-status':
                return {'activation': self.panel_activation, 'page': self.panel_page, 'reading': self.selection.status()}
            if operation in ('start', 'acquire', 'stop', 'wake'):
                self.error = None
            port = settings.load(self.path)['port']
            if operation == 'acquire':
                owner = psutil.Process(int(request['pid']))
                self.service.start(port)
                self.owners[request['session']] = (owner.pid, owner.create_time())
            elif operation == 'release':
                previous = self.owners.pop(request['session'], None)
                if previous and not self.owners and not self.independent and not self.on_demand and not self.input_owned and not self.panels and not self.selection.shortcuts and not self.selection.status()['reading']:
                    self.quit()
            elif operation == 'wake':
                self.service.start(port)
                self.on_demand = True
            elif operation == 'activity':
                pass  # the voice service started speaking; the reply refreshes the tray
            elif operation == 'background':
                # Started at login: stay running in the tray with no window.
                self.independent = True
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
                self.panel_page = 'Updates' if request.get('page') == 'Updates' else None
                self.panel_activation += 1
                if not self.panels:
                    self.panels.append(subprocess.Popen(runtime.command('--panel', '--settings', str(self.path)), env=runtime.environment()))
            elif operation in ('voice', 'language-voice'):
                pending = settings.select_voice(self.path, request['voice'], language_only=operation == 'language-voice')
                return {'pending_registration': pending}
            elif operation != 'status':
                raise ValueError('Unknown Akousousin command')
            return {'sessions': len(self.owners), 'running': bool(self.service.health(port)),
                    'login_session': self.login_session,
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
        self.bump()  # release control panels waiting for a change
        cleanup = [self.selection.close, self.input.close]
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
    from PySide6.QtCore import QCoreApplication, QLockFile, QObject, QTimer, Signal, Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtNetwork import QLocalServer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from shiboken6 import isValid
    graphical = os.name == 'nt' or bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
    if graphical and os.name != 'nt':
        # Install before Qt/portal startup so the desktop service can discover it
        # before the user enables shortcuts. Failures must not prevent TTS use.
        from .desktop_identity import ensure_desktop_entry
        try:
            ensure_desktop_entry()
            from .appimage_install import needs_move, create_menu_entry
            from .updates import is_appimage
            if is_appimage() and not needs_move():
                create_menu_entry()
            from .selection_shortcuts import ReadingShortcuts
            ensure_desktop_entry(app_id=ReadingShortcuts.app_id, name=ReadingShortcuts.desktop_name)
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
        from .qt_locale import install_link_handler
        install_link_handler(app)
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
    from . import updates
    update_monitor = updates.UpdateMonitor(path)
    update_dialog = None

    class Events(QObject):
        result = Signal(object, object)
        changed = Signal()  # something the tray shows may have changed
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
            QMessageBox.information(None, 'Akousousin', 'Default voice saved. Restart Windows apps so they use it.')
        if state.closed:
            # Reject new clients immediately, before potentially slow backend
            # cleanup. A restarting caller must connect to a fresh controller.
            server.close()
            QTimer.singleShot(250, app.quit)

    events.result.connect(finish)

    # Questions about state, which change nothing the tray or a panel shows.
    read_only = {'wait', 'status', 'panel-status', 'stt-status', 'selection-status'}

    def submit(request, socket=None):
        def work():
            try:
                result = state.request(request)
            except Exception as error:
                state.error = str(error)
                result = {'error': str(error)}
            if request.get('command') not in read_only:
                events.changed.emit()  # it may have changed what the tray and panels show
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
    tray_watcher = None
    if graphical and os.name != 'nt':
        # Qt picks its tray backend when the icon is created. If the desktop's
        # D-Bus tray is still starting (as at login), X11 falls back to an
        # XEmbed icon that never moves to StatusNotifier, and Wayland, which
        # has no fallback, shows nothing at all. Recreate it once the tray is up.
        from PySide6.QtDBus import QDBusConnection, QDBusServiceWatcher
        bus = QDBusConnection.sessionBus()
        watcher_name = 'org.kde.StatusNotifierWatcher'
        if bus.isConnected():
            tray_watcher = QDBusServiceWatcher(watcher_name, bus, QDBusServiceWatcher.WatchForRegistration, app)
            if bus.interface().isServiceRegistered(watcher_name).value():
                tray_watcher.deleteLater()
                tray_watcher = None
    tray = None
    if graphical:
        from .qt_locale import install_translators
        from .ui.tray import Tray
        install_translators(app)

        def in_use():
            return bool(state.owners or state.service.health(settings.load(path)['port']))
        tray = Tray(path, submit, in_use)
        if tray_watcher is not None:
            def attach_to_desktop(_service):
                tray.create()
                # Qt now owns the D-Bus icon and handles subsequent restarts.
                tray_watcher.deleteLater()
            tray_watcher.serviceRegistered.connect(attach_to_desktop)

    def notify_update(candidate):
        nonlocal update_dialog
        if update_dialog is not None:
            return
        box = QMessageBox()
        box.setWindowModality(Qt.NonModal)
        box.setAttribute(Qt.WA_ShowWithoutActivating)
        box.setWindowTitle('Akousousin update available')
        box.setText('Akousousin ' + candidate['version'] + ' is available.')
        box.setInformativeText('Open Updates to review and install it when you are ready.' if updates.is_appimage()
                               else 'Open the release download page, or update through your package manager.')
        now = box.addButton('Update now…' if updates.is_appimage() else 'Open download page…', QMessageBox.AcceptRole)
        later = box.addButton('Remind me later', QMessageBox.RejectRole)
        box.setDefaultButton(later)
        def finished(_):
            nonlocal update_dialog
            updates.remind_later(path)
            if box.clickedButton() == now:
                if updates.is_appimage():
                    submit({'command': 'configure', 'page': 'Updates'})
                else:
                    runtime.open_external(updates.download_page(candidate))
            update_dialog = None
        box.finished.connect(finished)
        update_dialog = box
        box.show()  # Nonmodal: notifications must not block controller requests.

    # The tray is refreshed when something tells it of a change: a request,
    # dictation or reading changing state, the voice service starting to
    # speak, a download, a settings or update file, or the desktop's colours.
    # Only while something is in progress does it also refresh on a timer, to
    # follow it to the end. Idle, the controller sleeps.
    from PySide6.QtCore import QFileSystemWatcher, QSocketNotifier
    from .download_status import current as current_downloads
    from akousousin_backend.downloads import directory as downloads_directory
    refresh_pending = False
    owner_watches = {}  # session -> (notifier, pidfd)
    watched_service = None
    reaping = threading.Lock()

    def changed():
        nonlocal refresh_pending
        if not refresh_pending:
            refresh_pending = True
            QTimer.singleShot(50, refresh)  # one refresh for a burst of changes
    events.changed.connect(changed)

    def poke():  # from any thread
        events.changed.emit()
    state.input.on_change = poke
    state.selection.on_change = poke

    def reap():
        # Reaping can stop inference, so never run it in Qt's GUI thread.
        if reaping.acquire(False):
            def work():
                try:
                    state.reap()
                finally:
                    reaping.release()
                    poke()
            threading.Thread(target=work, daemon=True).start()

    def watch_owners():
        """Be told when an app using the voice exits; returns False where the kernel can't tell us."""
        if not hasattr(os, 'pidfd_open'):
            return False
        with state.lock:
            owners = dict(state.owners)
        for session in [session for session in owner_watches if session not in owners]:
            notifier, descriptor = owner_watches.pop(session)
            notifier.setEnabled(False)
            notifier.deleteLater()
            os.close(descriptor)
        added = False
        for session, (pid, _created) in owners.items():
            if session in owner_watches:
                continue
            try:
                descriptor = os.pidfd_open(pid)
            except OSError:
                reap()  # already gone
                continue
            notifier = QSocketNotifier(descriptor, QSocketNotifier.Read)
            def exited(*_, notifier=notifier):
                notifier.setEnabled(False)  # stays readable once the process has exited
                reap()
            notifier.activated.connect(exited)
            owner_watches[session] = (notifier, descriptor)
            added = True
        if added:
            reap()  # a reused process ID is caught by the start-time check
        return True

    def watch_service():
        nonlocal watched_service
        process = state.service.process
        if process is not None and process is not watched_service:
            watched_service = process
            threading.Thread(target=lambda: (process.wait(), poke()), daemon=True).start()

    unload_timer = QTimer()
    unload_timer.setSingleShot(True)
    unload_timer.timeout.connect(reap)  # reaping unloads an idle dictation model

    def schedule_unload():
        due = state.input.until_expiry()
        if due is None:
            unload_timer.stop()
        else:
            unload_timer.start(int(due * 1000) + 100)

    def refresh():
        nonlocal refresh_pending
        refresh_pending = False
        state.bump()
        if state.closed and not connections:
            QTimer.singleShot(500, app.quit)
        watching_owners = watch_owners()
        watch_service()
        schedule_unload()
        active = bool(state.owners) and not watching_owners
        if active:
            reap()
        if tray:
            config = settings.load(path)
            health = state.service.health(config['port'])
            running = bool(health and health.get('ready'))
            process = state.service.process
            failed = process is not None and process.poll() not in (None, 0) and not running
            starting = process is not None and process.poll() is None and not running
            input_status = state.input.status()
            reading = state.selection.status()
            speaking = bool(health and health.get('speaking'))
            candidate = update_monitor.tick(quiet=bool(input_status['busy'] or speaking or reading.get('reading')))
            if candidate:
                notify_update(candidate)
            downloads = current_downloads()
            pending = bool(state.desktop and state.desktop.start_requested)
            tray.update(running=running, dictation=input_status, reading=reading,
                        pending=pending, downloads=downloads,
                        available=updates.available_update(path),
                        problem=bool((state.error and not running) or failed or input_status.get('phase') == 'error'),
                        speaking=speaking)
            active |= bool(input_status['busy'] or pending or reading.get('reading') or speaking
                           or downloads or starting or update_monitor.busy)
        if not active:
            timer.stop()
        elif not timer.isActive():
            timer.start(1500)

    timer = QTimer()
    timer.timeout.connect(refresh)
    files = QFileSystemWatcher(app)
    files.directoryChanged.connect(lambda _folder: changed())
    for folder in (Path(path).resolve().parent, downloads_directory()):
        try:
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            files.addPath(str(folder))
        except OSError:
            pass
    if tray and os.name != 'nt':
        # Plasma saves its colour and theme settings here; the tray's lines follow them.
        desktop_settings = QFileSystemWatcher(app)
        desktop_settings.addPath(os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config'))
        def colours_changed(_folder):
            tray.colours_changed()
            changed()
        desktop_settings.directoryChanged.connect(colours_changed)
    # A rare check for what no file or signal announces, such as the weekly update check.
    hourly = QTimer()
    hourly.timeout.connect(changed)
    hourly.start(3600 * 1000)
    refresh()
    if graphical and os.name != 'nt' and os.environ.get('WAYLAND_DISPLAY'):
        QTimer.singleShot(0, lambda: threading.Thread(target=state.restore_desktop_shortcuts, daemon=True).start())
    if graphical and os.name != 'nt':
        # Leave with the desktop. Plasma asks Qt to survive a compositor exit,
        # so at logout nothing else would stop this controller; the next login
        # would then reach a controller with no screen, tray or live shortcuts.
        from . import login_session
        state.login_session = login_session.current()
        if state.login_session:
            def check_login():
                if not state.closed and not login_session.running(state.login_session):
                    import logging
                    logging.warning('Login session %s ended; quitting', state.login_session)
                    submit({'command': 'quit'})
            try:
                # logind tells us when sessions change; no need to keep asking.
                session_monitor = login_session.Monitor()
                session_notifier = QSocketNotifier(session_monitor.fd, QSocketNotifier.Read, app)
                def sessions_changed(*_):
                    session_monitor.flush()
                    check_login()
                session_notifier.activated.connect(sessions_changed)
            except OSError:
                session_timer = QTimer()
                session_timer.timeout.connect(check_login)
                session_timer.start(3000)
    # Let the tray appear first, then load models in the background.
    QTimer.singleShot(1000, lambda: threading.Thread(target=state.get_ready, daemon=True).start())
    try:
        from . import startup
        startup.refresh()
    except Exception:
        import logging
        logging.exception('Could not update the start-at-login entry')
    try:
        app.exec()
    finally:
        # Stop accepting clients before waiting for backend process cleanup.
        server.close()
        state.quit()
        lock.unlock()
