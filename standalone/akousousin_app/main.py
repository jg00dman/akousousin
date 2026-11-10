# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Akousousin control panel / installer entry point."""
import argparse
import multiprocessing
import os
import sys
from pathlib import Path

from . import resources, runtime, settings
from .install import Installer


def main():
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == '--whisper':
        from akousousin_backend.recognition import main as recognition_main
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        recognition_main()
        return
    parser = argparse.ArgumentParser(description='Akousousin — Neural Voice Engine. SAPI TTS via Piper; experimental Speech Dispatcher and local Whisper dictation.')
    parser.add_argument('--wine-prefix', type=Path, help='Install into this initialized 64-bit Wine prefix')
    parser.add_argument('--wine', help='Wine executable or AppImage used by this prefix')
    parser.add_argument('--install', action='store_true', help='Install into native Windows')
    parser.add_argument('--install-only', action='store_true', help='Install without opening the control panel')
    parser.add_argument('--sapi-wav', nargs=2, metavar=('OUTPUT', 'TEXT'))
    parser.add_argument('--uninstall', action='store_true', help='Restore backed-up registry settings and DLLs')
    parser.add_argument('--wine-compat', action='store_true', help='Force the Wine 11.21 SAPI compatibility DLL')
    parser.add_argument('--settings', type=Path, default=settings.config_path())
    parser.add_argument('--refresh-registrations', action='store_true', help='Reapply saved SAPI registrations after an update')
    parser.add_argument('--protocol-version', action='store_true', help='Print launcher protocol version')
    parser.add_argument('--configure', action='store_true', help='Open shared speech preferences')
    parser.add_argument('--acquire-session', metavar='ID', help='Start/reuse speech for this application session')
    parser.add_argument('--release-session', metavar='ID', help='Release an application session')
    parser.add_argument('--owner-pid', type=int, help='Process owning the acquired session')
    parser.add_argument('--api-start', action='store_true', help='Wake speech on demand without pinning a model in memory')
    parser.add_argument('--install-speech-dispatcher', action='store_true', help='Register the output module in your user Speech Dispatcher configuration')
    parser.add_argument('--uninstall-speech-dispatcher', action='store_true', help='Remove your user output-module registration')
    parser.add_argument('--speech-dispatcher', action='store_true', help='Run a Speech Dispatcher output module on stdin/stdout')
    reading = parser.add_mutually_exclusive_group()
    reading.add_argument('--read-selection', action='store_true', help='Read highlighted Linux desktop text; repeat to stop')
    reading.add_argument('--read-clipboard', action='store_true', help='Read copied text; repeat to stop')
    reading.add_argument('--stop-reading', action='store_true', help='Stop only Akousousin selection reading')
    reading.add_argument('--selection-status', action='store_true', help='Show selection reading and shortcut status')
    parser.add_argument('--install-selection-action', action='store_true', help='Install a desktop action for manual global-shortcut binding')
    parser.add_argument('--dictation-toggle', action='store_true', help='Toggle enabled desktop dictation')
    parser.add_argument('--dictation-cancel', action='store_true', help='Cancel capture, recognition and pending insertion')
    parser.add_argument('--dictation-status', action='store_true', help='Show shared recognition state and latest transcripts')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--download-starter-voice', action='store_true',
                        help='Download the reviewed starter voice once into the persistent voice library')
    parser.add_argument('--quit', action='store_true', help='Stop Piper and quit Akousousin')
    parser.add_argument('--controller', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--panel', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--start-server', action='store_true')
    parser.add_argument('--stop-server', action='store_true')
    parser.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--instance', default='', help=argparse.SUPPRESS)
    parser.add_argument('--control-file', help=argparse.SUPPRESS)
    parser.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    bundle = parser.add_mutually_exclusive_group()
    bundle.add_argument('--install-bundle', type=Path, help='Install an extracted Linux tar bundle for this user')
    bundle.add_argument('--uninstall-bundle', type=Path, help='Remove a tar installation, preserving models and settings')
    parser.add_argument('--bundle-prefix', type=Path, help='Tar installation prefix (default: ~/.local)')
    args = parser.parse_args()
    if args.install_bundle or args.uninstall_bundle:
        if os.name != 'posix' or sys.platform != 'linux':
            raise RuntimeError('Tar installation requires Linux')
        if os.geteuid() == 0:
            raise RuntimeError('Run this per-user installer without sudo')
        if runtime.call(args.settings, {'command': 'status'}, launch=False):
            raise RuntimeError('Quit AKS from its tray before installing or removing a bundle')
        from .linux_bundle import install, uninstall
        if args.install_bundle:
            print('Installed: ' + str(install(args.install_bundle, args.bundle_prefix)))
        else:
            print(uninstall(args.uninstall_bundle))
        return
    if args.protocol_version:
        print('2')
        return
    if args.install_selection_action:
        from .selection import install_action
        print(install_action(args.settings))
        return
    if args.serve:
        from .backend import serve
        serve(args.settings, args.instance, args.control_file)
        return
    if args.controller:
        from .controller import run
        run(args.settings)
        return
    if args.speech_dispatcher:
        from .speech_dispatcher import Module
        resources.bootstrap(args.settings)
        Module(args.settings).run()
        return
    config = resources.bootstrap(args.settings)
    if args.download_starter_voice:
        import json
        config = resources.download_starter(args.settings)
        print(json.dumps(config['voices'][resources.STARTER]))
        return
    if args.refresh_registrations:
        from .updates import refresh_registrations
        for warning in refresh_registrations(args.settings):
            print('Warning: ' + warning, file=sys.stderr)
        return
    if args.uninstall_speech_dispatcher:
        from .speech_dispatcher import configure
        configure(args.settings, remove=True)
        print('Akousousin Speech Dispatcher support removed. Speech Dispatcher restarted.')
        return
    if args.install_speech_dispatcher:
        from .speech_dispatcher import configure
        configure(args.settings)
        print('Akousousin added to Speech Dispatcher. Speech Dispatcher restarted; select akousousin.')
        return
    if args.wine_prefix:
        config['wine_prefix'] = str(args.wine_prefix.expanduser().resolve())
    if args.wine:
        config['wine'] = args.wine
    if args.wine_prefix or args.wine:
        settings.save(args.settings, config)
    if args.uninstall:
        Installer(resources.root(), args.wine_prefix or config['wine_prefix'] or None,
                  args.wine or config['wine'] or None).uninstall()
        print('Akousousin uninstalled; original speech registration and DLLs restored.')
        return
    if args.wine_prefix or args.install or args.install_only:
        manifest = Installer(resources.root(), args.wine_prefix or None, args.wine,
                             args.wine_compat).install(config, args.settings)
        settings.register(args.settings, args.wine_prefix, args.wine)
        print(f'Akousousin installed. Recovery record: {manifest}')
        if args.install_only and not args.sapi_wav:
            return
    if args.sapi_wav:
        installer = Installer(resources.root(), args.wine_prefix or config['wine_prefix'] or None,
                              args.wine or config['wine'] or None)
        output = installer.windows(Path(args.sapi_wav[0]).resolve())
        result = installer.execute(installer.windows(resources.root() / 'sapi-probe.exe'), output,
                                   '0', '100', args.sapi_wav[1], timeout=75)
        print(result.stdout)
        return
    import json
    request = None
    if args.read_selection or args.read_clipboard or args.stop_reading or args.selection_status:
        request = {'command': 'selection-stop' if args.stop_reading else 'selection-status' if args.selection_status else 'selection-toggle'}
        if args.read_selection or args.read_clipboard:
            request['clipboard'] = args.read_clipboard
    elif args.dictation_toggle or args.dictation_cancel or args.dictation_status:
        request = {'command': 'stt-toggle' if args.dictation_toggle else 'stt-cancel' if args.dictation_cancel else 'stt-status'}
    elif args.api_start:
        request = {'command': 'wake'}
    elif args.acquire_session:
        request = {'command': 'acquire', 'session': args.acquire_session, 'pid': args.owner_pid or os.getppid()}
    elif args.release_session:
        request = {'command': 'release', 'session': args.release_session}
    elif args.start_server or args.stop_server or args.quit or args.status:
        operation = 'start' if args.start_server else 'stop' if args.stop_server else 'quit' if args.quit else 'status'
        request = {'command': operation}
    elif not args.panel and not args.smoke_test:
        request = {'command': 'configure', 'independent': not args.configure}
    if request:
        response = runtime.call(args.settings, request, launch=request['command'] not in ('release', 'stop', 'quit', 'status', 'stt-status', 'stt-cancel', 'selection-status', 'selection-stop'))
        print(json.dumps(response or {'running': False, 'sessions': 0}))
        return
    runtime.initialize()
    from .panel import Panel
    panel = Panel(args.settings, offer_install=not args.smoke_test)
    if args.smoke_test:
        panel.show('Voice Input')
        assert panel.voice_input.state.get()
        panel.root.after(1500, panel.root.destroy)
    panel.root.mainloop()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Akousousin: {error}', file=sys.stderr)
        raise SystemExit(1)
