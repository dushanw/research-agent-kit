# Research Multi-Agent Kit (macOS)

**Agents:** Claude Code implements in an isolated Git worktree; Python test gate runs locally; Codex conducts a read-only review; Cursor is the interactive human approval station. Nothing is automatically committed, pushed, or merged.

## 1. Prerequisites
Install Xcode command line tools (`xcode-select --install`) if Git is missing; install Python 3.10+ and Node.js/npm with your preferred package manager.

Install Codex: `npm install -g @openai/codex@latest`; then run `codex` once and sign in.
Check Claude: `claude --version` and sign in interactively with `claude`.
Cursor IDE: install and open the project normally. Cursor's optional terminal CLI: see https://cursor.com/docs/cli/overview and run `agent login` after installing.

## 2. Add to an EXISTING committed Git repository
Run from the repo root:

```bash
unzip -n /path/to/research-agent-kit.zip -d .
git status --short
# Review the additions. Never overwrite your existing AGENTS.md, CLAUDE.md, etc.
git add AGENTS.md CLAUDE.md .cursor docs tasks scripts .gitignore README.md
git commit -m 'Configure research agent workflow'
```

If the repository already has any of these files, merge their contents by hand. `unzip -n` skips existing files. Prefer starting in a new throwaway repo before applying to important research software.

## 3. Verify and prepare task

```bash
python3 scripts/orchestrate.py doctor
python3 scripts/orchestrate.py prepare --id normalize01
# A sibling worktree was created. Set up its independent Python environment:
cd ../YOUR_REPO_NAME-agent-normalize01
python3 -m venv .venv
# Adjust dependencies to your project's pyproject.toml:
.venv/bin/python -m pip install -e '.[dev]'
```

If your project has no `pyproject.toml` or `dev` extra, install only needed project dependencies plus pytest; use the explicit `.venv/bin/python -m pytest -q` command when running.

## 4. Orchestrate

```bash
cd ../YOUR_REPO_NAME
python3 scripts/orchestrate.py run --id normalize01 \
  --test-command '.venv/bin/python -m pytest -q'
```

Automation captures the implementation, tests, diff and review in `.agent-runs/<id>-<timestamp>/` (ignored by Git). Stop and fix environment/test issues if anything fails. A review completed without an exception does NOT mean that the review was favorable; read the Codex findings.

## 5. Review in Cursor; manually integrate

Open the sibling worktree in Cursor and inspect all changes including untracked files. Read `.agent-runs/.../codex.txt` from the original repo. Address findings in the worktree and re-run tests and review manually (the script intentionally will not rerun on a dirty worktree). Once approved, stage and commit changes *in the worktree*; then merge into the target branch after reviewing the commit. Do not merge an uncommitted working tree.

Example:

```bash
cd ../YOUR_REPO_NAME-agent-normalize01
git status --short
git diff HEAD
# Review each new untracked file too
git add -p
# New files must be added individually after review:
# git add src/approved_new_file.py tests/test_approved_new_file.py
git diff --cached --check
git diff --cached
git commit -m 'Add deterministic normalization helper'
# Then, in original repo, verify target branch and clean status before merge:
cd ../YOUR_REPO_NAME
git status --short
git branch --show-current
git merge --no-ff agent/normalize01
```

## Safety boundaries
- Git worktrees isolate checked-out files, not all runtime effects. Use separate `.venv` folders, unique ports, separate run directories, and do not point agents to writable shared datasets.
- Claude `acceptEdits` mode allows automatic file edits; tool and command permission behavior may vary with local settings. Use a container or other OS sandbox for untrusted repositories. Never use `--dangerously-skip-permissions`.
- Codex is explicitly read-only but may still see locally accessible data; do not run agents with private/regulated research data in scope.
- Reviews and test results are evidence, not proof. Scientific claims require expert validation.
- The orchestrator does not automatically repair findings or integrate branches; approval is a deliberate human gate.
