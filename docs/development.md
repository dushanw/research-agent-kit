# Development and verification
Prerequisites: macOS, Git 2.36+, Python 3.9+, Claude Code CLI, Codex CLI, Cursor IDE.
Optional: Cursor Agent CLI for later CLI automation (not used by the orchestrator).

Set up per-worktree Python environment:
`python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'`

If project does not support editable installs, adapt setup and `--test-command`.
Example test command: `.venv/bin/python -m pytest -q`.
No real experimental data should be used for the smoke test.

## Verifying the kit itself (offline)

Exact commands, run from the kit root (or from a repository the kit is installed in):

```bash
python3 -m compileall -q scripts examples
python3 -m unittest discover -s scripts/tests -v
(cd examples/research_demo && python3 -m unittest discover -s tests -t . -v)
```

`scripts/tests/test_orchestrate.py` uses **fake** `claude`/`codex` executables
(`scripts/tests/fake_cli.py`) put on `PATH`, and builds throwaway Git repositories under a
temporary directory whose path contains spaces. pytest is not required. If installed,
`python3 -m pytest scripts/tests -q` collects the same tests.

### What the offline suite covers

- `doctor` outside a Git repo with no agent CLIs installed; `doctor` with an incompatible Codex.
- `prepare`: bound task snapshot, collisions (path/branch/registration), dirty repo,
  invalid id, `.agent-runs/` not ignored, refusing a cwd in an unrelated repository.
- `run`: success; untracked file *content* reaching the reviewer prompt; staged/unstaged/
  untracked origins; Claude argv (read-only review flags, disallowed tools, strict MCP, no
  bypass); failing tests (review not run); skipped tests (never approvable); Claude
  failure and timeout (child killed); incompatible CLI detected before any change; Codex
  non-zero exit, missing verdict, wrong-nonce verdict, contradictory verdict; reviewer
  modifying the worktree; agent editing its task, the main checkout, or committing;
  secrets/binaries/data files/symlinks withheld; new ignored `.env` flagged; 3 MiB output
  capped; dirty worktree refused and preserved.
- Interrupts: SIGINT and SIGTERM give `interrupted` with children killed and the lock released;
  SIGKILL shows STALE and is later marked `interrupted`.
- Recovery: fix in the same worktree → `verify` (parent link) → `decide` rejections
  (non-TTY, wrong confirmation, changed tree, run not awaiting, unresolved CRITICAL finding)
  → approval → `check-promotion` fails before commit and passes after. The main branch is
  never modified.
- Unit tests: task schema, verdict parsing, gate assessment, secret/binary detection, test
  command parsing and environment scrubbing, process timeout/output cap/missing binary.

### Not covered (requires your signed-in tools)

- Real `claude` and `codex` behaviour, including whether the installed versions honour
  `--disallowedTools`, `--strict-mcp-config` and `--sandbox read-only` as documented, and their
  real output format. Run section 2 of README.md in a sandbox before using real projects.
- Authentication state of either CLI (doctor deliberately doesn't check it).
- Cursor IDE (used interactively, no automation).
- pip installs into a worktree venv (the tests use `python3 -m venv --without-pip`).
- Other macOS versions, Intel Macs, Homebrew/pyenv Pythons (tested: macOS 26 arm64, Python 3.9.6, Git 2.50.1).
