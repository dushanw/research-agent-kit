# Mac prerequisites — only install what is missing

ResearchFlow itself uses the Python standard library, Git, and the three vendors' CLIs. It does not require a Python package manager, Node, a database, Docker, a server or API keys. A project's own dependencies are a separate, approved setup step.

## Python and Git

```bash
python3 --version
git --version
```

The ResearchFlow controller needs Python 3.10+. Apple's preinstalled Python may be older. Install a current Python through your usual trusted method; do not replace system files. The Python.org macOS installer is an option. With an existing Homebrew installation, `brew install python` is another option; invoke the resulting new interpreter for `install.py`.

If Git is absent, macOS normally offers the Command Line Tools installation. You can request it with:

```bash
xcode-select --install
```

## Claude Code

Use your current installation and login. Run `claude --version`. Missing or out-of-date flags are reported by `researchflow doctor`; update using the official Claude Code installation instructions. Do not use permission-bypass options.

## Cursor command-line agent

A Cursor desktop installation alone does not establish that `agent` is on PATH. The documented macOS installer is:

```bash
curl -fsS https://cursor.com/install -o /tmp/cursor-install.sh
less /tmp/cursor-install.sh
bash /tmp/cursor-install.sh
export PATH="$HOME/.local/bin:$PATH"
agent --version
```

Review the downloaded installer before executing it. `researchflow setup` uses the CLI's own `models` command and, when needed, its browser login under a separate Cursor configuration directory.

## Codex

Keep your existing login. For an existing npm setup, the official package is:

```bash
npm install -g @openai/codex
codex
```

Sign in with the account/plan you intend to use. Do not paste an API key into a project, prompt or workflow setting. There is also an official standalone installer, so Node/npm are not prerequisites for ResearchFlow itself.

Then return to `researchflow doctor` and `researchflow demo --live`.

## Official references checked for this build

- Python installers: https://www.python.org/downloads/macos/
- Claude CLI flags and permissions: https://code.claude.com/docs/en/cli-reference
- Cursor installation: https://cursor.com/docs/cli/installation
- Cursor model selection and account discovery: https://cursor.com/docs/cli/reference/parameters
- Codex installation: https://github.com/openai/codex
- Codex scripted mode: https://developers.openai.com/codex/noninteractive/

Vendor CLIs can change independently of ResearchFlow. Its adapters fail visibly when required flags/output formats are missing; a documentation check is not proof of live compatibility. Managed enterprise policy can impose additional behavior outside this kit's control.
