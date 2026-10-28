"""Small shared pieces: files, local locks, and bounded child processes.

Locks coordinate cooperating processes on a local filesystem. They are not a
security boundary against another program running as the same OS user.
"""
from __future__ import annotations
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time
import uuid

class FlowError(Exception):
    pass

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def uid():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]

def digest(data):
    return hashlib.sha256(data).hexdigest()

def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True).encode()

def identity(value):
    return digest(encoded(value))

def home():
    return Path(os.environ.get("RESEARCHFLOW_HOME", "~/ResearchFlow")).expanduser().resolve()

def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise FlowError(f"Refusing symlink as record directory: {path}")
    return path

def write(path, data):
    """Atomic private file write; no truncation of an existing symlink target."""
    path = Path(path)
    private_dir(path.parent)
    raw = data.encode() if isinstance(data, str) else data
    temp = path.parent / (".tmp-" + uuid.uuid4().hex)
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)

def save(path, value):
    write(Path(path), json.dumps(value, indent=2, ensure_ascii=True) + "\n")

def load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise FlowError(f"Cannot read {path}: {exc}") from exc

@contextlib.contextmanager
def lock(path, shared=False):
    """Never unlink the lock file: otherwise two owners can lock two inodes."""
    private_dir(path.parent)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        try:
            fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise FlowError("This project is already busy. Finish its other ResearchFlow operation first.") from exc
        yield
    finally:
        os.close(fd)

def child_env(extra=None):
    # Do not inherit Git redirects/config injection, Python import redirects,
    # or the active Claude session marker into a worker.
    allow = {"PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "TERM",
             "TMPDIR", "SYSTEMROOT", "SSL_CERT_FILE", "SSL_CERT_DIR"}
    env = {k: v for k, v in os.environ.items() if k in allow}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
                "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
    if extra:
        env.update(extra)
    return env

def run(argv, cwd, *, timeout=120, stdin=None, env=None, limit=2_000_000):
    """Run literal argv; bound output and cleanup (including inherited pipes).

No reader threads and no buffered-close race. Kill the process group on timeout
or output overflow. A deliberately detached descendant is not guaranteed killed;
OS isolation is needed for hostile programs.
"""
    if not argv or not all(isinstance(x, str) and '\0' not in x for x in argv):
        raise FlowError("Command must be a nonempty list of strings.")
    started = now()
    start = time.monotonic()
    result = {"argv": argv, "cwd": str(cwd), "started": started, "exit_code": None,
              "reason": None, "stdout": "", "stderr": ""}
    # A regular temporary input file avoids a blocking write of a large prompt.
    import tempfile
    with tempfile.TemporaryFile() as inp:
        if stdin is not None:
            inp.write(stdin.encode() if isinstance(stdin, str) else stdin)
        inp.seek(0)
        try:
            p = subprocess.Popen(argv, cwd=cwd, env=env or child_env(), stdin=inp,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 start_new_session=True, bufsize=0)
        except OSError as exc:
            result.update(reason="unavailable", stderr=str(exc), ended=now())
            return result
        streams = {p.stdout: bytearray(), p.stderr: bytearray()}
        sel = selectors.DefaultSelector()
        for pipe in streams:
            os.set_blocking(pipe.fileno(), False)
            sel.register(pipe, selectors.EVENT_READ)
        killed_at = None
        def kill_group():
            nonlocal killed_at
            if killed_at is None:
                killed_at = time.monotonic()
                # Reap first. macOS returns EPERM, not ESRCH, for killpg on an
                # unreaped exited session leader, which would abort cleanup.
                if p.poll() is not None:
                    return
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    if p.poll() is None:
                        raise
        try:
            while sel.get_map() or p.poll() is None:
                elapsed = time.monotonic() - start
                if elapsed >= timeout and not result["reason"]:
                    result["reason"] = "timeout"
                    kill_group()
                if killed_at is not None and time.monotonic() - killed_at >= 1:
                    break
                for key, _ in sel.select(0.05):
                    pipe = key.fileobj
                    try:
                        chunk = os.read(pipe.fileno(), 65536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        sel.unregister(pipe)
                        continue
                    available = max(0, limit - sum(len(x) for x in streams.values()))
                    streams[pipe].extend(chunk[:available])
                    if len(chunk) > available and not result["reason"]:
                        result["reason"] = "output_limit"
                        kill_group()
            if p.poll() is None:
                kill_group()
            try:
                result["exit_code"] = p.wait(timeout=1)
            except subprocess.TimeoutExpired:
                result["reason"] = result["reason"] or "cleanup_timeout"
        except BaseException:
            kill_group()
            try:
                p.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            raise
        finally:
            sel.close()
            for pipe in streams:
                pipe.close()
        result["stdout"] = streams[p.stdout].decode("utf-8", "replace")
        result["stderr"] = streams[p.stderr].decode("utf-8", "replace")
        result["ended"] = now()
        result["seconds"] = round(time.monotonic() - start, 3)
        return result

def checked(argv, cwd, **kwargs):
    result = run(argv, cwd, **kwargs)
    if result["exit_code"] != 0 or result["reason"]:
        raise FlowError(f"Command failed ({result['reason'] or result['exit_code']}): "
                        f"{argv[0]}\n{result['stderr'][-1500:]}")
    return result["stdout"]

def within(root, relative):
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts:
        raise FlowError(f"Expected a relative project path: {relative}")
    target = root / rel
    if not target.resolve().is_relative_to(root.resolve()):
        raise FlowError(f"Path escapes the project: {relative}")
    return target
