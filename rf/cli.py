"""User surface: setup, start, status. Other commands are for Claude or maintenance."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from . import VERSION
from .support import FlowError, child_env, home, load, lock, now, private_dir, run, save, uid, write
from .project import inspect, locate, prepare, validate_workspace
from .providers import capability, cursor_profile, executable, settings, worker
from .workflow import PACKAGE, assign, baseline, check, consult, operation, status


def doctor():
    private_dir(home())
    cfg = settings()
    print('ResearchFlow ' + VERSION + ' — ' + sys.platform)
    print('Python: ' + sys.version.split()[0])
    git = run(['git', '--version'], home(), timeout=10)
    print((git['stdout'] or git['stderr']).strip())
    failures = []
    if git['exit_code'] != 0 or git['reason']:
        failures.append('Git is missing or not working.')
    for provider in ('claude', 'cursor', 'codex'):
        try:
            path, version = capability(provider, cfg)
            print(f'{provider}: FOUND {version} at {path}')
        except FlowError as exc:
            failures.append(str(exc))
            print(f'{provider}: NOT READY — {exc}')
    print('Cursor model: ' + (cfg['cursor_model'] or 'NOT SELECTED — run researchflow setup'))
    if not cfg['cursor_model']:
        failures.append('Cursor model not selected.')
    print('This checks local interfaces only. It does NOT prove login, billing, or live model behavior.')
    print('Live check: researchflow demo --live (uses your accounts, synthetic data only).')
    save(home() / 'doctor.json', {'time': now(), 'version': VERSION, 'failures': failures, 'live_models_tested': False})
    return 2 if failures else 0


def setup():
    private_dir(home())
    cfg = settings()
    command, _ = capability('cursor', cfg)
    env = child_env({'CURSOR_CONFIG_DIR': str(cursor_profile())})
    print('Using a separate Cursor CLI profile; your normal Cursor settings are unchanged.')
    result = run([command, 'models'], home(), timeout=60, env=env)
    if result['exit_code'] != 0 or result['reason']:
        print('Cursor needs a login in this profile. This opens the normal account sign-in flow.')
        if input('Open Cursor sign-in now? [y/N] ').strip().lower() != 'y':
            return 2
        code = subprocess.call([command, 'login'], env=env, cwd=home())
        if code:
            raise FlowError('Cursor login did not complete.')
        result = run([command, 'models'], home(), timeout=60, env=env)
    if result['exit_code'] != 0 or result['reason']:
        raise FlowError('Could not list models for this Cursor account: ' + result['stderr'][-1000:])
    text = re.sub(r'\x1b\[[0-9;]*m', '', result['stdout'])
    print(text)
    answer = input('Paste approved model IDs, separated by commas (first is default; choose a non-Claude family first): ').strip()
    roster = list(dict.fromkeys(m.strip() for m in answer.split(',') if m.strip()))
    model = roster[0] if roster else ''
    if not model or not re.fullmatch(r'[A-Za-z0-9._:/-]+', model) or model.lower() in {'auto', 'default'}:
        raise FlowError('A specific model ID is required; no silent Auto selection.')
    if any(s in model.lower() for s in ('claude', 'sonnet', 'opus', 'haiku')):
        raise FlowError('Choose a different family to get an independent perspective from the Claude lead.')
    for entry in roster:
        if not re.fullmatch(r'[A-Za-z0-9._:/-]+', entry) or entry.lower() in {'auto','default'} or not re.search(r'(?<![\w./:-])' + re.escape(entry) + r'(?![\w./:-])', text):
            raise FlowError('An exact model ID was not found in the returned list: ' + entry)
    cfg['cursor_model'] = model
    cfg['cursor_models'] = roster
    save(home() / 'settings.json', cfg)
    save(home() / 'cursor-models.json', {'time': now(), 'output': text, 'selected': model})
    print('Saved. Next: researchflow doctor, then researchflow demo --live')
    return 0


def launch(d, p):
    cfg = settings()
    if not cfg['cursor_model']:
        raise FlowError('Choose your Cursor worker first: researchflow setup')
    command, _ = capability('claude', cfg)
    root = validate_workspace(p)
    # Only one cooperating lead per workspace. Lock remains held while Claude runs.
    with lock(Path(os.environ.get('RESEARCHFLOW_INSTALL_ROOT', '~/.local/share/researchflow')).expanduser() / 'install.lock', shared=True), lock(d / 'session.lock'):
        token = uid()
        save(d / 'session.json', {'token': token, 'pid': os.getpid(), 'started': now()})
        _, text = status(d, p)
        print(text)
        driver = shlex.join([sys.executable, str(PACKAGE / 'researchflow.py'), '--project', p['id']])
        lead = (PACKAGE / 'prompts' / 'lead.md').read_text()
        lead += f'\n\nACTIVE PROJECT\nWorking folder: {root}\nStatus page: {d}/PROJECT_STATUS.md\nTask template: {PACKAGE}/task-template.json\nController command prefix (use exact paths): {driver}\nAll controller subcommands in the instructions follow that prefix. Keep RESEARCHFLOW_HOME and RESEARCHFLOW_PROJECT in child calls.\n'
        write(d / 'lead-prompt.md', lead)
        save(d / 'empty-mcp.json', {'mcpServers': {}})
        save(d / 'lead-settings.json', {'disableAllHooks': True})
        argv = [command, '--append-system-prompt-file', str(d / 'lead-prompt.md'),
                '--setting-sources', '', '--strict-mcp-config', '--mcp-config', str(d / 'empty-mcp.json'),
                '--settings', str(d / 'lead-settings.json'),
                'Read the ResearchFlow instructions and current status. Briefly orient me, then ask for my task unless it is already recorded. Continue through the configured workers rather than asking me to move between tools.']
        env = dict(os.environ)
        for key in list(env):
            if key.startswith('GIT_') or key in {'PYTHONPATH', 'PYTHONHOME', 'CLAUDECODE'}:
                env.pop(key)
        env.update(RESEARCHFLOW_HOME=str(home()), RESEARCHFLOW_PROJECT=p['id'], RESEARCHFLOW_SESSION=token)
        process = subprocess.Popen(argv, cwd=root, env=env)
        try:
            return process.wait()
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            raise
        finally:
            save(d / 'session.json', {'token': token, 'ended': now(), 'pid': None})
            status(d, load(d / 'project.json'), environment_check=False)


def start(path, no_launch=False):
    if path:
        report, _, _ = inspect(path)
        print(f'Original: {report["original"]}\nSource files in scope: {len(report["snapshot"]["manifest"])}')
        print('Unfinished work:\n' + (report['git_status'] or '(none)'))
        print('No project code has run. A separate worktree and a scoped recovery copy will be used.')
        print('Ignored files, datasets and environments are NOT copied. No commit/merge/push is performed.')
        if input('Have you paused other writers and approved copying this non-sensitive source? Type yes: ').strip() != 'yes':
            print('Stopped. Original unchanged.')
            return 2
        d, p = prepare(path)
    else:
        d, p = locate()
    status(d, p, environment_check=False)
    print('Your one status page: ' + str(d / 'PROJECT_STATUS.md'))
    return 0 if no_launch else launch(d, p)


def selftest():
    # Tests inherit no vendor credentials and use temporary fake worker executables.
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(PACKAGE / 'tests'), '-v'],
                            cwd=PACKAGE, env=child_env(), check=False)
    return result.returncode


def demo(live=False):
    if live:
        print('This makes a tiny Claude response, one Cursor call and one Codex review on synthetic code. Account usage/charges may apply.')
        if input('Run the live smoke check? Type yes: ').strip() != 'yes':
            return 2
    directory = home() / 'demos' / uid()
    private_dir(directory.parent)
    shutil.copytree(PACKAGE / 'examples' / 'tiny-research', directory, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    # Only this new disposable example is initialized/committed. Never an inherited project.
    from .project import git
    git(directory, 'init', '-b', 'main')
    git(directory, '-c', 'user.name=ResearchFlow demo', '-c', 'user.email=demo@invalid.example', 'add', '.')
    git(directory, '-c', 'user.name=ResearchFlow demo', '-c', 'user.email=demo@invalid.example', 'commit', '-m', 'Synthetic fixture')
    (directory / 'unfinished.md').write_text('A prior agent left this unfinished. Preserve it.\n')
    d, p = prepare(directory)
    original_settings = settings()
    old_path = os.environ.get('PATH', '')
    settings_file = home() / 'settings.json'
    saved_bytes = settings_file.read_bytes() if settings_file.exists() else None
    try:
        if not live:
            # Mock programs are scripts, not authenticated model calls.
            fake_bin = private_dir(d / 'fake-bin')
            for name in ('agent', 'codex', 'claude'):
                wrapper = fake_bin / name
                wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(PACKAGE / 'tests' / 'fake_worker.py')) + ' ' + name + ' "$@"\n')
                wrapper.chmod(0o700)
            os.environ['PATH'] = str(fake_bin) + os.pathsep + old_path
            cfg = dict(original_settings)
            cfg.update(cursor_model='fake-independent', codex_model='fake-codex', cursor_command='agent', codex_command='codex', claude_command='claude')
            save(settings_file, cfg)
        else:
            cmd, _ = capability('claude', original_settings)
            smoke = run([cmd, '-p', '--tools', '', '--setting-sources', '', '--strict-mcp-config',
                         '--mcp-config', '{"mcpServers":{}}', '--settings', '{"disableAllHooks":true}',
                         'Reply with exactly RESEARCHFLOW_OK. Do not access files or run tools.'], d, timeout=120)
            save(d / 'claude-live-smoke.json', smoke)
            if smoke['exit_code'] != 0 or smoke['reason'] or smoke['stdout'].strip() != 'RESEARCHFLOW_OK':
                raise FlowError('Claude live smoke did not return the expected answer; see claude-live-smoke.json.')
        task = load(PACKAGE / 'examples' / 'tiny-research' / 'demo-task.json')
        task['tests']['python'] = sys.executable
        assign(d, p, task)
        first = baseline(d, p)
        if first['state'] != 'FAIL':
            raise FlowError('The intentionally broken baseline did not fail as expected.')
        opinion = consult(d, p, 'Independently check the normalization contract. What edge cases must be tested?')
        if opinion['state'] != 'RECEIVED':
            raise FlowError(opinion['reason'])
        path = Path(p['workspace']) / 'stats.py'
        path.write_text(path.read_text().replace('return [0.0 for _ in values]  # deliberately wrong fixture',
                                                 'return [(x - low) / (high - low) for x in values]'))
        final = check(d, p)
        result = {'time': now(), 'live': live, 'project': p['id'], 'baseline': first['state'],
                  'candidate': final['state'], 'directory': str(d),
                  'implementation': 'A known fixture patch applied by the demo runner, not by a live coding agent.',
                  'limit': 'A successful smoke tests these CLI calls, not general model reliability or OS confinement.'}
        save(home() / ('live-smoke.json' if live else 'offline-demo.json'), result)
        print(json.dumps(result, indent=2))
        print('Open: ' + str(d / 'PROJECT_STATUS.md'))
        return 0 if final['state'] == 'CHECKED' else 2
    finally:
        os.environ['PATH'] = old_path
        if not live:
            if saved_bytes is None:
                settings_file.unlink(missing_ok=True)
            else:
                write(settings_file, saved_bytes)
            # The restored settings intentionally make this historical fake result stale.
            print('Offline demonstration used fake workers. It is not evidence that your real accounts work.')


def parser():
    p = argparse.ArgumentParser(description='ResearchFlow: talk to Claude; get independent model checks and readable evidence.')
    p.add_argument('--version', action='version', version=VERSION)
    p.add_argument('--project', help='Project ID (normally supplied by the Claude launcher)')
    s = p.add_subparsers(dest='command', required=True)
    for name in ('doctor', 'setup', 'selftest', 'status', 'baseline', 'check', 'rollback'):
        s.add_parser(name)
    a = s.add_parser('start', help='Inspect/preserve a project, then open its Claude session')
    a.add_argument('path', nargs='?')
    a.add_argument('--no-launch', action='store_true', help='Prepare only; useful for manual inspection')
    a = s.add_parser('inspect', help='Local static inventory; no project code or models')
    a.add_argument('path')
    a = s.add_parser('task', help='Record an owner-approved small task and its baseline source')
    a.add_argument('--file', required=True)
    a = s.add_parser('consult', help='Ask the configured Cursor model from Claude')
    a.add_argument('question')
    a.add_argument('--model', help='Use another model from the approved Cursor roster')
    a = s.add_parser('demo')
    a.add_argument('--live', action='store_true')
    a = s.add_parser('feedback', help='Save a plain-language requested framework change')
    a.add_argument('text')
    a = s.add_parser('develop', help='Copy the workflow to a NEW folder for safe editing')
    a.add_argument('destination')
    a = s.add_parser('update', help='Test and install a local new release; keeps previous release')
    a.add_argument('source')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    private_dir(home())
    try:
        if args.command == 'doctor':
            return doctor()
        if args.command == 'setup':
            return setup()
        if args.command == 'selftest':
            return selftest()
        if args.command == 'inspect':
            report, _, _ = inspect(args.path)
            dest = home() / 'inspections' / (uid() + '.json')
            save(dest, report)
            print(json.dumps(report, indent=2))
            print('Inventory saved: ' + str(dest))
            return 0
        if args.command == 'start':
            return start(args.path, args.no_launch)
        if args.command == 'demo':
            return demo(args.live)
        if args.command == 'feedback':
            file = home() / 'feedback.md'
            with lock(home() / 'feedback.lock'):
                prior = file.read_text() if file.exists() else '# Requested workflow changes\n'
                write(file, prior + '\n## ' + now() + '\n' + args.text + '\n')
            print('Saved: ' + str(file))
            return 0
        if args.command == 'develop':
            destination = Path(args.destination).expanduser().resolve()
            if destination.exists():
                raise FlowError('Development destination must be new. Existing work is not overwritten.')
            shutil.copytree(PACKAGE, destination, ignore=shutil.ignore_patterns('__pycache__', '.git', 'evidence'))
            feedback = home() / 'feedback.md'
            if feedback.exists():
                shutil.copy2(feedback, destination / 'REQUESTED_CHANGES.md')
            print(f'Edit only {destination}. Read docs/CHANGING_THE_WORKFLOW.md. Installed code and projects are unchanged.')
            return 0
        if args.command in {'update', 'rollback'}:
            command = [sys.executable, str(PACKAGE / 'install.py')]
            command += ['--source', str(Path(args.source).expanduser().resolve())] if args.command == 'update' else ['--rollback']
            return subprocess.call(command)
        d, p = locate(args.project)
        with operation(d):
            p = load(d / 'project.json')
            if args.command == 'task':
                print('Recorded task ' + assign(d, p, load(Path(args.file))))
                return 0
            if args.command == 'status':
                state, text = status(d, p)
                print(text)
                return 0 if state == 'CHECKED' else 2
            action = {'baseline': baseline, 'check': check, 'consult': consult}[args.command]
            r = action(d, p, args.question, args.model) if args.command == 'consult' else action(d, p)
            print(r.get('answer', r['state'] + ': ' + r['reason']))
            print('Status: ' + str(d / 'PROJECT_STATUS.md'))
            return 0 if r['state'] in {'PASS', 'RECEIVED', 'CHECKED'} else 2
    except FlowError as exc:
        print('STOPPED: ' + str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Interrupted. Existing work and records were preserved.', file=sys.stderr)
        return 130
    except OSError as exc:
        print('File/process error: ' + str(exc) + '. No automatic cleanup was attempted.', file=sys.stderr)
        return 2
