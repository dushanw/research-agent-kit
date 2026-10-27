#!/usr/bin/env python3
"""Create a disposable Git repository for trying the agent workflow safely.

    python3 scripts/make_sandbox.py ~/agent-sandbox

The sandbox contains the kit files plus the synthetic example package
(examples/research_demo) at its root, committed on branch `main`. It refuses to
write into an existing path, so it can never overwrite your work.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
KIT_ITEMS = ["AGENTS.md", "CLAUDE.md", "README.md", "CHANGELOG.md", ".gitignore", ".cursor",
             "docs", "tasks", "scripts"]
EXAMPLE = KIT / "examples" / "research_demo"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".git", ".agent-runs",
                                ".venv", "*.egg-info")


def build(dest: Path, with_venv: bool = False) -> Path:
    dest = dest.expanduser().resolve()
    if dest.exists():
        raise SystemExit(f"refusing to use existing path: {dest}")
    dest.mkdir(parents=True)
    for item in KIT_ITEMS:
        src = KIT / item
        if src.is_dir():
            shutil.copytree(src, dest / item, ignore=IGNORE)
        elif src.is_file():
            shutil.copy2(src, dest / item)
    for src in EXAMPLE.iterdir():
        if src.name in ("README.md", "__pycache__"):
            continue
        target = dest / src.name
        if src.is_dir():
            shutil.copytree(src, target, ignore=IGNORE, dirs_exist_ok=True)
        else:
            shutil.copy2(src, target)
    ident = ["-c", "user.name=agent-sandbox", "-c", "user.email=agent-sandbox@example.invalid",
             "-c", "commit.gpgsign=false"]
    for argv in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"],
                 ["git", *ident, "commit", "-q", "-m", "Sandbox: research-agent-kit + synthetic example"]):
        subprocess.run(argv, cwd=dest, check=True)
    if with_venv:
        subprocess.run([sys.executable, "-m", "venv", str(dest / ".venv")], check=True)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dest", help="new directory to create (must not exist)")
    args = ap.parse_args()
    dest = build(Path(args.dest))
    print(f"Sandbox repository: {dest}")
    print(f"  cd {dest} && python3 scripts/orchestrate.py doctor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
