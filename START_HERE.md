# ResearchFlow — start here

**You talk to Claude. It consults your chosen Cursor models, runs checks, and gets a Codex review. You receive one short status page and the actual results.**

This is a complete local code package, not another instruction-only improvement assignment. Start on the included synthetic example before using a real project. Nothing needs to be installed into your research repository.

## 1. Install once on your Mac

Unzip the download. In Terminal, open the extracted folder:

```bash
cd ~/Downloads/ResearchFlow
python3 install.py
export PATH="$HOME/.local/bin:$PATH"
```

Adjust only the first path if you extracted elsewhere. The installer requires **Python 3.10 or newer** and runs the included offline tests before activation. It does not download packages or change Apple's Python. If `python3` is older, use your installed newer interpreter, for example `python3.12 install.py`. Your research project may use its own separate Python environment.

The command remains available by its full path, `~/.local/bin/researchflow`, even without changing PATH. To make it available in future Terminal windows, add `export PATH="$HOME/.local/bin:$PATH"` once to your `~/.zshrc`.

Keep your existing Claude Code and Codex installations and sign-ins. Cursor's desktop editor and its **command-line agent** are different components. Check:

```bash
claude --version
codex --version
agent --version
```

Missing tools or an older Python? See [Mac prerequisites](docs/MAC_PREREQUISITES.md). Do not install anything into an inherited research project merely to satisfy this checklist.

## 2. Choose your Cursor models and check the connections

```bash
researchflow setup
researchflow doctor
researchflow demo --live
```

`setup` lists the models available to your Cursor account. Select one or more exact IDs, separated by commas. The first is the usual worker; choose a different family from Claude for that role. Other approved models can provide a fresh opinion when needed. There is no silent “Auto” substitution.

ResearchFlow uses a separate Cursor CLI configuration and may ask you to sign in to that profile. It does not overwrite your normal Cursor settings. Codex uses its normal saved authentication without loading its custom configuration.

`doctor` checks installed command interfaces. It does **not** establish that your accounts work. `demo --live` explicitly asks permission before making small calls using your accounts; account usage/charges may apply. It runs a tiny, deliberately broken normalization example, records the failure, applies a known demo repair, and verifies it. The repair in this smoke test is applied by the demo script, not written by a live model.

A successful smoke prints `baseline: FAIL` and `candidate: CHECKED`, then the exact status-page location. A failed live call is a blocker to inspect, not an instruction to disable permissions. A model may also identify a legitimate concern; read its saved review.

For a free, offline demonstration instead:

```bash
researchflow demo
```

That uses clearly labelled fake workers. It cannot verify subscriptions, authentication or real model behavior.

## 3. Start a real project

Use a local, non-sensitive Git repository that already has a commit. Pause other agents editing it first.

```bash
researchflow start "/absolute/path/to/your/project"
```

ResearchFlow inventories the source and unfinished work, asks permission to preserve it, creates one separate Git worktree, and opens **Claude Code**. Your original working files and index are not changed; Git's worktree registry and a new branch are created. A scoped source recovery copy is saved. Ignored data, model weights, secrets and environments are not backed up or copied.

Then just give Claude your task. For example:

> Study this paper and replicate the segmentation approach. Start with the authors' smallest runnable example. Explain what that milestone will and will not reproduce before changing code.

Stay in that conversation. Claude has the workflow commands and instructions. It will propose a small milestone, inspect the code/environment, record a baseline, consult a selected Cursor model, implement, run tests and the example, and request Codex review. Normal permission prompts and meaningful research decisions still come to you.

**You do not pass messages between tools. Cursor's editor is optional for inspecting code/results.**

## 4. Find your work and resume

Claude and the launcher display the exact path to one `PROJECT_STATUS.md`. It tells you the working folder, task, baseline failures, current checks, changed files, result files and next action. Detailed evidence is linked underneath it.

From the original project or its working folder:

```bash
researchflow status
researchflow start
```

`start` opens a fresh Claude session with the same workspace, task and status. It does not require the previous chat. `status` refreshes validity; a Markdown file sitting unopened cannot update itself after external edits.

`CHECKED` means the required tests and review completed for a specific source snapshot. It does **not** mean approved, merged, scientifically correct, or a complete paper replication. Inspect the actual output and decide whether to keep the change. There is no automatic commit/merge/push or fake “human approval” command.

## 5. Improve the workflow after testing it

Tell Claude what is awkward in plain language. There are built-in commands to save that feedback, make a separate editable copy, install a tested update and roll back. Your settings and research work stay separate from the software versions.

See [Changing the workflow](docs/CHANGING_THE_WORKFLOW.md). You do not need to learn the internal modules to request a change.

## What was checked before delivery

See [Verification results](evidence/VERIFICATION.md) for actual test counts and commands. Local tests exercise Git preservation, failure gates, selected-model handoffs, stale evidence and the installed layout. They use Linux and fake workers. **This package has not been run on your Mac or with your authenticated accounts here.** The included Mac self-test and live smoke are the remaining local checks.

For security boundaries and supported project scope, see [Limits](docs/LIMITS.md). The main design is intentionally small: one writer, two worker adapters, one status page, no server, no dashboard, no queue.
