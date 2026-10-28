#!/usr/bin/env python3
"""Local, versioned install. No network, no dependency installer, no project edits.

Updates are explicit trusted-code installation: checksums detect accidental
changes, not malicious authorship. Self-tests are not a substitute for code review.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
    with open(temporary, 'x') as f:
        os.chmod(temporary, 0o600)
        f.write(json.dumps(value, indent=2) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)


def release_file(path, source):
    # Finder/archive metadata is not code. Do not let merely opening the ZIP on
    # macOS invalidate an otherwise identical release. Other extra files fail.
    relative = path.relative_to(source)
    return (path.is_file() and not any(part in {'__pycache__', '.git', '__MACOSX'} for part in relative.parts)
            and path.name not in {'RELEASE.json', '.DS_Store'} and not path.name.startswith('._'))

def verify(source):
    meta = json.loads((source / 'RELEASE.json').read_text())
    if meta.get('format') != 1 or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', meta.get('version', '')):
        raise ValueError('Unsupported release format/version.')
    files = meta.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('Release has no file inventory.')
    actual = {str(p.relative_to(source)) for p in source.rglob('*') if release_file(p, source)}
    if actual != set(files):
        raise ValueError('Release inventory mismatch. Build the release manifest before installing modified code.')
    for name, expected in files.items():
        file = source / name
        if not file.resolve().is_relative_to(source.resolve()) or file.is_symlink() or not file.is_file():
            raise ValueError('Unsafe or missing release file: ' + name)
        if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise ValueError('Release checksum mismatch: ' + name)
    return meta


def main():
    if sys.version_info < (3, 10):
        raise SystemExit('Install Python 3.10+ first, then rerun this installer using that Python.')
    p = argparse.ArgumentParser()
    p.add_argument('--source', default=str(Path(__file__).resolve().parent))
    p.add_argument('--rollback', action='store_true')
    p.add_argument('--install-root', default=os.environ.get('RESEARCHFLOW_INSTALL_ROOT', '~/.local/share/researchflow'))
    p.add_argument('--bin-dir', default='~/.local/bin')
    a = p.parse_args()
    root = Path(a.install_root).expanduser().resolve()
    bindir = Path(a.bin_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lockfile = open(root / 'install.lock', 'a+')
    try:
        fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('An installation or ResearchFlow session is active. Close it before updating or rolling back.')
    current = root / 'active.json'
    previous = json.loads(current.read_text()) if current.exists() else None
    if a.rollback:
        if not previous or not previous.get('previous'):
            raise SystemExit('No previous installation is available. Nothing changed.')
        target = Path(previous['previous'])
        meta = verify(target)
        atomic(current, {'release': str(target), 'previous': previous['release'], 'version': meta['version'], 'python': previous.get('previous_python', previous['python']), 'previous_python': previous['python']})
        print('Rolled back. Projects, feedback and settings were not changed.')
        return 0
    source = Path(a.source).expanduser().resolve()
    meta = verify(source)
    release_id = meta['version'] + '-' + hashlib.sha256(json.dumps(meta['files'], sort_keys=True).encode()).hexdigest()[:12]
    destination = root / 'releases' / release_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        verify(destination)
    else:
        temp = destination.parent / ('.staging-' + uuid.uuid4().hex)
        shutil.copytree(source, temp, ignore=shutil.ignore_patterns('__pycache__', '.git', '.DS_Store', '__MACOSX', '._*'))
        # Test the copied/installed layout, not just the development checkout.
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        env['RESEARCHFLOW_INSTALLING'] = '1'
        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=temp, env=env)
        if result.returncode:
            raise SystemExit(f'Installation checks failed. Active release is unchanged. Inspect {temp}')
        verify(temp)
        os.replace(temp, destination)
    bindir.mkdir(parents=True, exist_ok=True)
    launcher = bindir / 'researchflow'
    marker = '# ResearchFlow managed launcher v1'
    if launcher.exists() and marker not in launcher.read_text(errors='replace'):
        raise SystemExit(f'{launcher} already exists and is not ours. It was not overwritten.')
    # A stable small shell shim chooses the interpreter recorded at installation.
    # No edits to .zshrc, Claude rules, Cursor settings, or user projects.
    code = ('import json,os,sys; from pathlib import Path; '
            'r=Path(sys.argv[1]); d=json.loads((r/"active.json").read_text()); '
            'os.environ["RESEARCHFLOW_INSTALL_ROOT"]=str(r); '
            'os.execv(d["python"],[d["python"],str(Path(d["release"])/"researchflow.py"),*sys.argv[2:]])')
    text = '#!/bin/sh\n' + marker + '\nexec ' + shlex.quote(sys.executable) + ' -c ' + shlex.quote(code) + ' ' + shlex.quote(str(root)) + ' "$@"\n'
    temp_launcher = bindir / ('.researchflow-' + uuid.uuid4().hex)
    temp_launcher.write_text(text)
    temp_launcher.chmod(0o700)
    os.replace(temp_launcher, launcher)
    if not previous or previous['release'] != str(destination):
        atomic(current, {'release': str(destination), 'previous': previous['release'] if previous else None,
                         'version': meta['version'], 'python': sys.executable,
                         'previous_python': previous['python'] if previous else None})
    print('\nInstalled ResearchFlow ' + meta['version'])
    print('Next: ' + shlex.quote(str(launcher)) + ' setup')
    print('Settings and project records live in ~/ResearchFlow, separate from versioned code.')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit('Install stopped without replacing the active release: ' + str(exc))
