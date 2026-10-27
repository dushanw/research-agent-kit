# Changelog

## 2.0.0 (2026-10-17)

Rewrite of `scripts/orchestrate.py` after an audit (docs/AUDIT.md). Standard library only, Python 3.9+.

### Added
- Commands `verify`, `status`, `report`, `decide`, `check-promotion` (in addition to `doctor`, `prepare`, `run`).
- Run state machine with `run.json`, `events.jsonl` audit log, `summary.md`, unique run ids.
- Timeouts, process-group kill on timeout/Ctrl-C/SIGTERM/SIGHUP, capped streamed logs, stale-run detection, per-task lock.
- Working-tree fingerprint (temporary index) used for integrity checks, approval binding and promotion checks.
- Review material covering committed/staged/unstaged/untracked changes vs. the base commit, with secret/data/binary/size policy.
- Nonce-tagged review verdict; review decision gate; written override for high/critical findings.
- CLI capability probing (`--help`, `--version`); no unsafe fallbacks.
- Task schema (`tasks/TEMPLATE.md`), task snapshot binding (sha256).
- `examples/research_demo` synthetic-data package; `scripts/make_sandbox.py`; 46 offline tests with fake CLIs.
- Docs: `docs/orchestrator.md`, `docs/security-and-privacy.md`, `docs/AUDIT.md`.

### Changed (breaking)
- `--id` is required (previously defaulted to `normalization`) and must be lowercase.
- `run` requires `--test-command` or `--skip-tests`; skipped tests are never approvable.
- Claude runs with `Bash`, `WebFetch`, `WebSearch` disallowed and `--strict-mcp-config` by default
  (opt in with `--allow-claude-bash`, `--allow-claude-web`, `--allow-mcp`).
- Run logs moved from `.agent-runs/<id>-<stamp>/` to `.agent-runs/runs/<run-id>/`; task records in
  `.agent-runs/tasks/<id>/`. v1 worktrees have no task record; prepare a new id.
- Python 3.9 is supported (docs previously said 3.10+); Git 2.36+ required.

### Migrated (content preserved)
- `tasks/current.md`: same goal and acceptance criteria, in the new section schema.
- `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/workflow.mdc`, `docs/development.md`, `docs/decisions.md`:
  original text kept verbatim; orchestrator-specific rules appended.
- README: install/usage rewritten; the v1 "Safety boundaries" points kept and extended.
