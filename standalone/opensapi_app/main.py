"""OpenSAPI control panel / installer entry point."""
import argparse
import multiprocessing
import sys
from pathlib import Path

from . import resources, settings
from .install import Installer
from .service import Service


def main():
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description='OpenSAPI — voices for Windows applications and Wine prefixes')
    parser.add_argument('--wine-prefix', type=Path, help='Install into this initialized 64-bit Wine prefix')
    parser.add_argument('--wine', help='Wine executable or AppImage used by this prefix')
    parser.add_argument('--install', action='store_true', help='Install into native Windows')
    parser.add_argument('--install-only', action='store_true', help='Install without opening the control panel')
    parser.add_argument('--sapi-wav', nargs=2, metavar=('OUTPUT', 'TEXT'))
    parser.add_argument('--uninstall', action='store_true', help='Restore backed-up registry settings and DLLs')
    parser.add_argument('--wine-compat', action='store_true', help='Force the Wine 11.21 SAPI compatibility DLL')
    parser.add_argument('--settings', type=Path, default=settings.config_path())
    parser.add_argument('--start-server', action='store_true')
    parser.add_argument('--stop-server', action='store_true')
    parser.add_argument('--serve', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--instance', default='', help=argparse.SUPPRESS)
    parser.add_argument('--control-file', help=argparse.SUPPRESS)
    parser.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        from .backend import serve
        serve(args.settings, args.instance, args.control_file)
        return
    config = resources.bootstrap(args.settings)
    if args.wine_prefix:
        config['wine_prefix'] = str(args.wine_prefix.expanduser().resolve())
    if args.wine:
        config['wine'] = args.wine
    settings.save(args.settings, config)
    if args.uninstall:
        Installer(resources.root(), args.wine_prefix or config['wine_prefix'] or None,
                  args.wine or config['wine'] or None).uninstall()
        print('OpenSAPI uninstalled; original speech registration and DLLs restored.')
        return
    if args.wine_prefix or args.install or args.install_only:
        manifest = Installer(resources.root(), args.wine_prefix or None, args.wine,
                             args.wine_compat).install(config)
        print(f'OpenSAPI installed. Recovery record: {manifest}')
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
    if args.start_server:
        resources.persistent_runtime(args.settings)
        Service(args.settings).start(config['port'])
        print('Piper ready on loopback.')
        return
    if args.stop_server:
        stopped = Service(args.settings).stop(config['port'])
        print('Owned server stopping.' if stopped else 'No server owned by this profile was stopped.')
        return
    from .panel import Panel
    panel = Panel(args.settings)
    if args.smoke_test:
        panel.root.after(1500, panel.root.destroy)
    panel.root.mainloop()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'OpenSAPI: {error}', file=sys.stderr)
        raise SystemExit(1)
