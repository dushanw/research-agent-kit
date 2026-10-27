# Trust boundaries, privacy and retention

## What the orchestrator guarantees

- It never runs `git commit`, `merge`, `push`, `reset`, `clean`, `rebase`, `worktree remove`
  or `branch -d`. The only state-changing Git calls are `git worktree add -b` in `prepare`, and
  object writes through a temporary index (see orchestrator.md).
- No `shell=True`. The test command is `shlex.split` and run directly. A leading `sh`, `bash`,
  `zsh`, `env`, `xargs`, `sudo`, ... is refused unless `--allow-shell-test-command` is given
  (recorded as a warning).
- No environment dump. Only the `PYTHONHASHSEED` value and the *names* of removed variables
  are recorded. Prompts longer than 300 characters appear in `run.json` only as length + hash
  (full text in `prompts/`).
- Every child process has a timeout and is killed with its whole process group on timeout,
  Ctrl-C, SIGTERM or SIGHUP.

## What it only detects (not prevents)

A Git status snapshot is **not an OS sandbox**. After the implementation stage the orchestrator
compares the main checkout's content and HEAD/branch, other worktrees' HEAD/branch, the
agent worktree's HEAD/branch, the task file, and newly created *ignored* paths. Not detected:

- writes anywhere else on disk (home directory, `/tmp`, other repositories, shared datasets);
- modifications *inside* ignored directories that already existed (e.g. `data/raw/` if ignored);
- network access and other external side effects (uploads, API calls, package installs);
- anything done by background processes that detached into their own session.

Use a container or VM for untrusted code. Mount datasets read-only.

## Model / CLI trust

- **Claude** (`acceptEdits`): file edits inside the working directory are auto-accepted.
  `Bash`, `WebFetch` and `WebSearch` are disallowed by default and MCP servers are disabled via
  `--strict-mcp-config`. Your own Claude settings (allow/deny rules, hooks) still apply and may
  differ by version; `doctor` reports the version actually used.
- **Codex** (`--sandbox read-only`): cannot write, but can **read** any file your user can
  read, including files the review material withheld. The policy keeps secrets and data out of
  the prompt; it cannot stop the model from opening a file itself.
- Both send the content they read to the vendor. **Never run these agents on repositories or
  machines where private participant data, credentials or regulated datasets are readable.**

## Untrusted task files and instructions

Task files, `AGENTS.md`, `CLAUDE.md` and code comments are prompts, not permissions. Nothing
in them can enable Bash, web or MCP access, change the sandbox, or skip a gate. Those are
command-line flags typed by the operator and recorded in `run.json`. Task text is bound by
sha256 at `prepare`, and a changed task file stops `run`/`verify`. Review a task from outside
your team before committing it.

## Logs and retention

`.agent-runs/` must be git-ignored (checked) and is created with 0700/0600 permissions. It
contains source code, diffs, model output and absolute paths. There is no automatic deletion:

```bash
ls -lt .agent-runs/runs/
rm -r .agent-runs/runs/<run-id>        # after the decision is merged or abandoned
```

Do not sync `.agent-runs/` to shared drives or attach it to tickets without redaction.
Secret patterns are a best-effort screen with false positives and false negatives. They are
not a substitute for keeping credentials out of the repository.
