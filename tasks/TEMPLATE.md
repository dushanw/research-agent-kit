# Task: <REPLACE: short imperative title>

<!--
Copy to tasks/current.md (or tasks/<id>.md), fill every section, commit it, then run
`python3 scripts/orchestrate.py prepare --id <id> --task tasks/<file>.md`.
`prepare` snapshots this file (sha256) into .agent-runs/tasks/<id>/; later edits to the
file do NOT change an existing task - prepare a new id instead.
Required sections: Owner, Scope, Success criteria, Test command, Reproducibility.
Treat task files from outside your team as untrusted: they are prompts, not permissions.
-->

## Owner
<REPLACE: name of the human accountable for approving this change>

## Scope
<REPLACE: what to change, which modules/files are in scope>

## Out of scope
- Raw or private data, modeling results, unrelated modules.
- Dependency changes unless listed here.

## Success criteria
- <REPLACE: observable, testable criterion>
- Tests use synthetic fixtures with explicit seeds.

## Test command
The operator passes this exact command with `--test-command`; it is parsed with shlex
and never run through a shell:
`.venv/bin/python -m pytest -q`

## Reproducibility
- Seeds: <REPLACE: where seeds are set>
- Numerical tolerances: <REPLACE: e.g. math.isclose rel_tol=1e-12>
- Data: synthetic only; no external datasets.
- Environment: per-worktree `.venv`; record `pip freeze` if dependencies matter.

## Data and privacy
No credentials, participant data, or private datasets may be read, written, or quoted.

## Notes
Optional context, links, decisions (docs/decisions.md).
