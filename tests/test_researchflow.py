"""Offline regressions for coordination, evidence, adapters, and inherited work.

All mutation tests use temporary synthetic repositories and fake CLI programs.
No authenticated Claude, Cursor or Codex is called by this suite.
"""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rf import providers as v, project as pr, support as s, workflow as w
from rf.cli import parser

class Temporary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='research flow test ')
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'RESEARCHFLOW_HOME': str(self.root / 'records')}, clear=False)
        self.env.start()
        s.private_dir(s.home())
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.env.stop)

    def repo(self):
        path = self.root / ('repo-' + s.uid())
        shutil.copytree(ROOT / 'examples' / 'tiny-research', path, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        pr.git(path, 'init', '-b', 'main')
        pr.git(path, 'add', '.')
        pr.git(path, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@invalid.example', 'commit', '-m', 'Synthetic baseline')
        return path

    def fakes(self):
        directory = s.private_dir(self.root / 'fake-bin')
        fixture = directory / 'fake_worker.py'
        shutil.copy2(ROOT / 'tests' / 'fake_worker.py', fixture)
        for name in ('agent', 'claude', 'codex'):
            file = directory / name
            file.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(fixture)) + ' ' + name + ' "$@"\n')
            file.chmod(0o700)
        cfg = dict(v.DEFAULTS, cursor_model='fake-independent', codex_model='fake-codex')
        cfg.update(cursor_command=str(directory / 'agent'), claude_command=str(directory / 'claude'), codex_command=str(directory / 'codex'))
        s.save(s.home() / 'settings.json', cfg)
        return directory, cfg

    def prepared_task(self):
        repo = self.repo()
        d, p = pr.prepare(repo)
        t = s.load(ROOT / 'examples' / 'tiny-research' / 'demo-task.json')
        t['tests']['python'] = sys.executable
        w.assign(d, p, t)
        return repo, d, p, t

class SupportTests(Temporary):
    def test_literal_arguments_do_not_expand_shell(self):
        marker = self.root / 'DO_NOT_CREATE'
        r = s.run([sys.executable, '-c', 'import sys; print(sys.argv[1])', '$(touch ' + str(marker) + ')'], self.root)
        self.assertEqual(r['exit_code'], 0)
        self.assertFalse(marker.exists())
        self.assertIn('$(touch', r['stdout'])

    def test_git_python_and_credential_environment_not_inherited(self):
        with patch.dict(os.environ, {'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'core.worktree','GIT_CONFIG_VALUE_0':'/elsewhere',
                                     'PYTHONPATH':'/untrusted','AWS_SECRET_ACCESS_KEY':'invalid','OPENAI_API_KEY':'invalid','CLAUDECODE':'1'}):
            env = s.child_env()
        for key in ('GIT_CONFIG_COUNT','GIT_CONFIG_KEY_0','GIT_CONFIG_VALUE_0','PYTHONPATH','AWS_SECRET_ACCESS_KEY','OPENAI_API_KEY','CLAUDECODE'):
            self.assertNotIn(key, env)
        self.assertEqual(env['GIT_CONFIG_GLOBAL'], os.devnull)

    def test_timeout_returns_with_bounded_cleanup(self):
        begin = time.monotonic()
        r = s.run([sys.executable, '-c', 'import time; time.sleep(30)'], self.root, timeout=.2)
        self.assertEqual(r['reason'], 'timeout')
        self.assertLess(time.monotonic() - begin, 3)

    def test_detached_pipe_holder_does_not_hang(self):
        # Allow interpreter startup; the detached child outlives the deadline. Kill it explicitly afterward.
        code = 'import subprocess,sys; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(15)"],start_new_session=True); print(p.pid,flush=True)'
        begin = time.monotonic()
        r = s.run([sys.executable, '-c', code], self.root, timeout=2)
        self.assertEqual(r['reason'], 'timeout')
        self.assertTrue(r['stdout'].strip().isdigit(), 'Fixture must prove the detached child started')
        try:
            self.assertLess(time.monotonic() - begin, 5)
        finally:
            import signal
            try: os.kill(int(r['stdout'].strip()), signal.SIGKILL)
            except ProcessLookupError: pass

    def test_output_limit_is_not_success(self):
        r = s.run([sys.executable, '-c', 'print("x"*100000)'], self.root, limit=1000)
        self.assertEqual(r['reason'], 'output_limit')
        self.assertLessEqual(len(r['stdout'])+len(r['stderr']), 1000)

    def test_exclusive_lock_never_unlinks_inode(self):
        file = self.root / 'lock'
        with s.lock(file):
            inode = file.stat().st_ino
            with self.assertRaises(s.FlowError):
                with s.lock(file):
                    self.fail('second writer entered')
        with s.lock(file):
            self.assertEqual(file.stat().st_ino, inode)

    def test_shared_session_lock_blocks_installer(self):
        file = self.root / 'install.lock'
        with s.lock(file, shared=True):
            with s.lock(file, shared=True):
                with self.assertRaises(s.FlowError):
                    with s.lock(file):
                        self.fail('upgrade during active sessions')

    def test_symlink_working_directory_escape_rejected(self):
        folder = s.private_dir(self.root / 'source')
        outside = s.private_dir(self.root / 'outside')
        (folder / 'tests').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(s.FlowError):
            s.within(folder, 'tests')

class ReviewTests(Temporary):
    def good(self):
        return {'summary':'Checked synthetic method','evidence_sufficient':True,'findings':[]}

    def test_claude_help_abbreviation_still_requires_the_file_option(self):
        abbreviated = '--append-system-prompt <prompt>\nvia: --append-system-prompt[-file]'
        self.assertTrue(v.option_documented(abbreviated, '--append-system-prompt-file'))
        self.assertTrue(v.option_documented('--append-system-prompt-file', '--append-system-prompt-file'))
        self.assertFalse(v.option_documented('--append-system-prompt <prompt>', '--append-system-prompt-file'))

    def test_cursor_profile_matches_documented_nested_schema(self):
        profile=v.cursor_profile()
        config=s.load(profile/'cli-config.json')
        self.assertEqual(config['editor'],{'vimMode':False})
        self.assertNotIn('editor.vimMode',config)
        self.assertIn('Write(**)',config['permissions']['deny'])
        self.assertIn('Shell(*)',config['permissions']['deny'])

    def test_valid_structured_review(self):
        self.assertEqual(v.review_verdict(json.dumps(self.good())), self.good())

    def test_missing_evidence_cannot_default_to_true(self):
        value = self.good(); del value['evidence_sufficient']
        with self.assertRaises(s.FlowError):
            v.review_verdict(json.dumps(value))

    def test_duplicate_verdict_cannot_erase_high_finding(self):
        high = self.good(); high['findings'] = [{'severity':'high','file':'x.py','problem':'wrong','evidence':'known counterexample'}]
        with self.assertRaises(s.FlowError):
            v.review_verdict(json.dumps(high) + '\n' + json.dumps(self.good()))

    def test_duplicate_keys_rejected(self):
        with self.assertRaises(s.FlowError):
            v.strict_json('{"evidence_sufficient":false,"evidence_sufficient":true}')

    def test_severity_without_evidence_rejected(self):
        value = self.good(); value['findings'] = [{'severity':'high','file':'x','problem':'p','evidence':''}]
        with self.assertRaises(s.FlowError):
            v.review_verdict(json.dumps(value))

    def test_malformed_severity_is_a_controlled_blocker(self):
        value=self.good();value['findings']=[{'severity':['high'],'file':'x','problem':'p','evidence':'e'}]
        with self.assertRaises(s.FlowError):
            v.review_verdict(json.dumps(value))

    def test_deleted_secret_is_screened(self):
        key = 'sk-' + 'a'*32
        t = s.load(ROOT / 'task-template.json'); t['context'] = []
        with self.assertRaises(s.FlowError):
            w.review_packet(t, {'config.py': ('key="' + key + '"').encode()}, {'config.py': b'key="removed"'}, {})

    def test_task_secret_is_screened(self):
        with self.assertRaises(s.FlowError):
            v.screen('TASK says use ' + 'sk-' + 'a'*32)

    def test_quoted_credential_assignment_is_screened(self):
        for quote in ('"', "'"):
            with self.subTest(quote=quote), self.assertRaises(s.FlowError):
                v.screen('password = ' + quote + 'unusual-long-credential' + quote)

    def test_no_silent_auto_model(self):
        s.save(s.home()/'settings.json', dict(v.DEFAULTS, cursor_model='auto'))
        with self.assertRaises(s.FlowError):
            v.settings()

    def test_cursor_explicit_model_and_restricted_flags(self):
        _, cfg = self.fakes()
        d = self.root / 'opinion'
        result = v.worker('cursor', 'Independent check of a synthetic requirement.', d, cfg)
        self.assertIn('FAKE', result)
        args = s.load(d/'process.json')['argv']
        self.assertEqual(args[args.index('--model')+1], 'fake-independent')
        self.assertEqual(args[args.index('--mode')+1], 'ask')
        self.assertEqual(args[args.index('--sandbox')+1], 'enabled')
        self.assertNotIn('--force', args)
        self.assertNotIn('--approve-mcps', args)

    def test_cursor_bad_envelope_is_not_a_completed_opinion(self):
        fake, cfg = self.fakes(); s.save(fake/'mode.json', {'malformed':True})
        with self.assertRaises(s.FlowError):
            v.worker('cursor', 'Synthetic question', self.root/'opinion', cfg)

    def test_codex_missing_final_does_not_parse_tool_logs(self):
        fake, cfg = self.fakes(); s.save(fake/'mode.json', {'missing':True})
        with self.assertRaises(s.FlowError):
            v.worker('codex', 'Synthetic review', self.root/'review', cfg)

    def test_codex_structured_readonly_adapter(self):
        _, cfg = self.fakes()
        verdict = v.worker('codex', 'Synthetic review', self.root/'review', cfg)
        self.assertTrue(verdict['evidence_sufficient'])
        args = s.load(self.root/'review'/'process.json')['argv']
        self.assertEqual(args[args.index('--sandbox')+1], 'read-only')
        self.assertIn('--ignore-user-config', args)
        self.assertIn('--output-schema', args)

class TakeoverTests(Temporary):
    def test_dirty_staged_unstaged_and_untracked_work_is_preserved(self):
        repo = self.repo()
        source = repo/'stats.py'
        source.write_text(source.read_text()+'\n# staged\n')
        pr.git(repo,'add','stats.py')
        source.write_text(source.read_text()+'# unstaged\n')
        (repo/'unfinished.md').write_text('keep this new work')
        before, _, index = pr.inspect(repo)
        d,p = pr.prepare(repo)
        after, _, index_after = pr.inspect(repo)
        self.assertEqual(before['head'], after['head'])
        self.assertEqual(before['git_status'], after['git_status'])
        self.assertEqual(index, index_after)
        self.assertEqual(source.read_bytes(), (Path(p['workspace'])/'stats.py').read_bytes())
        self.assertEqual((d/'recovery'/'original-index.bin').read_bytes(), index)
        self.assertTrue((Path(p['workspace'])/'unfinished.md').exists())

    def test_inherited_hook_does_not_execute(self):
        repo = self.repo(); marker = self.root/'hook-ran'
        hook = repo/'.git'/'hooks'/'post-checkout'
        hook.write_text('#!/bin/sh\ntouch ' + shlex.quote(str(marker)) + '\n')
        hook.chmod(0o700)
        head = pr.git(repo,'rev-parse','HEAD')
        pr.prepare(repo)
        self.assertFalse(marker.exists())
        self.assertEqual(pr.git(repo,'rev-parse','HEAD'), head)

    def test_git_filter_config_is_refused_before_checkout(self):
        repo = self.repo()
        pr.git(repo,'config','filter.fake.clean','cat')
        with self.assertRaises(s.FlowError):
            pr.inspect(repo)

    def test_raw_identity_changes_even_without_git_index_change(self):
        repo = self.repo(); snap,_ = pr.capture(repo)
        (repo/'new_module.py').write_text('important = 4\n')
        after,_ = pr.capture(repo)
        self.assertNotEqual(snap['id'], after['id'])

    def test_ignored_data_is_not_copied_or_claimed_backed_up(self):
        repo = self.repo()
        (repo/'.gitignore').write_text((repo/'.gitignore').read_text()+'data/\n')
        (repo/'data').mkdir(); (repo/'data'/'private.npy').write_bytes(b'not actual research data')
        d,p = pr.prepare(repo)
        self.assertFalse((Path(p['workspace'])/'data').exists())
        self.assertTrue((repo/'data'/'private.npy').exists())
        self.assertIn('NOT backed up', (d/'recovery'/'READ_ME.md').read_text())

    def test_source_symlink_is_refused(self):
        repo = self.repo()
        (repo/'link.py').symlink_to(repo/'stats.py')
        with self.assertRaises(s.FlowError):
            pr.inspect(repo)

    def test_existing_workspace_is_reused_not_overwritten(self):
        repo = self.repo(); d,p = pr.prepare(repo)
        f=Path(p['workspace'])/'stats.py'; f.write_text(f.read_text()+'\n# active change\n')
        d2,p2 = pr.prepare(repo)
        self.assertEqual(d,d2)
        self.assertIn('# active change', f.read_text())

    def test_changed_original_requires_reconciliation(self):
        repo = self.repo(); d,p = pr.prepare(repo)
        (repo/'later.md').write_text('new original work')
        with self.assertRaises(s.FlowError):
            pr.prepare(repo)
        self.assertFalse((Path(p['workspace'])/'later.md').exists())

class TestEvidenceTests(Temporary):
    def counts(self, **kw):
        result = {'tests':1,'failures':0,'errors':0,'skipped':0,'expected_failures':0,'unexpected_successes':0,'test_ids':['test_one']}
        result.update(kw)
        return result
    def test_exit_zero_without_evidence_is_blocked(self):
        self.assertEqual(w.test_gate(None, {'exit_code':0,'reason':None}, 1)[0],'BLOCKED')
    def test_zero_tests_not_passed(self):
        self.assertEqual(w.test_gate(self.counts(tests=0,test_ids=[]), {'exit_code':0,'reason':None}, 1)[0],'BLOCKED')
    def test_all_skipped_not_passed(self):
        self.assertEqual(w.test_gate(self.counts(skipped=1), {'exit_code':0,'reason':None}, 1)[0],'BLOCKED')
    def test_failed_counts_override_zero_exit(self):
        self.assertEqual(w.test_gate(self.counts(failures=1), {'exit_code':0,'reason':None}, 1)[0],'FAIL')
    def test_inconsistent_counts_blocked(self):
        self.assertEqual(w.test_gate(self.counts(tests=2), {'exit_code':0,'reason':None}, 1)[0],'BLOCKED')
    def test_expected_failures_are_not_a_clean_pass(self):
        self.assertEqual(w.test_gate(self.counts(expected_failures=1), {'exit_code':0,'reason':None}, 1)[0],'BLOCKED')
    def test_actual_all_skipped_unittest_is_blocked(self):
        root=s.private_dir(self.root/'source'); (root/'tests').mkdir(); (root/'tests'/'__init__.py').write_text('')
        (root/'tests'/'test_skip.py').write_text('import unittest\nclass T(unittest.TestCase):\n @unittest.skip("not run")\n def test_skip(self): pass\n')
        t=s.load(ROOT/'task-template.json');t['tests']['python']=sys.executable
        snap,raw=pr.capture(root)
        result=w.execute_checks(root,t,s.private_dir(self.root/'run'),snap,raw)
        self.assertEqual(result['state'],'BLOCKED')
        self.assertEqual(result['results']['skipped'],1)
    def test_actual_empty_suite_is_blocked(self):
        root=s.private_dir(self.root/'source');(root/'tests').mkdir();(root/'tests'/'__init__.py').write_text('')
        t=s.load(ROOT/'task-template.json');t['tests']['python']=sys.executable
        snap,raw=pr.capture(root)
        result=w.execute_checks(root,t,s.private_dir(self.root/'run'),snap,raw)
        self.assertEqual(result['state'],'BLOCKED')
    def test_missing_artifact_blocks_execution_gate(self):
        root=self.repo()
        f=root/'stats.py';f.write_text(f.read_text().replace('return [0.0 for _ in values]  # deliberately wrong fixture','return [(x-low)/(high-low) for x in values]'))
        t=s.load(ROOT/'examples'/'tiny-research'/'demo-task.json');t['tests']['python']=sys.executable;t['artifacts']=['outputs/missing.json']
        snap,raw=pr.capture(root)
        result=w.execute_checks(root,t,s.private_dir(self.root/'run'),snap,raw)
        self.assertEqual(result['state'],'BLOCKED')
        self.assertIn('missing', result['reason'])

class WorkflowTests(Temporary):
    def test_full_takeover_failure_repair_review_and_stale_handoff(self):
        fake,cfg=self.fakes()
        repo,d,p,t=self.prepared_task()
        original=(repo/'stats.py').read_bytes()
        first=w.baseline(d,p)
        self.assertEqual(first['state'],'FAIL')
        opinion=w.consult(d,p,'Independent method check')
        self.assertEqual(opinion['state'],'RECEIVED')
        f=Path(p['workspace'])/'stats.py'
        f.write_text(f.read_text().replace('return [0.0 for _ in values]  # deliberately wrong fixture','return [(x-low)/(high-low) for x in values]'))
        final=w.check(d,p)
        self.assertEqual(final['state'],'CHECKED', final['reason'])
        self.assertEqual((repo/'stats.py').read_bytes(),original)
        state,text=w.status(d,p)
        self.assertEqual(state,'CHECKED')
        self.assertIn('5 collected', text)
        self.assertTrue(Path(final['artifacts']['outputs/result.json']['path']).exists())
        self.assertEqual(json.loads(Path(final['artifacts']['outputs/result.json']['path']).read_text())['normalized'],[0,.5,1])
        self.assertNotIn('APPROVED', text)
        # New source invalidates the current report, including untracked source.
        (Path(p['workspace'])/'new.py').write_text('changed=1')
        self.assertEqual(w.status(d,p)[0],'STALE')
        (Path(p['workspace'])/'new.py').unlink()
        # A new severe review replaces the old positive current state.
        s.save(fake/'mode.json', {'high':True})
        newer=w.check(d,p)
        self.assertEqual(newer['state'],'NEEDS_ATTENTION')
        self.assertEqual(w.status(d,p)[0],'NEEDS_ATTENTION')
        self.assertNotEqual(p['latest'],final['directory'])
        # Failed attempts remain inspectable.
        self.assertTrue((Path(first['directory'])/'test-process.json').exists())

    def test_baseline_runs_without_any_proposed_diff(self):
        _,d,p,_=self.prepared_task()
        result=w.baseline(d,p)
        self.assertEqual(result['state'],'FAIL')
        self.assertEqual(result['gates']['results']['tests'],5)

    def test_worker_call_budget_is_enforced(self):
        _,d,p,_=self.prepared_task()
        p['worker_calls']=v.settings()['max_worker_calls']
        with self.assertRaises(s.FlowError):
            w.reserve_call(d,p)

    def test_takeover_cannot_overlap_active_lead_session(self):
        repo,d,p,t=self.prepared_task()
        with s.lock(d/'session.lock'):
            with self.assertRaises(s.FlowError):
                pr.prepare(repo)

    def test_no_approval_or_automatic_promotion_command(self):
        # The old fake-human approval boundary is removed, not relabelled as secure.
        with patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                parser().parse_args(['decide','--approve'])
            with self.assertRaises(SystemExit):
                parser().parse_args(['check-promotion'])

    def test_invalid_scope_and_cwd_contract_is_rejected(self):
        root=self.repo();t=s.load(ROOT/'task-template.json');t['tests']['directory']='../other'
        with self.assertRaises(s.FlowError):
            w.validate_task(t,root)

    def test_foreign_session_cannot_take_operation_lock(self):
        d=s.private_dir(self.root/'p')
        s.save(d/'session.json',{'token':'owner'})
        with s.lock(d/'session.lock'):
            with patch.dict(os.environ, {'RESEARCHFLOW_SESSION':'not-owner'}):
                with self.assertRaises(s.FlowError):
                    with w.operation(d):
                        self.fail('wrong owner')


    def test_source_change_after_capture_invalidates_evidence(self):
        root=self.repo();t=s.load(ROOT/'task-template.json');snap,_=pr.capture(root)
        r={'task_hash':s.identity(t),'snapshot':snap['id'],'controller_id':w.controller_id(),'settings_id':s.identity(v.settings()),'directory':str(self.root)}
        (root/'stats.py').write_text('# changed source')
        self.assertIn('Source', w.freshness(r,t,root,False))

    def test_missing_verified_artifact_invalidates_status(self):
        root=self.repo();t=s.load(ROOT/'task-template.json');snap,_=pr.capture(root)
        r={'task_hash':s.identity(t),'snapshot':snap['id'],'controller_id':w.controller_id(),'settings_id':s.identity(v.settings()),'directory':str(self.root),'artifacts':{'outputs/x':{'path':str(self.root/'missing'), 'sha256':'absent'}}}
        self.assertIn('output', w.freshness(r,t,root,False))

    def test_changed_evidence_invalidates_status(self):
        root=self.repo();t=s.load(ROOT/'task-template.json');snap,_=pr.capture(root)
        (self.root/'test.json').write_text('changed')
        r={'task_hash':s.identity(t),'snapshot':snap['id'],'controller_id':w.controller_id(),'settings_id':s.identity(v.settings()),'directory':str(self.root),'evidence_hashes':{'test.json':s.digest(b'old')}}
        self.assertIn('Evidence', w.freshness(r,t,root,False))

    def test_unapproved_cursor_override_is_blocked_without_call(self):
        self.fakes();_,d,p,t=self.prepared_task()
        result=w.consult(d,p,'Second opinion','not-authorized')
        self.assertEqual(result['state'],'BLOCKED')
        self.assertEqual(p.get('worker_calls',0),0)

    def test_approved_cursor_override_uses_exact_model(self):
        fake,cfg=self.fakes();cfg['cursor_models']=['fake-independent','fake-other'];s.save(s.home()/'settings.json',cfg)
        _,d,p,t=self.prepared_task()
        result=w.consult(d,p,'Second opinion','fake-other')
        self.assertEqual(result['state'],'RECEIVED')
        process=s.load(Path(result['directory'])/'cursor'/'process.json')
        self.assertEqual(process['requested_model'],'fake-other')

class InstallationTests(Temporary):
    def module(self):
        spec=importlib.util.spec_from_file_location('rf_installer_fixture',ROOT/'install.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_checksum_rejects_modified_code(self):
        source=s.private_dir(self.root/'release');(source/'main.py').write_text('print(1)')
        s.save(source/'RELEASE.json',{'format':1,'version':'3.0.0','files':{'main.py':s.digest(b'print(1)')}})
        self.module().verify(source)
        (source/'main.py').write_text('print(2)')
        with self.assertRaises(ValueError):
            self.module().verify(source)

    def test_checksum_rejects_extra_files(self):
        source=s.private_dir(self.root/'release');(source/'main.py').write_text('print(1)')
        s.save(source/'RELEASE.json',{'format':1,'version':'3.0.0','files':{'main.py':s.digest(b'print(1)')}})
        (source/'unexpected.py').write_text('pass')
        with self.assertRaises(ValueError):
            self.module().verify(source)

    def test_finder_metadata_does_not_corrupt_release_inventory(self):
        source=s.private_dir(self.root/'release');(source/'main.py').write_text('print(1)')
        s.save(source/'RELEASE.json',{'format':1,'version':'3.0.0','files':{'main.py':s.digest(b'print(1)')}})
        (source/'.DS_Store').write_bytes(b'Finder metadata')
        (source/'._main.py').write_bytes(b'AppleDouble metadata')
        (source/'__MACOSX').mkdir();(source/'__MACOSX'/'._main.py').write_bytes(b'archive metadata')
        self.module().verify(source)

    def test_installed_source_has_demo_and_runner_fixtures(self):
        for path in ('examples/tiny-research/stats.py','examples/tiny-research/tests/test_stats.py','tests/fake_worker.py','rf/test_runner.py','prompts/lead.md','task-template.json'):
            self.assertTrue((ROOT/path).is_file(),path)

if __name__=='__main__':
    unittest.main()
