# Approved decisions
- Automation runs locally in isolated Git worktrees.
- Only the operator approves commits and merges.
- Review is non-modifying and tests must pass before integration.

## 2026-10-17: orchestrator v2 (kit 2.0.0)
- Human approval is a recorded, interactive act (`decide --approve` needs a TTY and a typed
  confirmation code). Exit codes, passing tests and model verdicts are evidence, not approval.
- Tests and independent review are separate gates; skipped tests or a failed review make a run
  not approvable. High/critical findings need a written override from the human.
- A run is bound to a task snapshot (sha256), a base commit, and a verified tree id; merging
  is manual and checked with `check-promotion`.
- Claude runs with Bash/web tools disallowed and MCP disabled by default; enabling them is an
  explicit, recorded operator flag. Incompatible CLI versions stop the run (no fallback).
- Standard library only; Python 3.9+ (macOS system Python) is supported.
