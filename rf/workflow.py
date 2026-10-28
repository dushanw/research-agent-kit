"""Task -> baseline -> Cursor opinion -> tests -> Codex review -> readable handoff.

This module records observations, not human approval. It never integrates Git
changes. Claude is the interactive coordinator; ordinary tool permissions remain.
"""
from __future__ import annotations
import contextlib
import difflib
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
from . import VERSION
from .support import FlowError, digest, home, identity, load, lock, now, private_dir, run, save, uid, within, write
from .project import capture, put_snapshot, validate_workspace
from .providers import screen, settings, worker

PACKAGE = Path(__file__).resolve().parent.parent
RUNNER = PACKAGE / 'rf' / 'test_runner.py'

@contextlib.contextmanager
def operation(directory):
    # A cooperating second terminal may not work while the main Claude session owns it.
    session_file = directory / 'session.json'
    if session_file.exists():
        owner = load(session_file)
        if owner.get('token') != os.environ.get('RESEARCHFLOW_SESSION'):
            with lock(directory / 'session.lock'):
                pass
    with lock(directory / 'operation.lock'):
        yield

def controller_id():
    files = list((PACKAGE / 'rf').glob('*.py')) + list((PACKAGE / 'prompts').glob('*.md'))
    return identity({str(p.relative_to(PACKAGE)): digest(p.read_bytes()) for p in sorted(files)})

def task_dir(d, p):
    if not p.get('task_id'):
        raise FlowError('No task yet. Claude should write the short task contract and call researchflow task --file FILE.')
    return d / 'tasks' / p['task_id']

def validate_task(t, root):
    keys = {'schema', 'goal', 'why', 'allowed_paths', 'tests', 'example', 'artifacts', 'context', 'limits'}
    if not isinstance(t, dict) or set(t) != keys or t['schema'] != 1:
        raise FlowError('Task must use the supplied task-template.json fields; no unknown fields.')
    for name in ('goal', 'why', 'limits'):
        if not isinstance(t[name], str) or not t[name].strip():
            raise FlowError('Task needs plain-language ' + name)
    for name in ('allowed_paths', 'artifacts', 'context'):
        if not isinstance(t[name], list) or not all(isinstance(x, str) for x in t[name]):
            raise FlowError('Task path lists must contain relative paths.')
        for rel in t[name]:
            within(root, rel)
    if not t['allowed_paths']:
        raise FlowError('Specify the files/directories this task may change.')
    if not isinstance(t['tests'], dict) or set(t['tests']) != {'kind', 'directory', 'python', 'minimum'}:
        raise FlowError('tests needs kind, directory, python, and minimum.')
    tests = t['tests']
    if tests['kind'] not in {'unittest', 'pytest'} or type(tests['minimum']) is not int or tests['minimum'] < 1:
        raise FlowError('Use unittest or pytest and require at least one executed test.')
    within(root, tests['directory'])
    if not isinstance(tests['python'], str) or not tests['python'] or '\0' in tests['python']:
        raise FlowError('Specify one Python interpreter, not a shell command.')
    if t['example'] is not None:
        if not isinstance(t['example'], dict) or set(t['example']) != {'script', 'args'}:
            raise FlowError('example is null or {"script": "demo.py", "args": []}.')
        within(root, t['example']['script'])
        if not isinstance(t['example']['args'], list) or not all(isinstance(x, str) for x in t['example']['args']):
            raise FlowError('Example arguments must be literal strings.')
    for rel in t['artifacts']:
        if not rel.startswith('outputs/'):
            raise FlowError('Put verified result artifacts under outputs/ in the disposable execution copy.')
    if t['artifacts'] and t['example'] is None:
        raise FlowError('Expected artifacts require an example script to generate them.')
    screen(json.dumps(t))

def assign(d, p, t):
    root = validate_workspace(p)
    validate_task(t, root)
    snap, raw = capture(root)
    # A new task is an explicit contract change, not an automatic way to reset a failed gate.
    tid = uid()
    td = private_dir(d / 'tasks' / tid)
    save(td / 'task.json', t)
    save(td / 'base-manifest.json', snap)
    put_snapshot(td / 'base-source', raw, snap['manifest'])
    p.update(task_id=tid, latest=None, baseline=None, consult=None, worker_calls=0, check_attempts=0)
    save(d / 'project.json', p)
    status(d, p, environment_check=False)
    return tid

def interpreter(root, task):
    value = task['tests']['python']
    if '/' in value:
        target = Path(value).expanduser()
        if not target.is_absolute():
            target = root / target
        # Venv interpreters are commonly symlinks to an approved system interpreter.
        if not target.is_file() or not os.access(target, os.X_OK):
            raise FlowError(f'Python environment is missing: {target}. Ask Claude to set it up after inspecting dependencies.')
        return str(target.absolute())  # Do not resolve a venv symlink: it changes sys.prefix.
    found = shutil.which(value)
    if not found:
        raise FlowError('Python interpreter is not on PATH: ' + value)
    return found

def environment(root, task):
    exe = interpreter(root, task)
    r = run([exe, '-I', '-B', str(RUNNER), 'environment'], root, timeout=30)
    if r['exit_code'] != 0 or r['reason']:
        raise FlowError('Could not identify the approved Python environment.')
    try:
        value = json.loads(r['stdout'])
    except ValueError as exc:
        raise FlowError('Python environment record is malformed.') from exc
    return value

def test_gate(result, process, minimum):
    fields = {'tests', 'failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes', 'test_ids'}
    if not isinstance(result, dict) or set(result) != fields:
        return 'BLOCKED', 'Required structured test evidence is missing or malformed.'
    if any(type(result[k]) is not int or result[k] < 0 for k in fields - {'test_ids'}):
        return 'BLOCKED', 'Test counts are invalid.'
    if not isinstance(result['test_ids'], list) or len(result['test_ids']) != result['tests'] or not all(isinstance(x, str) for x in result['test_ids']):
        return 'BLOCKED', 'Test identity/count evidence is inconsistent.'
    if process['reason']:
        return 'FAIL', 'Test process did not finish: ' + process['reason']
    if result['failures'] or result['errors'] or result['unexpected_successes'] or process['exit_code'] != 0:
        return 'FAIL', 'The recorded test execution failed.'
    if result['tests'] < minimum or result['skipped'] or result['expected_failures']:
        return 'BLOCKED', 'Required tests were missing, skipped, or marked as expected failures.'
    return 'PASS', f"{result['tests']} tests executed; none failed or were skipped."

def execute_checks(root, task, record_dir, snap, raw):
    cfg = settings()
    execution = private_dir(record_dir / 'execution')
    put_snapshot(execution, raw, snap['manifest'])
    env = environment(root, task)
    save(record_dir / 'environment.json', env)
    result_file = record_dir / 'test-results.json'
    argv = [interpreter(root, task), '-I', '-B', str(RUNNER), task['tests']['kind'],
            '--root', str(execution), '--tests', task['tests']['directory'], '--output', str(result_file)]
    process = run(argv, execution, timeout=cfg['test_timeout'])
    save(record_dir / 'test-process.json', process)
    results = load(result_file) if result_file.is_file() else None
    state, reason = test_gate(results, process, task['tests']['minimum'])
    outputs = {}
    if state == 'PASS' and task['example']:
        # No old outputs were copied into execution; artifact existence is from this run.
        script = within(execution, task['example']['script'])
        if not script.is_file():
            state, reason = 'BLOCKED', 'The configured example script is missing.'
        else:
            argv = [interpreter(root, task), '-I', '-B', str(RUNNER), 'example',
                    '--root', str(execution), '--script', task['example']['script'], '--', *task['example']['args']]
            result = run(argv, execution, timeout=cfg['test_timeout'])
            save(record_dir / 'example-process.json', result)
            if result['exit_code'] != 0 or result['reason']:
                state, reason = 'FAIL', 'The representative example failed; inspect example-process.json.'
            else:
                for rel in task['artifacts']:
                    target = within(execution, rel)
                    if not target.is_file() or target.is_symlink() or target.stat().st_size == 0:
                        state, reason = 'BLOCKED', 'Required output is missing or empty: ' + rel
                        break
                    if target.stat().st_size > 50_000_000:
                        state, reason = 'BLOCKED', 'Output exceeds the 50 MB verification limit: ' + rel
                        break
                    outputs[rel] = {'path': str(target), 'sha256': digest(target.read_bytes())}
    after, _ = capture(execution)
    if after['id'] != snap['id']:
        state, reason = 'BLOCKED', 'Tests/example modified the source snapshot. Outputs must go in outputs/.'
    return {'state': state, 'reason': reason, 'results': results, 'environment_id': identity(env),
            'artifacts': outputs, 'command': argv}

def record(d, p, kind, task, snap):
    rd = private_dir(task_dir(d, p) / 'runs' / (uid() + '-' + kind))
    r = {'kind': kind, 'started': now(), 'state': 'RUNNING', 'reason': 'Operation has not completed.',
         'task_id': p['task_id'], 'task_hash': identity(task), 'snapshot': snap['id'],
         'version': VERSION, 'controller_id': controller_id(), 'settings_id': identity(settings()),
         'directory': str(rd), 'gates': None, 'artifacts': {}, 'integrated': False}
    save(rd / 'record.json', r)
    save(rd / 'source-manifest.json', snap)
    return rd, r

def seal(rd, r):
    r['ended'] = now()
    names = ['test-process.json', 'test-results.json', 'example-process.json', 'environment.json',
             'review/final.json', 'review/process.json', 'cursor/process.json', 'cursor/answer.md']
    r['evidence_hashes'] = {name: digest((rd / name).read_bytes()) for name in names if (rd / name).is_file()}
    save(rd / 'record.json', r)

def baseline(d, p):
    td = task_dir(d, p)
    task = load(td / 'task.json')
    root = validate_workspace(p)
    snap = load(td / 'base-manifest.json')
    _, raw = capture(td / 'base-source')
    rd, r = record(d, p, 'baseline', task, snap)
    p['baseline'] = str(rd)
    save(d / 'project.json', p)
    try:
        r['gates'] = execute_checks(root, task, rd, snap, raw)
        r.update(state=r['gates']['state'], reason=r['gates']['reason'])
    except (FlowError, OSError, ValueError) as exc:
        r.update(state='BLOCKED', reason=str(exc))
    except BaseException:
        r.update(state='INTERRUPTED', reason='Interrupted baseline; preserved all records.')
        raise
    finally:
        seal(rd, r)
        status(d, p, environment_check=False)
    return r

def reserve_call(d, p):
    if p.get('worker_calls', 0) >= settings()['max_worker_calls']:
        raise FlowError('Worker-call budget reached. Stop and ask the owner before extending the task.')
    p['worker_calls'] = p.get('worker_calls', 0) + 1
    save(d / 'project.json', p)

def context_text(task, raw):
    blocks = []
    for rel in task['context']:
        if rel not in raw:
            raise FlowError('Requested context file is missing or excluded: ' + rel)
        try:
            text = raw[rel].decode('utf8')
        except UnicodeDecodeError as exc:
            raise FlowError('Use extracted, approved text for worker context: ' + rel) from exc
        blocks.append(f'\n--- SOURCE {rel} ---\n{text}')
    return ''.join(blocks)

def consult(d, p, question, model=None):
    td = task_dir(d, p)
    task = load(td / 'task.json')
    root = validate_workspace(p)
    snap, raw = capture(root)
    rd, r = record(d, p, 'consult', task, snap)
    p['consult'] = str(rd)
    save(d / 'project.json', p)
    selected = settings()
    if model is not None:
        if model not in (selected['cursor_models'] or [selected['cursor_model']]):
            r.update(state='BLOCKED', reason='That Cursor model is not in your approved roster. Change it with researchflow setup, not a silent substitution.')
            seal(rd, r)
            return r
        selected['cursor_model'] = model
    packet = 'INDEPENDENT METHOD CHECK\nExplain assumptions, mismatches, missing source evidence and one recommended next step. Do not merely endorse the lead agent. Do not execute code.\n'
    packet += '\nTASK CONTRACT\n' + json.dumps(task, indent=2) + '\nQUESTION\n' + question + context_text(task, raw)
    try:
        screen(packet)
        reserve_call(d, p)
        answer = worker('cursor', packet, rd / 'cursor', selected)
        if capture(root)[0]['id'] != snap['id']:
            raise FlowError('Implementation changed while Cursor was inspecting its packet.')
        r.update(state='RECEIVED', reason='Independent Cursor answer recorded; this is advice, not test evidence.', answer=answer)
    except (FlowError, OSError, ValueError) as exc:
        r.update(state='BLOCKED', reason=str(exc))
    except BaseException:
        r.update(state='INTERRUPTED', reason='Interrupted Cursor call; no completed opinion recorded.')
        raise
    finally:
        seal(rd, r)
        status(d, p, environment_check=False)
    return r

def review_packet(task, base, candidate, gates):
    pieces = ['Review this bounded research change independently. Do not execute code or edit files. Return exactly the JSON schema provided. Report correctness errors, weakened tests, invalid scientific assumptions and claims exceeding evidence. Set evidence_sufficient=false when the supplied context cannot support review. Never treat model agreement as proof.\n',
              'TASK\n' + json.dumps(task, indent=2), '\nRUNNER OBSERVATIONS\n' + json.dumps(gates, indent=2)]
    for name in sorted(set(base) | set(candidate)):
        if base.get(name) == candidate.get(name):
            continue
        try:
            before = base.get(name, b'').decode('utf8')
            after = candidate.get(name, b'').decode('utf8')
        except UnicodeDecodeError as exc:
            raise FlowError('A changed binary cannot be reviewed by this text workflow: ' + name) from exc
        # Deleted lines are intentionally included and screened too.
        pieces.append('\n' + ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                                        fromfile='before/' + name, tofile='after/' + name)))
    pieces.append(context_text(task, candidate))
    text = '\n'.join(pieces)
    screen(text)
    return text

def check(d, p):
    td = task_dir(d, p)
    task = load(td / 'task.json')
    root = validate_workspace(p)
    validate_task(task, root)
    if not p.get('baseline'):
        raise FlowError('Run the approved baseline before implementation: researchflow baseline')
    br = load(Path(p['baseline']) / 'record.json')
    if br['state'] not in {'PASS', 'FAIL'}:
        raise FlowError('The baseline was not executable. Resolve its setup/blocker before checking a candidate.')
    if p.get('check_attempts', 0) >= settings()['max_check_attempts']:
        raise FlowError('Three check attempts (initial plus two repairs by default) are used. Stop and show the owner what is unresolved.')
    snap, raw = capture(root)
    rd, r = record(d, p, 'check', task, snap)
    p['latest'] = str(rd)
    p['check_attempts'] = p.get('check_attempts', 0) + 1
    save(d / 'project.json', p)
    try:
        _, base = capture(td / 'base-source')
        changes = sorted(n for n in set(base) | set(raw) if base.get(n) != raw.get(n))
        r['changes'] = changes
        for name in changes:
            if not any(name == a or name.startswith(a.rstrip('/') + '/') for a in task['allowed_paths']):
                raise FlowError('Change outside the approved task scope: ' + name)
        r['gates'] = execute_checks(root, task, rd, snap, raw)
        if r['gates']['state'] != 'PASS':
            r.update(state=r['gates']['state'], reason=r['gates']['reason'])
            return r
        baseline_ids = set((br.get('gates') or {}).get('results', {}).get('test_ids', []))
        required_ids = {x for x in baseline_ids if '_FailedTest' not in x}
        current_ids = set(r['gates']['results']['test_ids'])
        if not required_ids.issubset(current_ids):
            raise FlowError('Existing test identities disappeared. Resolve with the owner, not by quietly reducing coverage.')
        # A worker cannot turn a no-test/failed-test run green.
        if not p.get('consult') or load(Path(p['consult']) / 'record.json')['state'] != 'RECEIVED':
            raise FlowError('No completed independent method check. Ask Cursor with researchflow consult, then recheck.')
        r['consult_directory'] = p['consult']
        r['baseline_directory'] = p['baseline']
        packet = review_packet(task, base, raw, r['gates'])
        reserve_call(d, p)
        verdict = worker('codex', packet, rd / 'review', settings())
        r['review'] = verdict
        if not verdict['evidence_sufficient'] or any(x['severity'] in {'medium', 'high', 'critical'} for x in verdict['findings']):
            r.update(state='NEEDS_ATTENTION', reason='Codex identified unresolved findings or insufficient evidence. See review/final.json.')
        else:
            r.update(state='CHECKED', reason='Required checks ran and review completed. Human inspection and integration are still required.')
        r['artifacts'] = r['gates']['artifacts']
        if (capture(root)[0]['id'] != snap['id'] or identity(environment(root, task)) != r['gates']['environment_id']
                or identity(load(td / 'task.json')) != r['task_hash']
                or identity(settings()) != r['settings_id'] or controller_id() != r['controller_id']):
            r.update(state='STALE', reason='Source, task, workflow settings or environment changed during verification. The result does not validate the current workspace.')
    except (FlowError, OSError, ValueError) as exc:
        r.update(state='BLOCKED', reason=str(exc))
    except BaseException:
        r.update(state='INTERRUPTED', reason='Interrupted check. Partial work and evidence are preserved; no successful handoff.')
        raise
    finally:
        seal(rd, r)
        status(d, p, environment_check=False)
    return r

def freshness(r, task, root, environment_check=True):
    if r['task_hash'] != identity(task) or r['snapshot'] != capture(root)[0]['id']:
        return 'Source or task contract changed.'
    if r['controller_id'] != controller_id() or r['settings_id'] != identity(settings()):
        return 'Workflow code, instructions or model settings changed.'
    for rel, expected in r.get('evidence_hashes', {}).items():
        file = Path(r['directory']) / rel
        if not file.is_file() or file.is_symlink() or digest(file.read_bytes()) != expected:
            return 'Evidence was removed or changed: ' + rel
    for rel, item in r.get('artifacts', {}).items():
        f = Path(item['path'])
        if not f.is_file() or f.is_symlink() or digest(f.read_bytes()) != item['sha256']:
            return 'Verified output was removed or changed: ' + rel
    if environment_check and r.get('gates') and r['gates'].get('environment_id'):
        if identity(environment(root, task)) != r['gates']['environment_id']:
            return 'Python environment changed.'
    return None

def status(d, p, environment_check=True):
    root = validate_workspace(p)
    lines = ['# Project status', '', f'Working folder: `{root}`', f'Original (not edited): `{p["original"]}`',
             f'Branch: `{p["branch"]}`', 'Owner: one Claude session; other models only advise/review.', '']
    state = 'NOT_RUN'
    if p.get('task_id'):
        task = load(task_dir(d, p) / 'task.json')
        lines += ['**Task:** ' + task['goal'], '**Why:** ' + task['why']]
        if p.get('latest'):
            r = load(Path(p['latest']) / 'record.json')
            try:
                stale = freshness(r, task, root, environment_check)
                if r.get('consult_directory') and r['consult_directory'] != p.get('consult'):
                    stale = 'The independent method-check record changed after verification.'
                if r.get('baseline_directory') and r['baseline_directory'] != p.get('baseline'):
                    stale = 'The recorded baseline changed after verification.'
            except (FlowError, OSError) as exc:
                stale = 'Could not establish current validity: ' + str(exc)
            state = 'STALE' if stale else r['state']
            lines += [f'**Current result: {state}.** ' + (stale or r['reason']),
                      f'Checked source: `{r["snapshot"][:16]}` at {r.get("ended", r["started"])}',
                      f'Evidence: `{p["latest"]}`']
            if r.get('gates') and r['gates'].get('results'):
                x = r['gates']['results']
                lines.append(f'Tests: {x["tests"]} collected, {x["failures"]} failures, {x["errors"]} errors, {x["skipped"]} skipped.')
            changes = r.get('changes', [])
            lines.append('Changed files: ' + (', '.join(changes[:8]) or 'none') + (f' (+{len(changes)-8} more; see record.json)' if len(changes) > 8 else ''))
            for name, item in r.get('artifacts', {}).items():
                lines.append(f'Result {name}: `{item["path"]}`' + (' (stale/unverified now)' if stale else ''))
        else:
            lines.append('**Current result: NOT_RUN.** No candidate verification has completed.')
        if p.get('baseline'):
            b = load(Path(p['baseline']) / 'record.json')
            lines.append(f'Baseline: **{b["state"]}** — {b["reason"]} Evidence: `{p["baseline"]}`')
        else:
            lines.append('Baseline: NOT_RUN. Do not claim the inherited project works.')
        if p.get('consult'):
            c = load(Path(p['consult']) / 'record.json')
            lines.append(f'Cursor method check: {c["state"]}; `{p["consult"]}/cursor/answer.md` (opinion, not proof).')
        lines += ['Not verified: scientific conclusions, private/full datasets, and anything outside the task contract.',
                  'Research limits: ' + task['limits'],
                  'Run again (from the working folder, after checking the code/environment): `researchflow check`']
        lines.append('Next: ' + ('Inspect the output/diff and decide whether to keep the change. Nothing was merged.' if state == 'CHECKED' else 'Resolve the displayed blocker, then run the next bounded check; do not broaden the task silently.'))
    else:
        lines += ['**Current result: NOT_RUN.** Source was inventoried and preserved; no project code has been executed.',
                  'Next: Claude explains the research purpose, key files and proposed first milestone before editing.']
    lines += ['', f'Recovery scope and exclusions: `{d}/recovery/READ_ME.md`',
              'This page is refreshed by ResearchFlow commands. Run `researchflow status` after outside edits; an unopened Markdown file cannot update itself.',
              'CHECKED is evidence for a bounded task, not approval or proof of scientific validity.']
    text = '\n'.join(lines) + '\n'
    write(d / 'PROJECT_STATUS.md', text)
    return state, text
