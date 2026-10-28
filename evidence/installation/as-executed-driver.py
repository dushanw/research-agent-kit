from pathlib import Path
import subprocess, os, json, time, shutil, hashlib, fcntl, sys, platform
PACKAGE=Path('/mnt/data/rf-final-candidate/ResearchFlow')
ROOT=Path('/mnt/data/rf-install-validation-final')
ROOT.mkdir(exist_ok=False)
HOME=ROOT/'home'; HOME.mkdir()
EVIDENCE=ROOT/'evidence';EVIDENCE.mkdir()
RECORDS=HOME/'ResearchFlow';RECORDS.mkdir()
INSTALL=HOME/'.local/share/researchflow'; BIN=HOME/'.local/bin'
env=dict(os.environ, HOME=str(HOME), RESEARCHFLOW_HOME=str(RECORDS))
for key in list(env):
    if key.startswith('GIT_') or key.startswith('RESEARCHFLOW_') and key not in {'RESEARCHFLOW_HOME'} or key in {'PYTHONPATH','PYTHONHOME','CLAUDECODE'}:env.pop(key,None)
steps=[]; began=time.time()
def command(name,argv,ok=True,cwd=PACKAGE,timeout=240):
    start=time.time()
    p=subprocess.run([str(x) for x in argv],cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
    (EVIDENCE/(name+'.log')).write_text(p.stdout)
    steps.append({'name':name,'command':list(map(str,argv)),'exit_code':p.returncode,'seconds':round(time.time()-start,2),'expected_success':ok})
    print(name,p.returncode,flush=True)
    assert (p.returncode==0)==ok,(name,p.returncode,p.stdout[-2000:])
    return p.stdout
def record():
    (EVIDENCE/'results.json').write_text(json.dumps({'python':sys.version,'platform':platform.platform(),'steps':steps,'seconds':round(time.time()-began,2),'complete':len(steps)>=12,'live_models_tested':False},indent=2))
try:
    command('00-build-manifest',[sys.executable,PACKAGE/'tools/build_release.py'])
    command('01-fresh-install',[sys.executable,PACKAGE/'install.py','--install-root',INSTALL,'--bin-dir',BIN])
    launch=BIN/'researchflow';assert command('02-installed-version',[launch,'--version']).strip()=='3.0.0'
    original=json.loads((INSTALL/'active.json').read_text())
    # Owner data that must not be touched by install/develop/update/rollback.
    sys.path.insert(0,str(PACKAGE));from rf.providers import DEFAULTS
    settings=dict(DEFAULTS,cursor_model='owner-selected',cursor_models=['owner-selected'])
    (RECORDS/'settings.json').write_text(json.dumps(settings,indent=2))
    settings_bytes=(RECORDS/'settings.json').read_bytes()
    note=RECORDS/'projects'/'owner-preserved'/'note.txt';note.parent.mkdir(parents=True);note.write_text('Do not lose this existing research note.\n')
    command('03-repeat-install',[sys.executable,PACKAGE/'install.py','--install-root',INSTALL,'--bin-dir',BIN])
    assert json.loads((INSTALL/'active.json').read_text())==original
    command('04-installed-offline-demo',[launch,'demo'])
    assert (RECORDS/'settings.json').read_bytes()==settings_bytes
    command('05-feedback',[launch,'feedback','Make result location clearer; synthetic installer test only.'])
    development=ROOT/'development-copy'
    command('06-develop-copy',[launch,'develop',development])
    assert (development/'REQUESTED_CHANGES.md').is_file()
    version=development/'rf/__init__.py';version.write_text(version.read_text().replace('3.0.0','3.0.1'))
    with (development/'CHANGELOG.md').open('a') as f:f.write('\nSynthetic update fixture; no production behavior change.\n')
    command('07-build-update',[sys.executable,development/'tools/build_release.py'],cwd=development)
    command('08-update-through-launcher',[launch,'update',development])
    assert command('09-updated-version',[launch,'--version']).strip()=='3.0.1'
    updated=json.loads((INSTALL/'active.json').read_text());assert updated['previous']==original['release']
    with (INSTALL/'install.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
        command('10-active-session-blocks-rollback',[launch,'rollback'],ok=False)
        assert json.loads((INSTALL/'active.json').read_text())==updated
    version.write_text(version.read_text()+'\n# changed after inventory\n')
    command('11-tampered-update-blocked',[launch,'update',development],ok=False)
    assert json.loads((INSTALL/'active.json').read_text())==updated
    command('12-rollback-through-launcher',[launch,'rollback'])
    assert command('13-restored-version',[launch,'--version']).strip()=='3.0.0'
    assert (RECORDS/'settings.json').read_bytes()==settings_bytes
    assert note.read_text()=='Do not lose this existing research note.\n'
    assert (RECORDS/'feedback.md').is_file()
    assert Path(original['release']).is_dir() and Path(updated['release']).is_dir()
    steps.append({'name':'14-preservation-assertions','all_passed':True,'settings_unchanged':True,'project_note_unchanged':True,'feedback_preserved':True,'both_releases_retained':True})
    record()
except BaseException as exc:
    steps.append({'error':repr(exc)});record();raise
