"""Akousousin control panel / installer entry point."""
import argparse
import multiprocessing
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
    parser = argparse.ArgumentParser(description='Akousousin — Neural Voice Engine. SAPI TTS via Piper; experimental Speech Dispatcher; Whisper planned.')
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
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--quit', action='store_true', help='Stop Piper and quit Akousousin')
    parser.add_argument('--controller', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--panel', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--start-server', action='store_true')
    parser.add_argument('--stop-server', action='store_true')
    parser.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--instance', default='', help=argparse.SUPPRESS)
    parser.add_argument('--control-file', help=argparse.SUPPRESS)
    parser.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.protocol_version:
        print('2')
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
    if args.refresh_registrations:
        from .updates import refresh_registrations
        refresh_registrations(args.settings)
        return
    if args.uninstall_speech_dispatcher:
        from .speech_dispatcher import configure
        print(f'Module removed from {configure(args.settings, remove=True)}. Speech Dispatcher restarted.')
        return
    if args.install_speech_dispatcher:
        from .speech_dispatcher import configure
        print(f'Module registered in {configure(args.settings)}. Speech Dispatcher restarted; select akousousin.')
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
    import os
    request = None
    if args.api_start:
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
        response = runtime.call(args.settings, request, launch=request['command'] not in ('release', 'stop', 'quit', 'status'))
        print(json.dumps(response or {'running': False, 'sessions': 0}))
        return
    runtime.initialize()
    from .panel import Panel
    panel = Panel(args.settings)
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
