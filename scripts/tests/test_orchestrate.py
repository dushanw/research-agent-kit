"""Offline tests for scripts/orchestrate.py.

Run from the kit (or any repo the kit is installed in):

    python3 -m unittest discover -s scripts/tests -v

No real Claude/Codex/Cursor CLI is invoked: fake executables (fake_cli.py) are placed on
PATH. Every integration test builds a throwaway Git repository under a temporary
directory whose path contains spaces.
"""
from __future__ import annotations

import builtins
import contextlib
import io
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import make_sandbox  # noqa: E402
import orchestrate as orch  # noqa: E402

TEST_CMD = ".venv/bin/python -m unittest discover -s tests -t ."


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True).stdout.strip()


# --------------------------------------------------------------------------- unit tests

class TaskSchemaTest(unittest.TestCase):
    def test_current_task_is_valid(self):
        parsed = orch.parse_task((SCRIPTS.parent / "tasks" / "current.md").read_text())
        self.assertEqual(parsed["errors"], [])
        self.assertEqual(parsed["declared_test_command"], TEST_CMD)

    def test_template_is_rejected_until_filled(self):
        parsed = orch.parse_task((SCRIPTS.parent / "tasks" / "TEMPLATE.md").read_text())
        self.assertTrue(any("placeholder" in e for e in parsed["errors"]))

    def test_missing_sections(self):
        parsed = orch.parse_task("# Task: x\n\n## Scope\nsomething\n")
        joined = " ".join(parsed["errors"])
        for name in ("Owner", "Success Criteria", "Test Command", "Reproducibility"):
            self.assertIn(name, joined)


class VerdictParsingTest(unittest.TestCase):
    def test_parses_last_valid_line_with_nonce(self):
        text = ('REVIEW_VERDICT_JSON[abc]: {"max_severity": "none", "findings": []}\n'
                'REVIEW_VERDICT_JSON[abc]: {"max_severity": "low", "findings": '
                '[{"severity": "high", "file": "a.py", "line": 3, "title": "t"}]}\n')
        v = orch.parse_verdict(text, "abc")
        self.assertTrue(v["parsed"])
        self.assertEqual(v["max_severity"], "high")  # escalated by finding severity

    def test_wrong_nonce_or_bad_json_is_unparsed(self):
        self.assertFalse(orch.parse_verdict(
            'REVIEW_VERDICT_JSON[zzz]: {"max_severity": "none"}', "abc")["parsed"])
        self.assertFalse(orch.parse_verdict(
            'REVIEW_VERDICT_JSON[abc]: {"max_severity": "fine"}', "abc")["parsed"])
        self.assertFalse(orch.parse_verdict("no verdict", "abc")["parsed"])

    def test_text_mentioning_high_is_flagged(self):
        v = orch.parse_verdict('1. [high] bug\nREVIEW_VERDICT_JSON[n]: {"max_severity": "none"}', "n")
        self.assertTrue(v["text_mentions_severe"])
        d = {"state": "awaiting_decision", "stages": {"tests": {"status": "passed"},
             "review": {"status": "completed", "verdict": v}}}
        a = orch.assess(d)
        self.assertTrue(a["approvable"])
        self.assertTrue(a["overridable_blockers"])


class AssessmentTest(unittest.TestCase):
    def base(self, **over):
        d = {"state": "awaiting_decision", "stages": {
            "tests": {"status": "passed"},
            "review": {"status": "completed", "verdict": {"parsed": True, "max_severity": "low",
                                                          "findings": [], "evidence_sufficient": True}}},
             "integrity": [], "warnings": []}
        d.update(over)
        return d

    def test_clean_is_approvable_but_not_approved(self):
        d = self.base()
        self.assertTrue(orch.assess(d)["approvable"])
        self.assertIn("NOT YET APPROVED", orch.verdict_label(d))

    def test_skipped_tests_never_approvable(self):
        d = self.base()
        d["stages"]["tests"] = {"status": "skipped"}
        self.assertFalse(orch.assess(d)["approvable"])
        self.assertIn("NOT APPROVED", orch.verdict_label(d))

    def test_severe_review_with_exit_zero_needs_override(self):
        d = self.base()
        d["stages"]["review"]["verdict"]["max_severity"] = "critical"
        a = orch.assess(d)
        self.assertTrue(any("CRITICAL" in b for b in a["overridable_blockers"]))
        self.assertIn("BLOCKING FINDINGS", orch.verdict_label(d))

    def test_failed_integrity_is_hard_blocker(self):
        d = self.base(integrity=[{"check": "x", "ok": False, "detail": ""}])
        self.assertFalse(orch.assess(d)["approvable"])


class ReviewPolicyTest(unittest.TestCase):
    def test_secret_detection(self):
        self.assertIsNotNone(orch.secret_reason(".env", b"X=1"))
        self.assertIsNotNone(orch.secret_reason("pkg/id_rsa", b""))
        self.assertIsNone(orch.secret_reason(".env.example", b"X="))
        self.assertIsNotNone(orch.secret_reason("a.py", b'token = "AKIAABCDEFGHIJKLMNOP"'))
        self.assertIsNotNone(orch.secret_reason("a.py", b"-----BEGIN RSA PRIVATE KEY-----"))
        self.assertIsNone(orch.secret_reason("a.py", b"def f():\n    return 1\n"))

    def test_binary_detection(self):
        self.assertTrue(orch.is_binary(b"abc\x00def"))
        self.assertFalse(orch.is_binary("naïve text".encode()))


class TestCommandPolicyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="orch cmd "))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / ".venv" / "bin").mkdir(parents=True)
        py = self.tmp / ".venv" / "bin" / "python"
        py.write_text("#!/bin/sh\n")
        py.chmod(0o755)

    def test_no_shell_and_literal_args(self):
        argv, notes = orch.parse_test_command(".venv/bin/python -m pytest -k 'a and b' $HOME",
                                              self.tmp, self.tmp, False)
        self.assertEqual(argv, [".venv/bin/python", "-m", "pytest", "-k", "a and b", "$HOME"])
        self.assertTrue(any("passed literally" in n for n in notes))

    def test_shell_wrapper_requires_opt_in(self):
        with self.assertRaises(orch.OrchestratorError):
            orch.parse_test_command("bash -c 'pytest; rm -rf x'", self.tmp, self.tmp, False)
        argv, _ = orch.parse_test_command("/bin/sh -c true", self.tmp, self.tmp, True)
        self.assertEqual(argv[0], "/bin/sh")

    def test_missing_executable(self):
        with self.assertRaises(orch.OrchestratorError):
            orch.parse_test_command("venv2/bin/python -m pytest", self.tmp, self.tmp, False)
        with self.assertRaises(orch.OrchestratorError):
            orch.parse_test_command("definitely-not-a-binary-xyz", self.tmp, self.tmp, False)

    def test_env_is_sanitised(self):
        with mock.patch.dict(os.environ, {"PYTHONPATH": "/main/checkout", "VIRTUAL_ENV": "/v",
                                          "GIT_DIR": "/other/.git"}):
            env = orch.test_env()
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("VIRTUAL_ENV", env)
        self.assertNotIn("GIT_DIR", env)


class ProcessRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="orch proc "))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_timeout_kills_process_group(self):
        code = ("import subprocess,sys,time;"
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']);"
                "open('child.pid','w').write(str(p.pid)); time.sleep(60)")
        res = orch.run_process([sys.executable, "-c", code], self.tmp, log_path=self.tmp / "log",
                               timeout=2)
        self.assertTrue(res.timed_out)
        self.assertFalse(res.ok)
        child = int((self.tmp / "child.pid").read_text())
        deadline = time.time() + 5
        while orch.pid_alive(child) and time.time() < deadline:
            time.sleep(0.1)
        self.assertFalse(orch.pid_alive(child), "grandchild survived timeout")
        self.assertIn("TIMEOUT", (self.tmp / "log").read_text())

    def test_large_output_is_capped(self):
        res = orch.run_process([sys.executable, "-c", "print('z' * 3_000_000)"], self.tmp,
                               log_path=self.tmp / "log", timeout=30, max_log_bytes=100_000)
        self.assertTrue(res.ok)
        self.assertTrue(res.truncated)
        self.assertGreater(res.bytes_total, 3_000_000 - 1)
        self.assertLess((self.tmp / "log").stat().st_size, 101_000)
        self.assertEqual(stat.S_IMODE((self.tmp / "log").stat().st_mode), 0o600)

    def test_missing_binary_and_nonzero_exit(self):
        res = orch.run_process(["no-such-binary-xyz"], self.tmp)
        self.assertIn("not found", res.error)
        res = orch.run_process([sys.executable, "-c", "import sys; sys.exit(7)"], self.tmp)
        self.assertEqual(res.returncode, 7)
        self.assertFalse(res.ok)


# --------------------------------------------------------------------------- integration harness

class Sandbox(unittest.TestCase):
    """Builds `<tmp>/my repo` (kit + example package) and fake CLIs on PATH."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="orch it "))
        self.addCleanup(self._cleanup)
        self.repo = make_sandbox.build(self.tmp / "my repo")
        self.logdir = self.tmp / "fake logs"
        self.bindir = self.tmp / "fake bin"
        self.bindir.mkdir()
        for tool in ("claude", "codex"):
            w = self.bindir / tool
            w.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{HERE / "fake_cli.py"}" {tool} "$@"\n')
            w.chmod(0o755)
        gitconfig = self.tmp / "gitconfig"
        gitconfig.write_text("")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("FAKE_", "GIT_"))}
        self.env.update({
            "PATH": f"{self.bindir}:/usr/bin:/bin:/usr/sbin:/sbin",
            "FAKE_LOG_DIR": str(self.logdir), "GIT_CONFIG_GLOBAL": str(gitconfig),
            "GIT_CONFIG_NOSYSTEM": "1",
        })
        self.main_head = git(self.repo, "rev-parse", "HEAD")
        self.pids = []

    def _cleanup(self):
        for pid in self.pids:
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def orch(self, *args, env=None, cwd=None, timeout=180):
        e = dict(self.env)
        e.update(env or {})
        return subprocess.run([sys.executable, str(self.repo / "scripts" / "orchestrate.py"), *args],
                              cwd=cwd or self.repo, env=e, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, timeout=timeout)

    def prepare(self, task_id="t1"):
        r = self.orch("prepare", "--id", task_id)
        self.assertEqual(r.returncode, 0, r.stdout)
        wt = self.tmp / f"my repo-agent-{task_id}"
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(wt / ".venv")], check=True)
        return wt

    def runs(self):
        base = self.repo / ".agent-runs" / "runs"
        return sorted((json.loads((p / "run.json").read_text()) for p in base.iterdir()),
                      key=lambda d: d["created_at"] + d["run_id"])

    def last(self):
        return self.runs()[-1]

    def assert_main_untouched(self):
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), self.main_head)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertEqual(git(self.repo, "branch", "--show-current"), "main")


class DoctorTest(Sandbox):
    def test_doctor_outside_git_with_tools_missing(self):
        lone = self.tmp / "not a repo"
        lone.mkdir()
        shutil.copy2(SCRIPTS / "orchestrate.py", lone / "orchestrate.py")
        r = subprocess.run([sys.executable, str(lone / "orchestrate.py"), "doctor"], cwd=lone,
                           env={**self.env, "PATH": "/usr/bin:/bin"}, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stdout)
        self.assertIn("claude not found", r.stdout)
        self.assertIn("not inside a Git working tree", r.stdout)
        self.assertIn("[PASS] git", r.stdout)

    def test_doctor_ready_in_sandbox_and_auth_not_claimed(self):
        r = self.orch("doctor")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("READY", r.stdout)
        self.assertIn("NOT CHECKED", r.stdout)
        self.assertIn("deterministic normalization helper", r.stdout)

    def test_doctor_reports_incompatible_codex(self):
        r = self.orch("doctor", env={"FAKE_CODEX_HELP": "nosandbox"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not advertise required options", r.stdout)


class PrepareTest(Sandbox):
    def test_prepare_creates_bound_worktree_and_keeps_main_intact(self):
        wt = self.prepare("t1")
        self.assertEqual(git(wt, "branch", "--show-current"), "agent/t1")
        rec = json.loads((self.repo / ".agent-runs" / "tasks" / "t1" / "task.json").read_text())
        self.assertEqual(rec["base_commit"], self.main_head)
        self.assertEqual(len(rec["task_sha256"]), 64)
        self.assert_main_untouched()
        again = self.orch("prepare", "--id", "t1")
        self.assertEqual(again.returncode, 1)
        self.assertIn("already exists", again.stdout)

    def test_prepare_refuses_collisions_dirty_repo_bad_ids(self):
        (self.tmp / "my repo-agent-t2").mkdir()
        r = self.orch("prepare", "--id", "t2")
        self.assertIn("path already exists", r.stdout)
        self.assertEqual(r.returncode, 1)
        r = self.orch("prepare", "--id", "Bad ID")
        self.assertIn("invalid task id", r.stdout)
        (self.repo / "scratch.txt").write_text("uncommitted")
        r = self.orch("prepare", "--id", "t3")
        self.assertIn("uncommitted/untracked", r.stdout)
        self.assertFalse((self.tmp / "my repo-agent-t3").exists())

    def test_prepare_requires_agent_runs_ignored(self):
        gi = self.repo / ".gitignore"
        gi.write_text(gi.read_text().replace(".agent-runs/\n", ""))
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qam", "x")
        r = self.orch("prepare", "--id", "t1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not ignored", r.stdout)

    def test_refuses_when_cwd_is_another_repository(self):
        other = self.tmp / "other repo"
        other.mkdir()
        git(other, "init", "-q")
        r = self.orch("status", cwd=other)
        self.assertEqual(r.returncode, 1)
        self.assertIn("different repository", r.stdout)
        r = self.orch("status", "--repo", str(self.repo), cwd=other)
        self.assertEqual(r.returncode, 0, r.stdout)


class RunTest(Sandbox):
    def test_success_includes_untracked_content_and_is_not_approval(self):
        wt = self.prepare()
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD)
        self.assertEqual(r.returncode, 0, r.stdout)
        d = self.last()
        self.assertEqual(d["state"], "awaiting_decision")
        self.assertEqual(d["stages"]["tests"]["status"], "passed")
        self.assertIsNone(d["decision"])
        self.assertIn("NOT YET APPROVED", d["verdict_label"])
        files = {f["path"]: f for f in d["review_material"]["files"]}
        self.assertIn("untracked", files["tests/test_normalize.py"]["origin"])
        self.assertIn("unstaged", files["research_demo/__init__.py"]["origin"])
        prompt = (self.logdir / "codex_prompt.txt").read_text()
        self.assertIn("def zscore", prompt)              # untracked file *content* reviewed
        self.assertIn("class ZScoreTest", prompt)
        cargs = json.loads((self.logdir / "codex_argv.json").read_text())["argv"]
        self.assertEqual(cargs[:2], ["--sandbox", "read-only"])
        claude_argv = json.loads((self.logdir / "claude_argv.json").read_text())["argv"]
        self.assertIn("--strict-mcp-config", claude_argv)
        self.assertEqual(claude_argv[-3:], ["Bash", "WebFetch", "WebSearch"])
        self.assertNotIn("bypassPermissions", claude_argv)
        self.assertNotIn("--dangerously-skip-permissions", claude_argv)
        run_dir = self.repo / ".agent-runs" / "runs" / d["run_id"]
        for name in ("summary.md", "events.jsonl", "claude.log", "tests.log", "review.log",
                     "review-material.md"):
            self.assertTrue((run_dir / name).is_file(), name)
        self.assertEqual(stat.S_IMODE(run_dir.stat().st_mode), 0o700)
        # Nothing committed/merged anywhere.
        self.assertEqual(git(wt, "rev-parse", "HEAD"), self.main_head)
        self.assert_main_untouched()

    def test_severe_review_exit_zero_blocks_approval(self):
        self.prepare()
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD, env={"FAKE_CODEX_MODE": "severe"})
        self.assertEqual(r.returncode, orch.EXIT_NOT_APPROVABLE, r.stdout)  # codex itself exited 0
        d = self.last()
        self.assertEqual(d["stages"]["review"]["returncode"], 0)
        self.assertEqual(d["stages"]["review"]["verdict"]["max_severity"], "critical")
        self.assertIn("BLOCKING FINDINGS", d["verdict_label"])
        self.assertTrue(d["assessment"]["overridable_blockers"])
        self.assert_main_untouched()
        self.assertEqual(git(self.repo, "rev-list", "--count", "main..agent/t1"), "0")

    def test_failed_tests_stop_before_review(self):
        self.prepare()
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD, env={"FAKE_CLAUDE_MODE": "impl_bad"})
        self.assertEqual(r.returncode, 1)
        d = self.last()
        self.assertEqual(d["state"], "failed")
        self.assertEqual(d["stages"]["tests"]["status"], "failed")
        self.assertNotIn("review", d["stages"])
        self.assertIn("FAILED - NOT APPROVED", d["verdict_label"])
        self.assertFalse((self.logdir / "codex_prompt.txt").exists())

    def test_skip_tests_is_never_approvable(self):
        self.prepare()
        r = self.orch("run", "--id", "t1", "--skip-tests")
        self.assertEqual(r.returncode, orch.EXIT_NOT_APPROVABLE, r.stdout)
        d = self.last()
        self.assertEqual(d["stages"]["tests"]["status"], "skipped")
        self.assertFalse(d["assessment"]["approvable"])
        self.assertIn("NOT APPROVED", d["verdict_label"])

    def test_claude_failure_and_timeout(self):
        self.prepare()
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD, env={"FAKE_CLAUDE_MODE": "fail"})
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.last()["failure"]["stage"], "implement")
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD, "--claude-timeout", "2",
                      env={"FAKE_CLAUDE_MODE": "sleep"})
        self.assertEqual(r.returncode, 1, r.stdout)
        d = self.last()
        self.assertTrue(d["stages"]["implement"]["timed_out"])
        pid = int((self.logdir / "claude.pid").read_text())
        time.sleep(0.5)
        self.assertFalse(orch.pid_alive(pid))

    def test_incompatible_cli_fails_before_any_change(self):
        wt = self.prepare()
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD, env={"FAKE_CODEX_HELP": "nosandbox"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("codex CLI unusable", r.stdout)
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD, env={"FAKE_CLAUDE_HELP": "no-strict-mcp"})
        self.assertIn("--strict-mcp-config", r.stdout)
        self.assertFalse((self.logdir / "claude_argv.json").exists())
        self.assertEqual(git(wt, "status", "--porcelain"), "")

    def test_codex_nonzero_and_missing_verdict(self):
        self.prepare()
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD, env={"FAKE_CODEX_MODE": "fail"})
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.last()["failure"]["stage"], "review")
        r = self.orch("verify", "--id", "t1", "--test-command", TEST_CMD, env={"FAKE_CODEX_MODE": "noverdict"})
        self.assertEqual(r.returncode, orch.EXIT_NOT_APPROVABLE, r.stdout)
        d = self.last()
        self.assertFalse(d["stages"]["review"]["verdict"]["parsed"])
        self.assertTrue(any("unparseable" in b for b in d["assessment"]["overridable_blockers"]))
        r = self.orch("verify", "--id", "t1", "--test-command", TEST_CMD, env={"FAKE_CODEX_MODE": "injected"})
        self.assertFalse(self.last()["stages"]["review"]["verdict"]["parsed"])
        r = self.orch("verify", "--id", "t1", "--test-command", TEST_CMD, env={"FAKE_CODEX_MODE": "lie"})
        self.assertTrue(any("mentions high" in b for b in self.last()["assessment"]["overridable_blockers"]))

    def test_review_that_modifies_worktree_is_caught(self):
        self.prepare()
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD, env={"FAKE_CODEX_MODE": "modify"})
        self.assertEqual(r.returncode, 1, r.stdout)
        d = self.last()
        self.assertEqual(d["failure"]["stage"], "review")
        self.assertTrue(any(not c["ok"] for c in d["integrity"]))

    def test_agent_editing_its_task_or_main_repo_is_caught(self):
        self.prepare("t1")
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD, env={"FAKE_CLAUDE_MODE": "impl_good,modify_task"})
        self.assertEqual(r.returncode, 1)
        self.assertTrue(any(c["check"] == "task file unchanged by agent" and not c["ok"]
                            for c in self.last()["integrity"]))
        # A later verify refuses because the bound task no longer matches.
        r = self.orch("verify", "--id", "t1", "--test-command", TEST_CMD)
        self.assertIn("differs from the snapshot", r.stdout)

        self.prepare("t2")
        outside = self.repo / "research_demo" / "stats.py"
        r = self.orch("run", "--id", "t2", "--test-command", TEST_CMD,
                      env={"FAKE_CLAUDE_MODE": "impl_good,outside", "FAKE_OUTSIDE_PATH": str(outside)})
        self.assertEqual(r.returncode, 1)
        self.assertTrue(any(c["check"].startswith("main repository unchanged") and not c["ok"]
                            for c in self.last()["integrity"]))
        git(self.repo, "checkout", "--", "research_demo/stats.py")  # restore the test sandbox

    def test_agent_commit_is_caught(self):
        self.prepare()
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD,
                      env={"FAKE_CLAUDE_MODE": "impl_good,commit"})
        self.assertEqual(r.returncode, 1)
        self.assertTrue(any(c["check"].startswith("agent did not commit") and not c["ok"]
                            for c in self.last()["integrity"]))

    def test_secrets_binaries_data_ignored_and_symlinks_are_withheld(self):
        self.prepare()
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD,
                      env={"FAKE_CLAUDE_MODE": "impl_good,write_env,secret_file,binary,data_file,symlink"})
        self.assertEqual(r.returncode, orch.EXIT_OK, r.stdout)
        d = self.last()
        files = {f["path"]: f for f in d["review_material"]["files"]}
        self.assertIn("possible secret", files["research_demo/settings_local.py"]["withheld"])
        self.assertIn("binary", files["research_demo/blob.bin"]["withheld"])
        self.assertIn("data-file", files["research_demo/measurements.csv"]["withheld"])
        self.assertEqual(files["research_demo/hosts_link"]["symlink_target"], "/etc/hosts")
        prompt = (self.logdir / "codex_prompt.txt").read_text()
        self.assertNotIn("sk-ant-api03", prompt)
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", prompt)
        self.assertIn("def zscore", prompt)
        self.assertIn(".env", d["new_ignored_entries"])
        self.assertTrue(any("IGNORED path" in w for w in d["warnings"]))
        self.assertFalse((self.repo / ".agent-runs" / "runs" / d["run_id"] / "review-material.md")
                         .read_text().count("AKIA"))

    def test_large_claude_output_is_capped(self):
        self.prepare()
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD, "--max-log-bytes", "200000",
                      env={"FAKE_CLAUDE_MODE": "impl_good,big_output"})
        self.assertEqual(r.returncode, 0, r.stdout)
        imp = self.last()["stages"]["implement"]
        self.assertTrue(imp["log_truncated"])
        self.assertGreater(imp["bytes_total"], 3_000_000)

    def test_live_lock_blocks_second_run_without_creating_a_record(self):
        self.prepare()
        lock = self.repo / ".agent-runs" / "tasks" / "t1" / "lock"
        holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.pids.append(holder.pid)
        lock.write_text(json.dumps({"pid": holder.pid, "host": orch.socket.gethostname(),
                                    "run_id": "other"}))
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD)
        self.assertEqual(r.returncode, 1)
        self.assertIn("task is locked", r.stdout)
        self.assertFalse((self.repo / ".agent-runs" / "runs").exists())
        holder.kill()
        holder.wait()
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD)  # dead holder: lock cleared
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_run_refuses_dirty_worktree(self):
        wt = self.prepare()
        (wt / "notes.txt").write_text("human work in progress")
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not clean", r.stdout)
        self.assertEqual((wt / "notes.txt").read_text(), "human work in progress")


class InterruptTest(Sandbox):
    def _start(self, extra_env):
        e = dict(self.env)
        e.update(extra_env)
        p = subprocess.Popen([sys.executable, str(self.repo / "scripts" / "orchestrate.py"), "run",
                              "--id", "t1", "--test-command", TEST_CMD], cwd=self.repo, env=e,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        deadline = time.time() + 60
        while not (self.logdir / "claude.pid").exists() and time.time() < deadline:
            time.sleep(0.1)
        time.sleep(0.3)
        child = int((self.logdir / "claude.pid").read_text())
        self.pids.append(child)
        return p, child

    def test_ctrl_c_and_sigterm_leave_inspectable_interrupted_runs(self):
        self.prepare()
        for sig in (signal.SIGINT, signal.SIGTERM):
            (self.logdir / "claude.pid").unlink(missing_ok=True)
            p, child = self._start({"FAKE_CLAUDE_MODE": "sleep"})
            p.send_signal(sig)
            out, _ = p.communicate(timeout=60)
            self.assertEqual(p.returncode, orch.EXIT_INTERRUPTED, out)
            d = self.last()
            self.assertEqual(d["state"], "interrupted")
            self.assertIn("INTERRUPTED - NOT APPROVED", d["verdict_label"])
            time.sleep(0.5)
            self.assertFalse(orch.pid_alive(child), "agent process survived interrupt")
            self.assertFalse((self.repo / ".agent-runs" / "tasks" / "t1" / "lock").exists())

    def test_sigkill_shows_stale_then_marked_interrupted(self):
        self.prepare()
        p, child = self._start({"FAKE_CLAUDE_MODE": "sleep"})
        p.kill()
        p.communicate(timeout=30)
        os.kill(child, signal.SIGKILL)
        d = self.last()
        self.assertEqual(d["state"], "implementing")
        r = self.orch("status")
        self.assertIn("STALE", r.stdout)
        # The next verify cleans the stale lock and records the dead run as interrupted.
        r = self.orch("verify", "--id", "t1", "--skip-tests")
        self.assertIn("no changes relative to the base commit", r.stdout)
        states = [x["state"] for x in self.runs()]
        self.assertEqual(states[0], "interrupted")


class RecoveryAndDecisionTest(Sandbox):
    def decide(self, *args, tty=True, typed=None):
        out = io.StringIO()

        class FakeStdin(io.StringIO):
            def isatty(self):
                return tty

        with mock.patch.object(orch.sys, "stdin", FakeStdin()), \
                mock.patch.object(builtins, "input", lambda _prompt="": typed or ""), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), \
                mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": self.env["GIT_CONFIG_GLOBAL"]}):
            rc = orch.main(["decide", "--repo", str(self.repo), *args])
        return rc, out.getvalue()

    def test_fix_reverify_decide_and_check_promotion(self):
        wt = self.prepare()
        r = self.orch("run", "--id", "t1", "--test-command", TEST_CMD, env={"FAKE_CLAUDE_MODE": "impl_bad"})
        self.assertEqual(r.returncode, 1)
        failed = self.last()["run_id"]
        # Human fixes the bug in the same worktree (work is preserved), then re-verifies.
        sys.path.insert(0, str(HERE))
        import fake_cli
        (wt / "research_demo" / "normalize.py").write_text(fake_cli.NORMALIZE_GOOD)
        r = self.orch("verify", "--id", "t1", "--test-command", TEST_CMD)
        self.assertEqual(r.returncode, 0, r.stdout)
        d = self.last()
        self.assertEqual(d["kind"], "verify")
        self.assertEqual(d["parent_run"], failed)
        run_id, tree = d["run_id"], d["fingerprints"]["verified"]

        rc, out = self.decide("--run", failed, "--approve", "--reviewer", "me", "--note", "looks ok")
        self.assertEqual(rc, 1)
        self.assertIn("only runs awaiting a decision", out)
        rc, out = self.decide("--run", run_id, "--approve", "--reviewer", "me", "--note", "looks ok", tty=False)
        self.assertIn("interactively", out)
        rc, out = self.decide("--run", run_id, "--approve", "--reviewer", "me", "--note", "looks ok",
                              typed="wrong")
        self.assertIn("did not match", out)
        self.assertEqual(self.last()["state"], "awaiting_decision")

        (wt / "research_demo" / "normalize.py").write_text(fake_cli.NORMALIZE_GOOD + "\n# edited\n")
        rc, out = self.decide("--run", run_id, "--approve", "--reviewer", "me", "--note", "looks ok",
                              typed=tree[:8])
        self.assertIn("changed since this run verified", out)
        (wt / "research_demo" / "normalize.py").write_text(fake_cli.NORMALIZE_GOOD)

        rc, out = self.decide("--run", run_id, "--approve", "--reviewer", "me", "--note", "reviewed diff",
                              typed=tree[:8])
        self.assertEqual(rc, 0, out)
        d = self.last()
        self.assertEqual(d["decision"]["decision"], "approved")
        self.assertEqual(d["decision"]["verified_tree"], tree)

        # Not committed yet -> promotion check fails and changes nothing.
        r = self.orch("check-promotion", "--run", run_id)
        self.assertEqual(r.returncode, 1)
        self.assertIn("NOT READY", r.stdout)
        # Human commits exactly the verified content in the worktree.
        git(wt, "add", "-A")
        git(wt, "-c", "user.name=h", "-c", "user.email=h@example.invalid", "commit", "-qm", "normalize")
        r = self.orch("check-promotion", "--run", run_id)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("git merge --no-ff --no-commit agent/t1", r.stdout)
        self.assertIn("NOT executed", r.stdout)
        self.assert_main_untouched()  # still nothing merged

    def test_severe_findings_require_written_override(self):
        self.prepare()
        self.orch("run", "--id", "t1", "--test-command", TEST_CMD, env={"FAKE_CODEX_MODE": "severe"})
        d = self.last()
        tree = d["fingerprints"]["verified"]
        rc, out = self.decide("--run", d["run_id"], "--approve", "--reviewer", "me", "--note", "ship it",
                              typed=tree[:8])
        self.assertEqual(rc, 1)
        self.assertIn("CRITICAL", out)
        self.assertEqual(self.last()["state"], "awaiting_decision")
        rc, out = self.decide("--run", d["run_id"], "--reject", "--reviewer", "me", "--note", "critical bug")
        self.assertEqual(rc, 0, out)
        self.assertIn("REJECTED", self.last()["verdict_label"])
        self.assert_main_untouched()

    def test_report_and_status(self):
        self.prepare()
        self.orch("run", "--id", "t1", "--test-command", TEST_CMD)
        r = self.orch("status", "--id", "t1", "--run", "latest")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("MATCHES the verified tree", r.stdout)
        r = self.orch("report", "--id", "t1", "--run", "latest")
        self.assertIn("## Gates", r.stdout)
        r = self.orch("report", "--id", "t1", "--run", "latest", "--format", "json")
        self.assertEqual(json.loads(r.stdout)["state"], "awaiting_decision")


class ExamplePackageTest(unittest.TestCase):
    def test_example_suite_passes(self):
        ex = SCRIPTS.parent / "examples" / "research_demo"
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                           cwd=ex, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
