"""Test packaged SAPI, the approved starter voice, shared sessions and controller lifecycle."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/standalone-ci'
WORK.mkdir(parents=True, exist_ok=True)
native = os.name == 'nt'
package = ROOT / 'build/standalone-package/Akousousin'
executable = package / ('akousousin.exe' if native else 'akousousin')
resource = package / 'resources'
settings_path = WORK / 'settings.json'
prefix = WORK / 'prefix'
prefix.mkdir(exist_ok=True)
(prefix / '.akousousin-test-prefix').touch()
env = os.environ.copy()
env.update(PYTHONPATH=str(ROOT / 'standalone') + os.pathsep + str(ROOT / 'backend'),
           AKOUSOUSIN_RESOURCES=str(resource), AKOUSOUSIN_STANDALONE='1',
           AKOUSOUSIN_CLSID='{EA7A00AB-0FB7-4DEB-81C5-550D854F390F}',
           AKOUSOUSIN_TOKEN=r'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\Tokens\Akousousin-Piper-en_US-ljspeech-medium',
           XDG_STATE_HOME=str(WORK / 'state'), QT_QPA_PLATFORM='offscreen',
           WINEPREFIX=str(prefix), XDG_CONFIG_HOME=str(WORK / 'config'), XDG_DATA_HOME=str(WORK / 'data'))
if native:
    env['LOCALAPPDATA'] = str(WORK / 'appdata')
    env['AKOUSOUSIN_NATIVE_WINDOWS'] = '1'
    originals = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [
        Path(os.environ['WINDIR']) / 'System32/sapi.dll',
        Path(os.environ['WINDIR']) / 'System32/Speech/Common/sapi.dll'] if p.exists()}
    install = [str(executable), '--install', '--install-only', '--settings', str(settings_path)]
else:
    executable = ROOT / 'standalone-dist/Akousousin-x86_64.AppImage'
    os.environ['APPIMAGE_EXTRACT_AND_RUN'] = '1'
    env['APPIMAGE_EXTRACT_AND_RUN'] = '1'
    subprocess.run([str(executable), '--help'], env=env, check=True, timeout=60)
    runtime = ROOT / 'build/standalone-package/downloads/wine-runtime.tar.xz'
    wine_dir = WORK / 'wine'
    wine_dir.mkdir(exist_ok=True)
    subprocess.run(['tar', '-xJf', str(runtime), '-C', str(wine_dir)], check=True)
    wine = wine_dir / 'usr/bin/wine'
    env.update(WINE=str(wine), WINESERVER=str(wine_dir / 'usr/bin/wineserver'),
               WINEDLLOVERRIDES='mscoree,mshtml=;sapi=n,b', WINEDEBUG='-all')
    subprocess.run([str(wine), 'wineboot.exe', '-u'], env=env | {'WINEDLLOVERRIDES': 'mscoree,mshtml='},
                   check=True, timeout=120)
    subprocess.run([env['WINESERVER'], '-w'], env=env, check=True, timeout=90)
    assert (prefix / 'system.reg').is_file(), 'Wine initialization did not persist its registry'
    # Benchmarks must measure speech/cancellation, not repeated Wine session startup.
    # Keep the disposable test session alive; retain the original three-second assertions.
    subprocess.run([env['WINESERVER'], '-p600'], env=env, check=True, timeout=15)
    subprocess.run([str(wine), 'cmd.exe', '/c', 'exit'], env=env, check=True, timeout=60,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    install = [str(executable), '--wine-prefix', str(prefix), '--wine', str(wine), '--wine-compat',
               '--install-only', '--settings', str(settings_path)]
# Fresh settings must bootstrap the approved voice from the actual package.
subprocess.run([str(executable), '--settings', str(settings_path), '--status'], env=env, check=True, timeout=60)
sys.path[:0] = [str(ROOT / 'standalone'), str(ROOT / 'backend')]
from akousousin_app import settings
from akousousin_app.service import Service
config = settings.load(settings_path)
assert config['voice'] == 'en_US-ljspeech-medium'
assert Path(config['voices'][config['voice']]['path']).is_file(), 'Bundled default voice was not installed'
subprocess.run(install, env=env, check=True, timeout=180)
for name in ['sapi-probe.exe', 'engine-probe.exe']:
    shutil.copy(resource / name, ROOT / 'build' / name)
for script, log in [('tests/test_integration.py', 'integration.log'), ('tests/test_failures.py', 'failure-recovery.log')]:
    print(f'Running {script}', flush=True)
    with (WORK / log).open('w', encoding='utf-8') as output:
        result = subprocess.run([sys.executable, str(ROOT / script)], env=env, stdout=output,
                                stderr=subprocess.STDOUT, timeout=300)
    print((WORK / log).read_text(), flush=True)
    result.check_returncode()
config = settings.load(settings_path)
service = Service(settings_path)
def public(*args):
    completed = subprocess.run([str(executable), '--settings', str(settings_path), *args], env=env,
                               check=False, capture_output=True, text=True, timeout=100)
    print(completed.stdout, completed.stderr, flush=True)
    completed.check_returncode()
    return __import__('json').loads(completed.stdout.splitlines()[-1])
try:
    assert public('--acquire-session', 'logos-ci', '--owner-pid', str(os.getpid()))['running']
    if not native:
        identity = Path(env['XDG_DATA_HOME']) / 'applications/org.akousousin.Akousousin.desktop'
        assert identity.is_file(), 'Packaged controller did not install desktop identity'
        print(identity.read_text(), flush=True)
        # The real portal uses GIO lookup by ID, not merely file existence.
        subprocess.run([sys.executable, '-c',
                        "import ctypes; lib=ctypes.CDLL('libgio-2.0.so.0'); "
                        "lookup=lib.g_desktop_app_info_new; lookup.argtypes=[ctypes.c_char_p]; "
                        "lookup.restype=ctypes.c_void_p; "
                        "assert lookup(b'org.akousousin.Akousousin.desktop'), 'Packaged desktop identity cannot be resolved by host GIO'"],
                       env=env, check=True, timeout=10)
    assert public('--acquire-session', 'second-ci', '--owner-pid', str(os.getpid()))['sessions'] == 2
    wav = WORK / 'real-sapi.wav'
    command = [str(executable), '--settings', str(settings_path), '--sapi-wav', str(wav), 'Standalone Open SAPI is speaking.']
    subprocess.run(command, env=env, check=True, timeout=90)
    with wave.open(str(wav), 'rb') as audio:
        assert audio.getnchannels() == 1 and audio.getsampwidth() == 2 and audio.getframerate() == 22050
        assert audio.getnframes() > 2205 and any(audio.readframes(audio.getnframes()))
    assert public('--release-session', 'logos-ci')['running']
    assert public('--release-session', 'second-ci')['closed']
    import time
    time.sleep(2)
    assert not public('--status')['running']
    assert public('--start-server')['independent']
    public('--acquire-session', 'logos-ci', '--owner-pid', str(os.getpid()))
    assert public('--release-session', 'logos-ci')['running'], 'Independent service was stopped by Logos release'
finally:
    public('--quit')
# Exercise actual SAPI-triggered startup, without an OD session or manual Start.
# Keep the assertion on generated neural audio; a healthy HTTP listener alone is insufficient.
import time
time.sleep(2)
config['idle_timeout'] = 2
settings.save(settings_path, config)
try:
    cold_wav = WORK / 'on-demand-sapi.wav'
    subprocess.run([str(executable), '--settings', str(settings_path), '--sapi-wav', str(cold_wav),
                    'Speech started directly from the SAPI call.'], env=env, check=True, timeout=100)
    with wave.open(str(cold_wav), 'rb') as audio:
        assert audio.getnframes() > 2205
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        health = service.health(config['port'])
        if health and health.get('model_loaded') is False:
            break
        time.sleep(.2)
    else:
        raise AssertionError('Idle model did not unload')
    # Same resident listener must reload the model on its next speech request.
    subprocess.run([str(executable), '--settings', str(settings_path), '--sapi-wav', str(WORK / 'idle-restart.wav'),
                    'The idle model has restarted.'], env=env, check=True, timeout=100)
    print('PASS: SAPI cold startup and reload after idle unload', flush=True)
finally:
    public('--quit')
    config['idle_timeout'] = 300
    settings.save(settings_path, config)
    time.sleep(2)

assert not (WORK / 'data/Akousousin/runtimes').exists(), 'An extracted runtime was retained'
subprocess.run([str(executable), '--settings', str(settings_path), '--smoke-test'], env=env, check=True, timeout=30)
if not native:
    os.environ.update({k: v for k, v in env.items() if k in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'AKOUSOUSIN_RESOURCES')})
    from akousousin_app.panel import Panel
    from PIL import ImageGrab
    panel = Panel(settings_path)
    panel.root.update()
    ImageGrab.grab().save(WORK / 'control-panel.png')
    panel.root.destroy()
# Updates reapply saved active registrations using the new package. Exercise
# this against the initialized Wine/native Windows installation before rollback.
subprocess.run([str(executable), '--settings', str(settings_path), '--refresh-registrations'],
               env=env, check=True, timeout=180)
print('PASS: packaged refresh of saved active SAPI registrations', flush=True)
command = [str(executable), '--uninstall', '--settings', str(settings_path)]
if not native:
    command += ['--wine-prefix', str(prefix), '--wine', str(wine)]
subprocess.run(command, env=env, check=True, timeout=90)
if not native:
    subprocess.run([env['WINESERVER'], '-k'], env=env, check=True, timeout=15)
    subprocess.run([env['WINESERVER'], '-w'], env=env, check=True, timeout=30)
if native:
    for path, sha in originals.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha, 'Windows system SAPI was modified'
print('PASS: standalone DLL, deterministic/failure tests, real SAPI speech, panel, service reuse/stop/restart and uninstall.')
