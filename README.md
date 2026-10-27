# Research Multi-Agent Kit (macOS), v2

**Agents:** Claude Code implements in an isolated Git worktree. The orchestrator runs your
test command locally as a separate gate. Codex reviews read-only as an independent gate.
**You** triage in Cursor and record the decision. Nothing is ever committed, pushed or
merged automatically: `decide --approve` must be typed by a human in a terminal, and even
then the merge commands are only printed.

```
prepare ──► run: implement (Claude) ─► tests ─► review (Codex) ─► awaiting_decision ─► decide (human)
                │ fail/timeout/Ctrl-C ─► failed / interrupted (inspectable, never "success")
                └─ fix in worktree ─► verify: tests ─► review ─► awaiting_decision ...
approved ─► you commit in the worktree ─► check-promotion (read-only) ─► you merge by hand
```

What is and is not tested: [docs/development.md](docs/development.md). Design and state
machine: [docs/orchestrator.md](docs/orchestrator.md). Trust boundaries:
[docs/security-and-privacy.md](docs/security-and-privacy.md). Audit of v1: [docs/AUDIT.md](docs/AUDIT.md).

## 1. Prerequisites (macOS, Apple silicon or Intel)

```bash
xcode-select --install          # Git and Python 3.9 if missing (skip if already installed)
git --version                   # need >= 2.36
python3 --version               # need >= 3.9 (the system 3.9.6 works)
npm install -g @openai/codex@latest
codex                           # sign in interactively once, then quit
claude --version                # install Claude Code first if missing, then:
claude                          # sign in interactively once, then quit
```

Cursor IDE is used interactively. Its optional `agent` CLI is not used by this kit.
Never use `--dangerously-skip-permissions`; the orchestrator never passes it.

## 2. Try it first in a disposable sandbox (recommended)

```bash
cd /path/to/research-agent-kit
python3 -m unittest discover -s scripts/tests -v          # offline; fake CLIs; ~35 s
python3 scripts/make_sandbox.py ~/agent-sandbox            # refuses if the path exists
cd ~/agent-sandbox
python3 scripts/orchestrate.py doctor
python3 scripts/orchestrate.py prepare --id demo1
cd ../agent-sandbox-agent-demo1 && python3 -m venv .venv && cd ../agent-sandbox
python3 scripts/orchestrate.py run --id demo1 --test-command '.venv/bin/python -m unittest discover -s tests -t .'
```

The sandbox contains only the kit and a synthetic example package
([examples/research_demo](examples/research_demo)). That last command calls your real,
signed-in Claude and Codex.

## 3. Add the kit to an EXISTING committed repository

From the kit folder, copy without overwriting anything you already have:

```bash
REPO=/path/to/your/repo
rsync -a --ignore-existing --exclude .git --exclude examples --exclude README.md --exclude __pycache__ ./ "$REPO"/
cp -n README.md "$REPO"/docs/AGENT_WORKFLOW.md
cd "$REPO"
git status --short
```

If you already had `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `.cursor/rules/workflow.mdc`
or `docs/*.md`, rsync kept **yours**: merge the kit's versions in by hand. The one
required line is `.agent-runs/` in `.gitignore` (doctor checks it). Then:

```bash
git diff; git status --short          # review every addition
git add AGENTS.md CLAUDE.md .cursor docs tasks scripts .gitignore
git commit -m 'Add human-gated research agent workflow'
python3 scripts/orchestrate.py doctor
```

## 4. Production use

1. Write the task: `cp tasks/TEMPLATE.md tasks/current.md`, fill every section, then
   `git add tasks/current.md && git commit -m 'Task: ...'`.
2. Prepare an isolated worktree bound to that exact task text (sha256 snapshot):
   ```bash
   python3 scripts/orchestrate.py prepare --id norm01
   ```
3. Give the worktree its own environment (never share the main checkout's venv):
   ```bash
   cd ../YOUR_REPO-agent-norm01
   python3 -m venv .venv
   .venv/bin/python -m pip install -e '.[dev]'   # or your project's install steps
   cd ../YOUR_REPO
   ```
4. Run implementation, then tests, then review:
   ```bash
   python3 scripts/orchestrate.py run --id norm01 --test-command '.venv/bin/python -m pytest -q'
   ```
   Exit codes: `0` = ready for your decision, `3` = finished but blocked (skipped tests,
   blocking findings, unparsed verdict), `1` = failed, `130` = interrupted.
5. Read `.agent-runs/runs/<run-id>/summary.md` (the human summary for Cursor) and
   `review.log`. `run.json` is the machine-readable record.

The test command is split with `shlex` and executed **without a shell**: `$VARS`, globs,
`;`, `|` and `&&` are passed through literally. Use the worktree's `.venv/bin/python` so the
worktree's code is what gets tested. `PYTHONPATH`, `VIRTUAL_ENV`, `PYTHONHOME` and `GIT_DIR`
are removed from the test environment, and `PYTHONHASHSEED=0` is set unless you set it.

## 5. Review, decide, and merge (all manual)

```bash
cd ../YOUR_REPO-agent-norm01 && cursor .           # or open the folder in Cursor
git status --short --untracked-files=all
git diff <base-commit>                              # base commit is in summary.md
cd ../YOUR_REPO
python3 scripts/orchestrate.py status --id norm01 --run latest
# Approve: interactive TTY only; you type 8 chars of the verified tree id.
python3 scripts/orchestrate.py decide --run <run-id> --approve --reviewer "$USER" --note 'Read diff + review'
#   + --override-findings '<why high/critical findings are acceptable>'  when blocked by findings
#   + --acknowledge-warnings                                             when warnings were listed
# Or reject:
python3 scripts/orchestrate.py decide --run <run-id> --reject --reviewer "$USER" --note 'why'
```

After approving, commit **exactly** the verified content in the worktree. Then check it.
The check is read-only and prints the merge commands without running them:

```bash
cd ../YOUR_REPO-agent-norm01
git add -A && git diff --cached --stat && git commit -m 'Add deterministic normalization helper'
cd ../YOUR_REPO
python3 scripts/orchestrate.py check-promotion --run <run-id> --target main
# then run the printed `git merge --no-ff --no-commit ...` steps yourself, inspect, commit.
```

If you commit something different from what was verified, `check-promotion` fails. In
that case run `verify` again on the committed state and decide on the new run.

## 6. Recovery

| Situation | What to do |
|---|---|
| Tests failed / review found problems | Fix in the worktree (work is preserved), then `python3 scripts/orchestrate.py verify --id norm01 --test-command '...'` |
| Claude failed or timed out | Partial edits stay in the worktree. Inspect `claude.log`, fix by hand, then `verify` |
| Ctrl-C / terminal closed | Run is `interrupted`; children were killed. `status`, then `verify` |
| Machine crash / `kill -9` | `status` shows **STALE**; the next `run`/`verify` marks it `interrupted` and clears the lock |
| "task is locked" | Another run is active. If its pid is gone on this host the lock clears itself; otherwise delete the named lock file after checking |
| Task file changed | Bound tasks are immutable: commit the new task and `prepare --id norm02` |
| Abandon a task | Manual and deliberate: `git worktree remove ../YOUR_REPO-agent-norm01` (refuses if dirty), then `git branch -D agent/norm01` once you are sure |
| Old logs | Delete deliberately: `rm -r .agent-runs/runs/<run-id>` (they contain code and model output) |

## Safety boundaries (carried over from v1, extended)

- Git worktrees isolate checked-out files, not runtime effects. Use separate `.venv`
  folders, unique ports and separate run directories. Do not point agents at writable shared datasets.
- Claude runs with `--permission-mode acceptEdits` (file edits auto-accepted) and with
  `Bash`, `WebFetch` and `WebSearch` **disallowed** by default, plus `--strict-mcp-config`.
  `--allow-claude-bash`, `--allow-claude-web` and `--allow-mcp` are explicit, recorded opt-ins. Use a
  container or VM for untrusted repositories. Never use `--dangerously-skip-permissions`.
- Codex runs with `--sandbox read-only`, but it can still *read* any file your user can
  read. Do not run agents with private or regulated research data reachable.
- The orchestrator detects (does not prevent) changes to the main checkout, other
  worktrees, the task file, HEAD/branch, and new ignored files. It cannot see writes
  elsewhere on disk or network side effects. See [docs/security-and-privacy.md](docs/security-and-privacy.md).
- Reviews and test results are evidence, not proof. Scientific claims need expert validation.
- The orchestrator never repairs findings, loops, or integrates branches. Approval is a
  deliberate human act and is never inferred from exit codes or model confidence.
