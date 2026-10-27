# Orchestrator design (scripts/orchestrate.py, v2)

One standard-library Python file (3.9+). All external programs are started with argument
arrays (never `shell=True`) in their own process group, with a timeout.

## Commands

| command | changes anything? | purpose |
|---|---|---|
| `doctor` | no | Tool versions, CLI capability probe (`--help`), repo checks. Works outside Git. Never calls a model; authentication is reported as **NOT CHECKED**. |
| `prepare --id ID [--task F] [--base REF] [--worktree-root DIR]` | creates branch `agent/ID`, a worktree `<repo>-agent-ID` and `.agent-runs/tasks/ID/` | Binds the task: the committed task text at the base commit is snapshotted with its sha256. Refuses on a dirty repo, an existing branch/path/registration, an invalid task, or `.agent-runs/` not ignored. |
| `run --id ID (--test-command CMD \| --skip-tests)` | Claude edits the worktree; writes a run directory | Implement → integrity checks → tests → review. Requires a clean worktree at the base commit. |
| `verify --id ID (...)` | writes a run directory | Tests + review of the worktree's **current** state (dirty or committed). Used after human fixes. |
| `status [--id ID] [--run R]` | no | Lists tasks/runs; for one run, also compares the live worktree and branch tip with the verified tree. |
| `report --run R [--format md\|json]` | rewrites `summary.md` | Human summary (for Cursor) or the JSON record. |
| `decide --run R (--approve\|--reject) --reviewer N --note T` | updates `run.json` | Human decision. Approval needs a TTY and a typed confirmation code, refuses hard blockers, and needs `--override-findings` / `--acknowledge-warnings` when applicable. |
| `check-promotion --run R [--target B]` | no | Verifies the approval, a clean worktree, branch tip tree == verified tree, ancestry and a clean target. **Prints** the merge commands; never runs them. |

`R` may be a full run id, a unique prefix, or `latest` together with `--id`.

## State machine (`run.json: state`)

```
created ─► implementing ─► testing ─► reviewing ─► awaiting_decision ─► decided
   │            │             │           │
   └────────────┴─────────────┴───────────┴──► failed | interrupted        (terminal)
verify starts at created ─► testing ...
```

Illegal transitions raise. `failed` and `interrupted` are terminal: a new attempt is a new
run (`verify`) with `parent_run` set. A run whose state is non-terminal and whose pid is
dead is shown as **STALE**; the next `run`/`verify` for that task marks it `interrupted`.

Gate assessment (`assessment` in run.json) is recomputed from the recorded facts:

- **Hard blockers** (cannot be approved): tests not `passed` (including `skipped`), review not
  `completed`, any failed integrity check, a recorded failure, an interrupted run.
- **Override required** (`--override-findings`, 20+ characters, recorded): verdict
  `high`/`critical`, verdict line missing or unparseable, review text mentioning high/critical
  issues while the verdict says otherwise, reviewer reporting insufficient evidence.
- **Warnings** (`--acknowledge-warnings`): content withheld from the reviewer, new ignored
  paths created by the agent, changed symlinks, test command resolved outside the worktree,
  explicit opt-ins (`--allow-claude-bash`, `--allow-mcp`, ...).

## Run directory `.agent-runs/runs/<task>-<UTC stamp>-<random>/` (0700, files 0600)

| file | content |
|---|---|
| `run.json` | Full record: base commit, HEAD, task sha256, tool paths/versions/capabilities, options, per-stage exit code/duration/bytes/timeout flags, integrity checks, warnings, verified tree, assessment, decision |
| `events.jsonl` | Append-only audit log (state transitions, warnings, integrity results) |
| `summary.md` | Human summary: verdict, gates, blockers, findings, changed files, next commands |
| `claude.log`, `tests.log`, `review.log` | Streamed output (stdout+stderr), capped at `--max-log-bytes` (20 MiB) |
| `review-last-message.txt` | Codex final message (when `--output-last-message` is supported) |
| `review-material.md` | Exactly the change material sent to the reviewer |
| `prompts/claude.txt`, `prompts/review.txt` | Exact prompts sent |

`.agent-runs/tasks/<id>/` holds `task.json` (binding), `task.md` (immutable snapshot) and the
`lock` file while a run is active.

## Fingerprint ("verified tree")

`GIT_INDEX_FILE=<tmp> git read-tree HEAD && git add -A && git write-tree` gives a tree id
for the working tree's full content (tracked + untracked, non-ignored), without touching the
real index, HEAD or files. It is used to:

- detect any content change by tests or by the reviewer (including edits to untracked files);
- produce review material against the **base commit** (covers committed, staged, unstaged
  and untracked changes in one diff);
- refuse `decide --approve` if the worktree changed after verification;
- prove in `check-promotion` that the committed branch tip equals what was verified.

Side effect: blob objects are written to `.git/objects` (unreferenced; `git gc` removes them).
Clean/smudge filters configured in *your* Git config run as part of `git add`.

## Review material policy

Per changed path, from Git objects (symlinks are never followed on disk):

- Text patch included if ≤ 64 KiB per file and ≤ 256 KiB in total (`--review-max-*-bytes`).
- Withheld, with the reason written into the material and a warning: secret-like paths
  (`.env*`, `*.pem`, `id_rsa*`, `*credential*`, `*secret*`, ...), secret-like content (private
  keys, AWS/GitHub/Slack/`sk-` keys, `password = "..."`), data files (`.csv`, `.parquet`, `.h5`,
  `.npy`, `.pkl`, checkpoints, ...), binaries, files > 2 MiB, nested repositories/submodules.
- Symlinks are shown as `link -> target`, flagged when the target leaves the repository.

The material goes into the Codex prompt as one argument (macOS ARG_MAX is 1 MiB; the prompt
is capped at ~700 KB). Codex may also read repository files itself; see the security doc.

## Verdict protocol

The review prompt asks for a final line `REVIEW_VERDICT_JSON[<nonce>]: {...}`. The nonce is
random per run and generated after the agent finished, so code or comments written by the
agent cannot contain a matching line. The last valid line wins. Severity is escalated to the
highest finding severity. Missing or invalid → `parsed: false` → override required.

## Claude / Codex invocation and capability checks

```
claude -p <prompt> --permission-mode acceptEdits --strict-mcp-config [--max-turns 50] \
       --disallowedTools Bash WebFetch WebSearch          # variadic flag last
codex exec --sandbox read-only [--output-last-message <run>/review-last-message.txt] <prompt>
```

Before anything runs, `claude --help` must list `-p/--print`, `--permission-mode`, the chosen
mode name, `--disallowedTools` and (unless `--allow-mcp`) `--strict-mcp-config`. `codex exec
--help` must list `--sandbox` and `read-only`. If any is missing, the run stops before
Claude is invoked and nothing is changed. There is no fallback to other modes.
`bypassPermissions` cannot be selected.

## Exit codes

`0` ready for human decision · `1` failed / refused · `3` finished but blocked (not approvable
or override required) · `130` interrupted · `2` command-line usage error.
