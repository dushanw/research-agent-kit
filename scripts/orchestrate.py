#!/usr/bin/env python3
"""Human-gated Claude implementation -> local test -> read-only Codex review.

No automatic commits, merges, pushes, deletions, or reparative edits.
"""
import argparse
import datetime as dt
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


def cmd(argv, cwd, log=None, check=True, env=None):
    result = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env)
    if log:
        Path(log).write_text(result.stdout, encoding='utf-8')
    if check and result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {shlex.join(argv)}\n{result.stdout[-1800:]}")
    return result


def git(root, *args):
    return cmd(['git', *args], root).stdout.strip()


def safe_slug(value):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,48}', value):
        raise ValueError('Task ID must be letters/numbers/underscores/hyphens (max 49 chars)')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['doctor', 'prepare', 'run'])
    parser.add_argument('--id', default='normalization')
    parser.add_argument('--test-command', default='python3 -m pytest -q',
                        help='Shell syntax parsed with shlex; no shell expansion')
    parser.add_argument('--skip-tests', action='store_true', help='Review only; not merge-ready')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    repo = Path(git(root, 'rev-parse', '--show-toplevel')).resolve()
    if root != repo:
        raise RuntimeError('Kit must be installed in the main repository root')
    required = ['git', 'python3', 'claude', 'codex']
    print('Available commands:')
    for name in required + ['cursor', 'agent', 'cursor-agent']:
        print(f'  {name}: {shutil.which(name) or "NOT FOUND"}')
    print('Worktrees:\n' + git(root, 'worktree', 'list'))
    if args.action == 'doctor':
        print('Docs:', *(f'{p}={Path(root,p).exists()}' for p in
                          ['AGENTS.md','CLAUDE.md','tasks/current.md']), sep='\n  ')
        return
    for name in required:
        if not shutil.which(name):
            raise RuntimeError(f'{name} missing from PATH; run doctor and install/sign in first')
    if git(root, 'status', '--porcelain'):
        raise RuntimeError('Main repository has uncommitted/untracked files; commit/clean deliberately first')
    if not (root/'tasks/current.md').is_file():
        raise RuntimeError('Missing tasks/current.md')
    task_id = safe_slug(args.id)
    branch = 'agent/' + task_id
    worktree = repo.parent / f'{repo.name}-agent-{task_id}'
    if args.action == 'prepare':
        if worktree.exists() or git(root, 'branch', '--list', branch):
            raise RuntimeError('Worktree or branch already exists; use a new --id')
        cmd(['git','worktree','add','-b', branch, str(worktree),'HEAD'],root)
        print('Prepared:', worktree)
        print('Setup .venv inside worktree; then run with action=run')
        return
    if not worktree.is_dir():
        raise RuntimeError('No worktree: use prepare first')
    if git(worktree,'branch','--show-current') != branch:
        raise RuntimeError('Unexpected branch for task worktree')
    if git(worktree,'status','--porcelain'):
        raise RuntimeError('Worktree not clean before implementation; resolve manually')
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    logs = repo/'.agent-runs'/f'{task_id}-{stamp}'
    logs.mkdir(parents=True,exist_ok=False)
    try:
        print('Implementing in:', worktree)
        prompt = ('Read AGENTS.md, CLAUDE.md, and tasks/current.md. Implement the task '
                  'and its synthetic-data tests in this worktree only. Do not commit, push, '
                  'merge, delete datasets, or operate outside this worktree. '
                  'Do not fabricate test or research results. Summarize edits and risks.')
        cmd(['claude','-p','--permission-mode','acceptEdits',prompt],worktree,
            logs/'claude.txt')
        diff = git(worktree,'diff','HEAD','--')
        new_files = git(worktree,'ls-files','--others','--exclude-standard')
        if not diff and not new_files:
            raise RuntimeError('Claude produced no visible file changes')
        (logs/'diff.txt').write_text(diff + '\nUNTRACKED FILES:\n'+new_files+'\n')
        if args.skip_tests:
            (logs/'tests.txt').write_text('SKIPPED BY OPERATOR: not merge-ready\n')
        else:
            print('Running checks:', args.test_command)
            cmd(shlex.split(args.test_command),worktree,logs/'tests.txt')
        before = git(worktree,'status','--porcelain') + git(worktree,'diff','HEAD','--')
        print('Read-only Codex review...')
        review_prompt = ('Independently review all changes against HEAD, including untracked '
                         'files, with reference to AGENTS.md and tasks/current.md. '
                         'Find correctness, scientific reproducibility, privacy, security, '
                         'edge-case and test-coverage problems. Do not modify files. '
                         'Return numbered findings with severity, file locations and evidence. '
                         'State when evidence is insufficient.')
        cmd(['codex','exec','--sandbox','read-only',review_prompt],worktree,logs/'codex.txt')
        after = git(worktree,'status','--porcelain') + git(worktree,'diff','HEAD','--')
        if before != after:
            raise RuntimeError('Review changed Git state: inspect manually before proceeding')
        (logs/'STATUS.txt').write_text('COMPLETED: HUMAN REVIEW REQUIRED; NO MERGE OR COMMIT\n')
        print('Complete. Review logs in:',logs)
        print('Inspect change: git -C',shlex.quote(str(worktree)),'diff HEAD')
        print('Untracked files: git -C',shlex.quote(str(worktree)),'ls-files --others --exclude-standard')
        print('Review with Cursor; no automatic merge.')
    except Exception as exc:
        (logs/'STATUS.txt').write_text('STOPPED: '+str(exc)+'\n')
        print('STOPPED:',exc, file=sys.stderr)
        print('Logs:',logs, file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
