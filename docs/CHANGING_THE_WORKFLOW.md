# Change it without breaking your working projects

Your feedback should be understandable without implementation jargon. Examples: “The status is too long,” “Use a different model for method checks,” or “Save a visual preview with each segmentation result.”

## Change which Cursor models may be used

```bash
researchflow setup
```

Select the permitted roster; the first is the default. Claude can choose another approved model for a bounded question with `consult --model EXACT_ID "question"`. Calls are recorded by requested model, returned model when available, CLI version, task and output. There is no silent fallback or majority vote.

Ordinary settings live in `~/ResearchFlow/settings.json`, not in installed source code. They include model choices, timeouts, six worker calls per task and three check attempts by default. Time/call limits are not exact monetary caps. Increase budgets deliberately, not as an automatic response to failure. Changes make affected previous verification stale.

## Request a code/workflow change

You can tell Claude the request directly. It can save it with:

```bash
researchflow feedback "Make the status report show the result file first."
researchflow develop ~/Desktop/researchflow-next
```

`develop` requires a **new** destination. It copies the code and your recorded feedback there. Nothing in the running release, original research project, working branch or old run history is overwritten.

Give Claude this instruction in the development copy:

> Read START_HERE.md and REQUESTED_CHANGES.md if present. Make the smallest change that satisfies my feedback. Keep existing behavior and regression tests. Add a test for the change. Do not edit the installed release or my research project. Explain the difference in plain language. Do not install the update from an active research session.

No new platform, daemon, framework or dashboard is needed to change a prompt, add an adapter, adjust a report or support another test runner.

## Test and install the revised copy

In the editable copy:

```bash
python3 researchflow.py selftest
python3 tools/build_release.py
```

The release builder updates checksums; it does not prove safety. Review the change and test results. For a meaningful release, change `VERSION` in `rf/__init__.py` and add a short entry to CHANGELOG.md. Avoid editing installed directories directly.

Close active ResearchFlow/Claude sessions before installation, then:

```bash
researchflow update ~/Desktop/researchflow-next
```

The installer checks the inventory, copies the complete new release, runs its offline tests in that copied layout, and switches the launcher only after success. Your settings, feedback, project paths and evidence remain in `~/ResearchFlow`. Prior versions remain installed. Unknown future configuration formats are refused, not silently rewritten.

Repeat `researchflow doctor` and `researchflow demo --live` when an adapter or vendor CLI changes. A source upgrade invalidates old code-bound checks; recheck the current research task before relying on its status.

## Undo a troublesome update

After closing active sessions:

```bash
researchflow rollback
```

This changes which framework version launches. It does not undo research code changes, merge branches, delete outputs or restore a project snapshot. It checks the prior release inventory first. A future incompatible project-record format may not be readable by an older version; never assume code rollback migrates data backward.

## For the person editing the code

There are six small responsibilities, not a general multi-agent platform:

| File | Responsibility |
|---|---|
| `rf/cli.py` | Simple commands, Claude launch and demo |
| `rf/project.py` | Static takeover, scoped recovery and worktree ownership |
| `rf/workflow.py` | Task/baseline, checks, current status and evidence |
| `rf/providers.py` | Cursor and Codex call formats and validation |
| `rf/test_runner.py` | Actual unittest/pytest counts and example execution |
| `rf/support.py` | Bounded subprocesses, atomic records and local locks |

`prompts/lead.md` defines the plain-language operator behavior. `tests/` provides offline regression fixtures. `install.py` performs versioned installation. Add code only where a demonstrated requirement needs it.

The original v2 tests target a different private API and approval workflow; they are not represented as passing v3 tests. The new suite preserves their relevant safety intent and adds takeover/multiple-model coverage. Do not reintroduce TTY-based “proof of human approval,” stale-file lock deletion, exit-zero-only test gates, or silent overlays of old/new executables.
