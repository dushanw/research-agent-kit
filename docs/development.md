# Development and verification
Prerequisites: macOS, Git, Python 3.10+, Claude Code CLI, Codex CLI, Cursor IDE.
Optional: Cursor Agent CLI for later CLI automation.

Set up per-worktree Python environment:
`python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'`

If project does not support editable installs, adapt setup and `--test-command`.
Example test command: `.venv/bin/python -m pytest -q`.
No real experimental data should be used for the smoke test.
