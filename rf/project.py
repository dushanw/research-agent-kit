"""Inspect an inherited project, preserve a scoped copy, and own one worktree."""
from __future__ import annotations
import fnmatch
import os
from pathlib import Path
import re
import shutil
import stat
from .support import FlowError, checked, digest, home, identity, load, lock, now, private_dir, save, uid, within, write

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
             ".ruff_cache", "node_modules", "data", "datasets", "outputs", ".agent-runs"}
SECRET_NAMES = [".env", ".env.*", "*.pem", "*.key", "*credentials*", "*secrets*", ".netrc",
                ".npmrc", ".pypirc", "id_rsa*", "id_ed25519*"]
DATA_SUFFIXES = {".npy", ".npz", ".h5", ".hdf5", ".pt", ".pth", ".ckpt", ".parquet",
                ".pkl", ".pickle", ".safetensors", ".csv", ".tsv", ".dcm", ".nii"}
MAX_FILE = 2_000_000
MAX_TOTAL = 30_000_000
MAX_FILES = 3000

def git(root, *args):
    return checked(["git", "--no-pager", "--literal-pathspecs", "-c", "core.hooksPath=" + os.devnull,
                    "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
                    "-c", "core.autocrlf=false", "-c", "core.pager=cat",
                    "-C", str(root), *args], Path(root), timeout=30, limit=8_000_000)

def excluded(name):
    p = Path(name)
    if any(x in SKIP_DIRS for x in p.parts):
        return "environment, data, generated output, or internal directory"
    if any(fnmatch.fnmatch(p.name.lower(), pat) for pat in SECRET_NAMES):
        return "credential-like filename"
    if p.suffix.lower() in DATA_SUFFIXES:
        return "research data/model file"
    return None

def check_name(name):
    if any(ord(c) < 32 for c in name) or '\\' in name or '\ufffd' in name:
        raise FlowError("Unsupported filename (control character, backslash, or invalid UTF-8).")
    p = Path(name)
    if p.is_absolute() or '..' in p.parts or '.git' in p.parts:
        raise FlowError(f"Unsafe source path: {name}")

def capture(root, names=None):
    """Raw-byte identity, independent of Git clean filters. Exclusions are visible."""
    root = Path(root).resolve()
    skipped = []
    if names is None:
        names = []
        for directory, dirs, files in os.walk(root, followlinks=False):
            for name in list(dirs):
                rel = str((Path(directory) / name).relative_to(root))
                p = root / rel
                if p.is_symlink():
                    raise FlowError(f"Source directory symlink is unsupported: {rel}")
                if excluded(rel):
                    dirs.remove(name)
                    if name != '.git':
                        skipped.append(rel + "/")
            for name in files:
                rel = str((Path(directory) / name).relative_to(root))
                if rel == '.git':
                    continue
                names.append(rel)
    contents, manifest = {}, {}
    total = 0
    for name in sorted(set(names)):
        check_name(name)
        reason = excluded(name)
        if reason:
            skipped.append(name)
            continue
        path = within(root, name)
        if path.is_symlink():
            raise FlowError(f"Source file symlink is unsupported: {name}")
        if not path.exists():
            continue
        if not path.is_file():
            raise FlowError(f"Not a regular source file: {name}")
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as fh:
            info = os.fstat(fh.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
                raise FlowError(f"Source file exceeds the 2 MB limit or is not regular: {name}")
            raw = fh.read(MAX_FILE + 1)
        total += len(raw)
        if len(raw) > MAX_FILE or total > MAX_TOTAL or len(manifest) >= MAX_FILES:
            raise FlowError("Source snapshot exceeds its limit. Use a smaller code-only project; keep datasets outside it.")
        contents[name] = raw
        manifest[name] = {"sha256": digest(raw), "bytes": len(raw), "executable": bool(info.st_mode & 0o111)}
    return {"manifest": manifest, "id": identity(manifest), "excluded": sorted(set(skipped))}, contents

def put_snapshot(destination, contents, manifest):
    for name, raw in contents.items():
        target = within(destination, name)
        write(target, raw)
        target.chmod(0o700 if manifest[name]["executable"] else 0o600)

def inspect(path):
    """No project code, filters, hooks, tests, installers, or network are executed."""
    path = Path(path).expanduser().resolve()
    if not path.is_dir():
        raise FlowError(f"Project folder does not exist: {path}")
    root = Path(git(path, "rev-parse", "--show-toplevel").strip()).resolve()
    # Read local config WITHOUT following includes; disallow nontrivial inherited semantics.
    cfg = git(root, "config", "--local", "--no-includes", "--null", "--list")
    keys = [item.split('\n', 1)[0].lower() for item in cfg.split('\0') if item]
    bad = [k for k in keys if k.startswith(('filter.', 'include.', 'includeif.', 'submodule.')) or k == 'core.worktree']
    if bad:
        raise FlowError("Takeover stopped before execution: inspect unsupported Git configuration: " + ', '.join(bad))
    head = git(root, "rev-parse", "--verify", "HEAD").strip()
    tree = git(root, "ls-tree", "-rz", "HEAD")
    head_names = []
    for item in tree.split('\0'):
        if not item:
            continue
        meta, name = item.split('\t', 1)
        mode = meta.split()[0]
        if mode not in {'100644', '100755'}:
            raise FlowError(f"Takeover stopped: symlink or submodule in committed source: {name}")
        check_name(name)
        if excluded(name):
            raise FlowError(f"Tracked sensitive/data/internal file is outside the supported code-only scope: {name}. Original is unchanged.")
        head_names.append(name)
    names = git(root, "ls-files", "-c", "-o", "--exclude-standard", "-z").split('\0')
    names = [n for n in names if n]
    snap, contents = capture(root, names)
    # Attribute transformations can make a checkout differ from the inspected bytes.
    for name in set(head_names) | set(contents):
        if Path(name).name == '.gitattributes':
            raw = contents.get(name, b'')
            committed = git(root, "show", f"HEAD:{name}") if name in head_names else ''
            if re.search(r'\b(filter|working-tree-encoding)\s*=', raw.decode('utf8', 'replace') + committed):
                raise FlowError("Git attribute filters/encoding require a separately prepared code-only checkout.")
    index_name = Path(git(root, "rev-parse", "--git-path", "index").strip())
    index_path = index_name if index_name.is_absolute() else root / index_name
    index = index_path.read_bytes() if index_path.exists() else b''
    report = {"schema": 1, "time": now(), "original": str(root), "head": head,
              "branch": git(root, "branch", "--show-current").strip() or '(detached)',
              "worktrees": git(root, "worktree", "list", "--porcelain"),
              "git_status": git(root, "status", "--porcelain=v1", "-uall"),
              "snapshot": snap, "index_sha256": digest(index), "head_files": head_names,
              "purpose": "Not inferred from code. Claude must inspect requirements and explain the purpose.",
              "not_run": "No project code or model was executed. Ignored files, environments and data were not copied."}
    return report, contents, index

def prepare(path):
    report, contents, index = inspect(path)
    root = Path(report["original"])
    project_id = re.sub(r'[^a-z0-9-]', '-', root.name.lower())[:25] + '-' + digest(str(root).encode())[:10]
    directory = home() / 'projects' / project_id
    private_dir(directory)
    with lock(directory / 'session.lock'), lock(directory / 'operation.lock'):
        if (directory / 'project.json').exists():
            p = load(directory / 'project.json')
            if p.get('schema') != 1:
                raise FlowError("Project record belongs to an unsupported newer format; no changes made.")
            validate_workspace(p)
            if report['snapshot']['id'] != p['takeover_snapshot']:
                raise FlowError('The original changed since takeover. Nothing was refreshed or overwritten. Resume/reconcile in the preserved workspace: ' + p['workspace'])
            return directory, p
        # Recheck before any writes. Other agents must be paused throughout takeover.
        repeat, _, _ = inspect(root)
        if repeat['snapshot']['id'] != report['snapshot']['id'] or repeat['index_sha256'] != report['index_sha256'] or repeat['head'] != report['head']:
            raise FlowError("Original checkout is changing. Pause its writer before takeover.")
        recovery = private_dir(directory / 'recovery')
        put_snapshot(recovery / 'source', contents, report['snapshot']['manifest'])
        save(recovery / 'inventory.json', report)
        write(recovery / 'original-index.bin', index)
        write(recovery / 'READ_ME.md', '# Recovery scope\n\nThe original checkout was not edited. source/ preserves only the included working-file bytes.\noriginal-index.bin preserves the original staged index; do NOT install it into another worktree.\nIgnored files, environments, datasets and excluded files are NOT backed up. Original Git history is still required.\nA Git worktree shares history and metadata, and is not an OS security sandbox.\n')
        workspace = directory / 'workspace'
        branch = 'researchflow/' + project_id + '-' + uid()
        if workspace.exists():
            raise FlowError(f"An unfinished preparation exists at {workspace}. Preserve it and inspect recovery/inventory.json; no overwrite attempted.")
        git(root, 'worktree', 'add', '-b', branch, str(workspace), report['head'])
        for name in report['head_files']:
            target = within(workspace, name)
            if name not in contents and target.is_file():
                target.unlink()  # New dedicated worktree only; mirrors inherited deletions.
        put_snapshot(workspace, contents, report['snapshot']['manifest'])
        actual, _ = capture(workspace)
        if actual['id'] != report['snapshot']['id']:
            raise FlowError(f"Takeover copy mismatch. Preserved workspace and recovery at {directory}; do not continue.")
        repeat, _, _ = inspect(root)
        if repeat['snapshot']['id'] != report['snapshot']['id'] or repeat['index_sha256'] != report['index_sha256'] or repeat['head'] != report['head']:
            raise FlowError("Original changed during preparation. Both folders are preserved; inspect before continuing.")
        p = {"schema": 1, "id": project_id, "created": now(), "original": str(root),
             "workspace": str(workspace), "branch": branch, "original_head": report['head'],
             "takeover_snapshot": report['snapshot']['id'], "latest": None, "task_id": None}
        save(directory / 'project.json', p)
        save(directory / 'takeover.json', report)
        return directory, p

def validate_workspace(project):
    root = Path(project['workspace'])
    if not root.is_dir() or Path(git(root, 'rev-parse', '--show-toplevel').strip()).resolve() != root.resolve():
        raise FlowError("The registered worktree is missing or points to a different project.")
    if git(root, 'branch', '--show-current').strip() != project['branch']:
        raise FlowError("The active worktree branch changed. Inspect before continuing.")
    return root

def locate(project_id=None):
    project_id = project_id or os.environ.get('RESEARCHFLOW_PROJECT')
    if project_id:
        if not re.fullmatch(r'[a-z0-9-]+', project_id):
            raise FlowError('Invalid project identifier.')
        d = home() / 'projects' / project_id
        return d, load(d / 'project.json')
    cwd = Path.cwd().resolve()
    for f in (home() / 'projects').glob('*/project.json'):
        p = load(f)
        if cwd.is_relative_to(Path(p['workspace'])) or cwd == Path(p['original']):
            return f.parent, p
    raise FlowError('No active project. Start with: researchflow start /path/to/project')
