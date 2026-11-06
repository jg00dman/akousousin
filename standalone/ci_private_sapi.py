# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Measure Wine DLL routing in a fresh prefix; never operate on a user prefix."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/private-sapi'
RUNTIME = WORK / 'runtime'
WINE = RUNTIME / 'usr/bin/wine'
SERVER = RUNTIME / 'usr/bin/wineserver'
PRIVATE = r'C:\Program Files\Akousousin\compat\x64\sapi.dll'
ENV_KEY = r'HKLM\System\CurrentControlSet\Control\Session Manager\Environment'
OVERRIDE_KEY = r'HKCU\Software\Wine\DllOverrides'
CLASSES = r'HKLM\Software\Classes\CLSID'
RESULTS = {}


def run(args, env, name, check=True, timeout=60):
    # Wine services may inherit stdout after the command exits. Files avoid
    # waiting for a pipe EOF from a long-lived background service.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        completed = subprocess.run([str(x) for x in args], env=env, stdout=output,
                                   stderr=errors, timeout=timeout)
        output.seek(0); errors.seek(0)
        result = subprocess.CompletedProcess(completed.args, completed.returncode,
            output.read().decode('utf-8', errors='replace'),
            errors.read().decode('utf-8', errors='replace'))
    with (WORK / (name + '.log')).open('a', encoding='utf-8') as log:
        log.write(str([str(x) for x in args]) + '\n' + result.stdout + result.stderr + '\n')
    if check and result.returncode:
        raise RuntimeError(f'{name}: exit {result.returncode}\n{result.stdout}\n{result.stderr}')
    return result


def wine(args, env, name, **kwargs):
    return run([WINE, *args], env, name, **kwargs)


def value(key, field, env):
    result = wine(['reg.exe', 'query', key, *field, '/reg:64'], env, 'registry', check=False)
    if result.returncode:
        return None
    match = re.search(r'^\s+[^\r\n]+?\s+(REG_(?:EXPAND_)?SZ)\s+([^\r\n]*)', result.stdout, re.M)
    if not match:
        raise RuntimeError('Cannot parse registry value: ' + result.stdout)
    return match.groups()


def put_value(key, field, original, env):
    if original is None:
        wine(['reg.exe', 'delete', key, *field, '/f', '/reg:64'], env, 'registry', check=False)
    else:
        kind, data = original
        wine(['reg.exe', 'add', key, *field, '/t', kind, '/d', data, '/f', '/reg:64'], env, 'registry')


def restart(env):
    run([SERVER, '-k'], env, 'server', check=False)
    run([SERVER, '-w'], env, 'server', timeout=30)
    run([SERVER, '-p600'], env, 'server')
    wine(['cmd.exe', '/c', 'exit'], env, 'server')


def snapshot(prefix):
    result = {}
    for file in (prefix / 'drive_c/windows').rglob('*'):
        if file.name.lower() != 'sapi.dll':
            continue
        result[str(file.relative_to(prefix))] = {
            'symlink': os.readlink(file) if file.is_symlink() else None,
            'sha256': hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None,
        }
    return result


def measure(label, env, absolute=False):
    entries = []
    for caller in ('one', 'two'):
        for mode in ('load', 'datakey', 'voice'):
            args = [WORK / 'clients' / caller / 'probe.exe', mode]
            if absolute and mode == 'load':
                args.append(PRIVATE)
            output = wine(args, env, label, check=False)
            values = dict(line.split('=', 1) for line in output.stdout.splitlines() if '=' in line)
            entries.append({'caller': caller, 'mode': mode, 'exit': output.returncode, **values})
    RESULTS[label] = entries
    print(label + ': ' + json.dumps(entries), flush=True)
    return entries


def private(entry):
    return entry.get('MODULE', '').replace('/', '\\').casefold() == PRIVATE.casefold()


def sapi_classes(env):
    result = wine(['reg.exe', 'query', CLASSES, '/s', '/reg:64'], env, 'class-discovery')
    records = {}
    key = None
    for line in result.stdout.splitlines():
        if line.startswith('HKEY_'):
            key = line.strip()
        match = re.match(r'\s+\(Default\)\s+(REG_(?:EXPAND_)?SZ)\s+(.+)$', line)
        if key and key.lower().endswith('\\inprocserver32') and match:
            kind, data = match.groups()
            if data.strip('"').replace('/', '\\').split('\\')[-1].lower() == 'sapi.dll':
                records[key] = (kind, data)
    assert records, 'No SAPI COM registrations discovered'
    assert any('{D9F6EE60-58C9-458B-88E1-2F908FD7F87C}' in key.upper() for key in records)
    assert any('{96749377-3391-11D2-9EE3-00C04F797396}' in key.upper() for key in records)
    RESULTS['original_sapi_classes'] = records
    return records


def functional_test(prefix, env):
    # Guard the existing installer: this experiment permits only private writes.
    sys.path[:0] = [str(ROOT / 'standalone'), str(ROOT / 'backend')]
    from akousousin_app.install import Installer, CLSID, FULL_TOKEN
    from akousousin_app import settings
    class PrivateOnlyInstaller(Installer):
        def put(self, source, target):
            assert Path(target).is_relative_to(self.directory), 'System DLL write attempted'
            return super().put(source, target)
    environment = os.environ.copy()
    os.environ.update(env)
    installer = PrivateOnlyInstaller(ROOT / 'build/standalone-engine', prefix, str(WINE))
    config = json.loads(json.dumps(settings.DEFAULTS))
    config['voices'] = {'en_US-ljspeech-medium': {'name': 'Private SAPI probe', 'language': 'en_US',
                                              'sample_rate': 22050, 'path': '/unused-test-model'}}
    try:
        installer.install(config, WORK / 'settings.json')
        assert not installer.state['compatibility'], 'Existing system replacement path was used'
        for name in ('engine-probe.exe', 'sapi-probe.exe'):
            shutil.copy2(ROOT / 'build/standalone-engine' / name, ROOT / 'build' / name)
        test_env = dict(env, AKOUSOUSIN_STANDALONE='1', AKOUSOUSIN_CLSID=CLSID,
                        AKOUSOUSIN_TOKEN=FULL_TOKEN + 'en_US-ljspeech-medium')
        result = run([sys.executable, ROOT / 'tests/test_integration.py'], test_env,
                     'private-com-integration', timeout=240)
        RESULTS['functional_integration'] = {'exit': result.returncode, 'summary': result.stderr[-1800:]}
        print(result.stdout + result.stderr, flush=True)
    finally:
        if installer.manifest.exists():
            installer.uninstall()
        os.environ.clear(); os.environ.update(environment)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    source = next(RUNTIME.rglob('x86_64-windows/sapi.dll'))
    RESULTS['runtime_sapi_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    for caller in ('one', 'two'):
        folder = WORK / 'clients' / caller
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(WORK / 'sapi-location.exe', folder / 'probe.exe')
    with tempfile.TemporaryDirectory(prefix='prefix-', dir=WORK) as temporary:
        prefix = Path(temporary)
        env = dict(os.environ, WINEPREFIX=str(prefix), WINEARCH='win64', WINEDEBUG='-all',
                   WINESERVER=str(SERVER), WINE=str(WINE), WINEDLLOVERRIDES='mscoree,mshtml=')
        env.pop('WINEPATH', None)
        try:
            wine(['wineboot.exe', '-u'], env, 'initialize', timeout=120)
            run([SERVER, '-w'], env, 'initialize', timeout=90)
            restart(env)
            before = snapshot(prefix)
            assert before, 'No baseline SAPI files found'
            RESULTS['system_before'] = before
            baseline = measure('baseline', env)
            assert all(entry['exit'] == 0 for entry in baseline if entry['mode'] != 'load'), 'Baseline COM initialization failed'
            destination = prefix / 'drive_c/Program Files/Akousousin/compat/x64/sapi.dll'
            destination.parent.mkdir(parents=True)
            shutil.copy2(source, destination)
            original_path = value(ENV_KEY, ['/v', 'Path'], env)
            assert original_path is not None
            original_override = value(OVERRIDE_KEY, ['/v', 'sapi'], env)
            put_value(ENV_KEY, ['/v', 'Path'], (original_path[0], PRIVATE.rsplit('\\', 1)[0] + ';' + original_path[1]), env)
            put_value(OVERRIDE_KEY, ['/v', 'sapi'], ('REG_SZ', 'native,builtin'), env)
            restart(env)
            path_entries = measure('path_and_override', env)
            measure('explicit_absolute_load', env, absolute=True)
            forced_env = dict(env, WINEPATH=PRIVATE.rsplit('\\', 1)[0])
            measure('winepath_and_override', forced_env)
            records = sapi_classes(env)
            for key in records:
                put_value(key, ['/ve'], ('REG_SZ', PRIVATE), env)
            restart(env)
            com_entries = measure('private_com', env)
            com_ok = all(entry['exit'] == 0 and private(entry) for entry in com_entries if entry['mode'] != 'load')
            RESULTS['private_com_works'] = com_ok
            RESULTS['path_only_covers_all_modes'] = all(entry['exit'] == 0 and private(entry) for entry in path_entries)
            if com_ok:
                functional_test(prefix, env)
            for key, original in records.items():
                put_value(key, ['/ve'], original, env)
            put_value(ENV_KEY, ['/v', 'Path'], original_path, env)
            put_value(OVERRIDE_KEY, ['/v', 'sapi'], original_override, env)
            restart(env)
            restored = measure('registration_restored', env)
            assert [(entry['caller'], entry['mode'], entry['exit'], entry.get('MODULE')) for entry in restored] == [(entry['caller'], entry['mode'], entry['exit'], entry.get('MODULE')) for entry in baseline], 'Restored registration differs from baseline'
            after = snapshot(prefix)
            RESULTS['system_after'] = after
            RESULTS['system_files_unchanged'] = before == after
            assert before == after, 'System SAPI file bytes or links changed'
            assert hashlib.sha256(source.read_bytes()).hexdigest() == RESULTS['runtime_sapi_sha256']
            assert com_ok, 'Private COM mapping did not route all tested COM clients'
        finally:
            try:
                run([SERVER, '-k'], env, 'cleanup', check=False)
                run([SERVER, '-w'], env, 'cleanup', check=False, timeout=30)
            finally:
                (WORK / 'results.json').write_text(json.dumps(RESULTS, indent=2), encoding='utf-8')
    print('PASS: experiment completed in a disposable prefix; system SAPI files unchanged', flush=True)


if __name__ == '__main__':
    main()
