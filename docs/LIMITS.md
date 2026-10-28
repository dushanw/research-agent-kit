# Boundaries and honest limitations

ResearchFlow is a **supervised coordinator for trusted, non-sensitive local research source**. It is not a security sandbox and is not ready to execute an arbitrary hostile repository unattended. This page separates implemented behavior from broader guarantees.

## What it does protect against in its supported workflow

The controller never merges, pushes, stashes, resets, cleans or deletes your original work. Its only normal Git mutation is creating a dedicated branch/worktree. The demo initializes and commits only a new synthetic fixture. Original staged/unstaged/untracked source is preserved, and the original Git index is copied as recovery evidence. A new worktree alone does not include dirty work: ResearchFlow explicitly transfers the included working bytes, including deletions. Staged-vs-unstaged distinctions remain in the original index; the new workspace is not a byte-for-byte restoration of the original Git index.

Git hooks are disabled for controller Git calls. Git environment redirects are cleared. Inherited filters, submodules, local includes and source symlinks are conservatively refused. Identity is computed from actual included file bytes rather than a Git clean-filter result.

One cooperating Claude session owns a project. OS file locks on a local filesystem serialize operations without deleting stale lock files. There is no parallel implementation, automatic queue or background service. An unrelated editor or same-user process can still change files; the owner must pause other writers. Before/after fingerprints do not prove that no transient change occurred between observations.

Checks run in disposable source copies, not the original repository. Tests produce structured counts; zero tests, missing tooling/evidence, skipped tests, expected failures, missing artifacts, failed commands and malformed reviews cannot become CHECKED. Original test identities must remain. Candidate tests can still be incorrect or malicious: a runner does not prove scientific validity or isolate arbitrary Python.

The process runner bounds runtime, captured output and pipe cleanup. A process deliberately detaching from its group may escape termination; use OS-level isolation for hostile code. There is no promise to kill every possible descendant or prevent a test from accessing your home directory or network. No API-key environment variables are forwarded by the worker/test helpers, but default account files on the same machine are not protected from an unrestricted same-user process.

## Takeover scope

Start with a source-code repository with at least one commit. Git-ignored files are not copied during initial takeover. Environment/cache directories, datasets, model weights, credential-like filenames and common data formats are excluded. Tracked excluded files cause a visible stop rather than an incomplete checkout presented as complete. Source limits are 2 MB per file, 30 MB total and 3,000 files. For a larger or data-heavy repository, prepare an explicitly approved code-only working project; do not put private data into Git just to bypass a stop. Ignored source needed at runtime must be identified and deliberately brought into the approved scope.

`recovery/source` covers only files listed in its inventory. It is not a full-machine backup. Original history, ignored work, original datasets, external services and installed environments remain outside that recovery capture. If an inherited writer changes the original after takeover, it is not silently synchronized into the active workspace.

Each task freezes a new baseline from its then-current workspace. That baseline can be tested without any proposed code diff. Its recorded environment may differ from the previous agent's original environment; do not silently call those equivalent.

## Model diversity and privacy

Only approved task/context text, raw source diffs (including removed and new lines), and selected runner observations go into worker packets. Binary change review and packets over 230 KB are blocked. Complete outbound packets are checked for several common credential patterns. **This is a best-effort screen, not a secret-detection guarantee.** It cannot identify every confidential statement, token format, encoded secret or personal datum. Review the scope before authorizing external model calls.

Cursor runs in Ask mode with explicit model selection, enabled CLI sandbox, a dedicated profile, and deny rules for shell, writes, web fetch and MCP. The profile is not a second account or proof of authentication isolation. Codex uses read-only execution and ignores custom user configuration/rules. Neither worker is launched in the implementation checkout: each gets a small separate packet folder. These are configured restrictions; actual vendor enforcement and enterprise managed settings require testing on your Mac. Existing vendor policy/configuration outside the supported defaults may prevent a call.

Model identity is recorded as requested and, when the CLI supplies it, reported. Some Cursor output does not report the actual model; the kit says so rather than inventing proof. An explicitly different reported model blocks the call. Model aliases and vendor routing still depend on the provider. Six calls and per-call timeouts are practical limits, not precise token or dollar budgets. No silent fallback is performed when login, quota, permissions or a model is unavailable.

An opinion from Cursor does not establish methodological correctness. Codex receives evidence rather than only the implementer's story, but it can still miss defects. Medium-or-higher code-review findings or insufficient evidence block CHECKED. There is no vote and no general proof from two agreeing models.

## Current status versus approval

The generated status rechecks raw source, task, selected settings/instructions, recorded Python/package metadata, evidence files and verified output hashes. It cannot automatically know changes in unrecorded external datasets, package source tampering, hidden services or scientific assumptions. Package metadata is not a complete environment capture. An editable package install can import source from outside the copied run; for each real project, include an import-origin check in its approved baseline and verify that application modules come from the intended source. Native libraries, external services and unrecorded data require their own checks. A plain Markdown file does not refresh in the background; run `status` at resumption and after outside edits.

Records live outside the source checkout, but they are still writable by your OS user. They are inspectable integrity evidence, not tamper-proof audit logs. A hostile implementation agent with unrestricted access to your user account could forge records or modify the controller. No special token or terminal prompt is claimed to solve that problem.

CHECKED is not APPROVED. The old pretend-human terminal approval and automatic promotion checker were removed. Actual human review/integration remain outside this controller. Review the resulting diff and output, including new files and changes to tests/tolerances, before accepting changes. Review low-severity findings too. The kit does not claim an enforceable human-authentication boundary.

## Vendor documentation used for the adapters

Checked October 17, 2026; use `doctor` and the live smoke against the versions installed on your Mac.

- Claude system-prompt/settings flags: https://code.claude.com/docs/en/cli-reference
- Claude hook configuration: https://code.claude.com/docs/en/hooks
- Cursor model/mode/CLI parameters: https://cursor.com/docs/cli/reference/parameters
- Cursor JSON envelope: https://cursor.com/docs/cli/reference/output-format
- Cursor profiles: https://cursor.com/docs/cli/reference/configuration
- Cursor permission rules: https://cursor.com/docs/cli/reference/permissions
- Codex scripted calls, structured outputs and authentication: https://developers.openai.com/codex/noninteractive/
- Codex CLI flags: https://developers.openai.com/codex/cli/reference/
- Git worktrees: https://git-scm.com/docs/git-worktree

These references support command choices, not claims that a live integration or operating-system isolation was tested here.
