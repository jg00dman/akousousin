"""Test program-only packages; download a voice only into disposable CI test data, never an artifact."""
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
package = ROOT / 'build/standalone-package/OpenSAPI'
executable = package / ('opensapi.exe' if native else 'opensapi')
resource = package / 'resources'
settings_path = WORK / 'settings.json'
prefix = WORK / 'prefix'
prefix.mkdir(exist_ok=True)
(prefix / '.opensapi-test-prefix').touch()
env = os.environ.copy()
env.update(PYTHONPATH=str(ROOT / 'standalone') + os.pathsep + str(ROOT / 'backend'),
           OPENSAPI_RESOURCES=str(resource), OPENSAPI_STANDALONE='1',
           OPENSAPI_CLSID='{EA7A00AB-0FB7-4DEB-81C5-550D854F390F}',
           OPENSAPI_TOKEN=r'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices\Tokens\OpenSAPI-Piper-en_US-ljspeech-medium',
           WINEPREFIX=str(prefix), XDG_CONFIG_HOME=str(WORK / 'config'), XDG_DATA_HOME=str(WORK / 'data'))
if native:
    env['LOCALAPPDATA'] = str(WORK / 'appdata')
    env['OPENSAPI_NATIVE_WINDOWS'] = '1'
    originals = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [
        Path(os.environ['WINDIR']) / 'System32/sapi.dll',
        Path(os.environ['WINDIR']) / 'System32/Speech/Common/sapi.dll'] if p.exists()}
    install = [str(executable), '--install', '--install-only', '--settings', str(settings_path)]
else:
    executable = ROOT / 'standalone-dist/OpenSAPI-x86_64.AppImage'
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
    install = [str(executable), '--wine-prefix', str(prefix), '--wine', str(wine), '--wine-compat',
               '--install-only', '--settings', str(settings_path)]
# Package has already been built. Voice weights below stay exclusively under build/test-voice.
sys.path[:0] = [str(ROOT / 'standalone'), str(ROOT / 'backend')]
from opensapi_app import catalogue, settings
from opensapi_app.service import Service
config = settings.load(settings_path)
entry = catalogue.catalogue(resource)['en_US-ljspeech-medium']
voice = catalogue.install(entry, WORK / 'test-voice', reviewed=True)
config['voices']['en_US-ljspeech-medium'] = voice
config['language_voices']['en_US'] = 'en_US-ljspeech-medium'
settings.save(settings_path, config)
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
config['runtime'] = str(executable)
settings.save(settings_path, config)
service = Service(settings_path)
try:
    service.start(config['port'])
    wav = WORK / 'real-sapi.wav'
    command = [str(executable), '--settings', str(settings_path), '--sapi-wav', str(wav), 'Standalone Open SAPI is speaking.']
    subprocess.run(command, env=env, check=True, timeout=90)
    with wave.open(str(wav), 'rb') as audio:
        assert audio.getnchannels() == 1 and audio.getsampwidth() == 2 and audio.getframerate() == 22050
        assert audio.getnframes() > 2205 and any(audio.readframes(audio.getnframes()))
    assert Service(settings_path).stop(config['port']), 'Reopened panel could not stop its own server'
    service.start(config['port'])
    assert service.health(config['port'])['ready']
finally:
    Service(settings_path).stop(config['port'])
subprocess.run([str(executable), '--settings', str(settings_path), '--smoke-test'], env=env, check=True, timeout=30)
if not native:
    os.environ.update({k: v for k, v in env.items() if k in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'OPENSAPI_RESOURCES')})
    from opensapi_app.panel import Panel
    from PIL import ImageGrab
    panel = Panel(settings_path)
    panel.root.update()
    ImageGrab.grab().save(WORK / 'control-panel.png')
    panel.root.destroy()
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
