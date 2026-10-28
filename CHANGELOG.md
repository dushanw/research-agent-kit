# Changes

## 3.0.0 — simpler operator experience and Cursor workers

- One `start` command opens Claude with the coordinator instructions and project status; no manual cross-tool message copying.
- Explicit roster of Cursor models; default independent method check and optional alternative-model consultation.
- Codex review through a structured-output adapter, separate from the implementation folder.
- Inherited-project inventory, scoped recovery including unfinished source and index evidence, one worktree and zero-diff baseline checks.
- Structured unittest/pytest counts, artifact checks, bounded attempts and current/stale status.
- Plain-language task contracts and a six-statement handoff.
- Side-by-side tested installs, persistent settings/feedback, development copies and rollback.
- Removed the old terminal-based “human approval” and stale approval/promotion mechanism. No automatic integration replaces them.
- No automatic v2 state import or in-place overwrite. Original v1/v2 code and existing research projects remain untouched by installation.

This release narrows the earlier prototype rather than retaining every old command. Tests and scope limits are documented; live macOS/account behavior must be checked locally. Future changes should start from demonstrated user feedback, not a new agent platform.
