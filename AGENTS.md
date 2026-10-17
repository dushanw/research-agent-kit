# Shared research engineering policy
Read tasks/current.md, docs/architecture.md, docs/decisions.md before significant edits.

## Research integrity
- Never fabricate measurements, benchmark outcomes, plots, citations, or test results.
- Set and record random seeds; record datasets, data versions, environment, and metrics.
- Preserve raw datasets; never modify source data or commit private participant records.
- Prefer tests with synthetic fixtures. Flag any inference or statistic not independently validated.

## Change management
- Follow the assigned task scope and acceptance criteria.
- Do not push, merge, delete data, install unreviewed dependencies, or change access controls.
- Keep changes on the assigned Git worktree; do not modify other worktrees.
- Never put credentials or private research data in prompts, logs, or Git.
- Use docs/decisions.md for approved significant architectural decisions.
- Report modified files, executed checks and their actual outcomes, remaining risks.
