# Audit of research-agent-kit v1 (baseline)

Audited 2026-10-17 on macOS 26 / arm64, Apple Git 2.50.1, system Python 3.9.6.
Line numbers refer to the baseline `scripts/orchestrate.py` (Git commit `3bd026c` on
`main` of the kit repository; an untouched copy is kept in `research-agent-kit.orig-2026-10-17/`).
Status column: **fixed** = addressed in v2.0.0 and covered by a test (test name given);
**mitigated** = reduced and documented, not eliminated.

## P0: safety and correctness

| # | Location | Problem | Impact | Status |
|---|---|---|---|---|
| 1 | L45-48 | `git rev-parse` runs before any command, including `doctor`, with `check=True`. | `doctor` crashes with a traceback outside a Git repo, so it can't diagnose a fresh machine. | fixed (`test_doctor_outside_git_with_tools_missing`) |
| 2 | L49-53 | Prerequisites are only `shutil.which()`, printed for every command; no versions, no flag checks, no distinction from authentication. | "Found on PATH" reads as "ready"; incompatible CLIs fail mid-run. | fixed: version + `--help` capability probe; auth explicitly reported as NOT CHECKED |
| 3 | L45, L67, L77 | Repo root is derived from the script location only; the worktree is accepted if its *branch name* matches. | An unrelated clone at the sibling path with branch `agent/<id>` would be driven by Claude. Inherited `GIT_DIR`/`GIT_WORK_TREE` would redirect every Git call. | fixed: common-dir + registered-worktree check, cwd/other-repo refusal, Git env scrubbed (`test_refuses_when_cwd_is_another_repository`) |
| 4 | L17-24 | `subprocess.run` with no timeout; all output buffered in memory; log written only after exit. | Hung CLI blocks forever; huge output exhausts memory; Ctrl-C leaves no log at all. | fixed: process group, timeouts, streamed capped logs (`test_timeout_kills_process_group`, `test_large_output_is_capped`) |
| 5 | L119-123 | Only `Exception` is caught. `KeyboardInterrupt`/SIGTERM skip the handler. | Interrupted runs leave no `STATUS.txt`, so you can't tell them from in-progress runs. | fixed: explicit `interrupted` state, stale detection (`test_ctrl_c_and_sigterm_...`, `test_sigkill_shows_stale_...`) |
| 6 | L97-98, L114 | `--skip-tests` ends with the same `COMPLETED: HUMAN REVIEW REQUIRED` status as a tested run. | A skipped test gate looks like a passed one. | fixed: `skipped` is a hard blocker (`test_skip_tests_is_never_approvable`) |
| 7 | L110-114 | Codex exit status 0 means "completed"; the findings are never parsed. | A review with critical findings ends in the same state as a clean one. | fixed: nonce-tagged verdict line, blocking severities, written override required (`test_severe_review_exit_zero_blocks_approval`) |
| 8 | L92-96 | `git diff HEAD` plus untracked file *names* only. | New files (usually most of the change) never reach the review artefact; secrets in new files are never screened. | fixed: temp-index fingerprint + per-file review material with secret/binary/data/size policy (`test_success_includes_untracked_content...`, `test_secrets_binaries_...`) |
| 9 | L102, L111-113 | The before/after comparison uses `status --porcelain` + tracked diff. | Edits to *untracked* files during review (`??` stays `??`) and writes to ignored paths are invisible. | fixed: content fingerprint + `--ignored` status (`test_review_that_modifies_worktree_is_caught`) |
| 10 | L86-90 | The agent is told to read `tasks/current.md` from its own worktree and may edit it. Nothing binds a run to a task version. | The agent can rewrite its own acceptance criteria; the reviewer then judges against the rewritten task. | fixed: sha256 snapshot at `prepare`, checked before/after (`test_agent_editing_its_task_or_main_repo_is_caught`) |
| 11 | L90 | `claude -p --permission-mode acceptEdits` with no tool restrictions. Bash/web/MCP availability depends on the user's global settings. | Commands with side effects can run outside Git's view. | mitigated: Bash/WebFetch/WebSearch disallowed by default, `--strict-mcp-config` required, opt-in flags recorded. Not an OS sandbox. |
| 12 | L101 | Tests inherit `PYTHONPATH`/`VIRTUAL_ENV`; the default command is `python3 -m pytest`. | With an activated venv where the main checkout is installed editable, the tests import the *main* checkout, so the worktree's code goes untested. | fixed: environment scrubbed, interpreter resolution recorded, `bash -c` refused without opt-in |
| 13 | L101 | A failing test raises and stops; the tree isn't re-checked after tests. | Tests that rewrite source files change what is reviewed. | fixed: fingerprint before/after tests |
| 14 | L79-80, README §5 | `run` refuses a dirty worktree, and there is no re-verification command. | After fixing findings, the only option is a manual re-run; the docs admit the script "will not rerun". | fixed: `verify` command (`test_fix_reverify_decide_and_check_promotion`) |
| 15 | README §5 | After the human commits in the worktree, `git diff HEAD` is empty. | Re-review after committing reviews nothing. | fixed: everything is diffed against the recorded **base commit** |
| 16 | README L70 | The merge instructions don't tie the merged commit to what was tested and reviewed. | Someone can commit a different subset than was verified and merge it. | fixed: `check-promotion` compares the branch tip tree to the verified tree; read-only |

## P1: workflow, reproducibility, privacy

| # | Location | Problem | Status |
|---|---|---|---|
| 17 | L81-83 | Run ids have second resolution; `mkdir(exist_ok=False)` sits outside `try`. Two runs in the same second crash. | fixed: timestamp + random suffix, microsecond ordering |
| 18 | L114, L120 | Status is free text; no machine-readable record (base commit, versions, exit codes, durations). | fixed: `run.json` (state machine), `events.jsonl`, `summary.md` |
| 19 | L83, L21 | Logs are created with default permissions; nothing checks that `.agent-runs/` is git-ignored. | fixed: 0700/0600, ignore check refuses otherwise |
| 20 | L32 | Task ids allow upper case. On case-insensitive APFS, `Foo`/`foo` collide as worktree directories. | fixed: lowercase only (breaking; documented) |
| 21 | L69-71 | Collision checks cover only path existence and branch. Prunable worktree registrations, worktrees inside the repo and an unwritable parent aren't checked. | fixed |
| 22 | L40 | Default `--id normalization`: a bare `run` silently targets a default task. | fixed: `--id` required |
| 23 | tasks/current.md | No schema: owner, test command and reproducibility expectations aren't captured. | fixed: `tasks/TEMPLATE.md` + validator |
| 24 | README §1, docs/development.md | Docs require Python 3.10+, but macOS ships 3.9.6 as `/usr/bin/python3`. | fixed: code supports 3.9+, tested on 3.9.6 |
| 25 | (none) | No tests or example project existed (`tests/` was empty). | fixed: 46 offline tests + `examples/research_demo` |

## P2: noted, not implemented

- Running several tasks concurrently: per-task locks exist, but CPU/GPU/port isolation does not.
- Cost/token budgets: Claude `--max-turns` is passed only when the installed CLI advertises it.
  Neither CLI exposes a reliable spend cap through flags we could verify locally.
- Containerised execution (the only real way to prevent writes outside the worktree).
