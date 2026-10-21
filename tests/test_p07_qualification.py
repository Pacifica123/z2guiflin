"""Qualification falsifiers are executable; fixture PASS is not owner evidence."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import copy,hashlib,importlib.util,json,os,shutil,signal,subprocess,sys,time
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/gui_checks'))
import p07_qualification as q
from p07_process import run_bounded
from zap2_gui.distribution import ensure_workspace

def tiny(tmp,name,version,text):
    root=tmp/name;root.mkdir();(root/'managed').write_text(text)
    files={'managed':{'sha256':hashlib.sha256(text.encode()).hexdigest(),'mode':0o644}}
    manifest={'schemaVersion':1,'version':version,'files':files,'releaseDigest':hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
    (root/'RELEASE_MANIFEST.json').write_text(json.dumps(manifest));return root

def content(root):return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}

@pytest.mark.parametrize('state',['running','started','stale','unknown','applied'])
def test_same_release_installed_bootstrap_allows_owned_inspect_stop(tmp_path,state):
    package=tiny(tmp_path,'package','1.0.0rc7','same');ws=tmp_path/'data/workspace';receipt=ensure_workspace(package,ws)
    path=ws/'.zap2/runtime/sessions/default.session.json';path.parent.mkdir(parents=True);path.write_text(json.dumps({'state':state,'pid':12345}))
    before=content(ws)
    assert ensure_workspace(package,ws)==receipt
    assert content(ws)==before # no PID/ownership assertion or mutation is made by bootstrap

def test_real_upgrade_still_requires_stop_and_downgrade_is_non_destructive(tmp_path):
    old=tiny(tmp_path,'old','0.10.0rc6','before');new=tiny(tmp_path,'new','1.0.0rc7','after');ws=tmp_path/'data/workspace'
    # Живой PID (сам тест) — runtime действительно работает, обновление ждёт остановки.
    ensure_workspace(old,ws);path=ws/'.zap2/runtime/sessions/default.session.json';path.parent.mkdir(parents=True);path.write_text(json.dumps({'state':'running','pid':os.getpid()}));before=content(ws)
    with pytest.raises(ValueError,match='reconcile'):ensure_workspace(new,ws)
    assert content(ws)==before
    path.write_text(json.dumps({'state':'stopped'}));ensure_workspace(new,ws);before=content(ws)
    with pytest.raises(ValueError,match='downgrade'):ensure_workspace(old,ws)
    assert content(ws)==before

def test_unknown_product_version_needs_explicit_migration(tmp_path):
    old=tiny(tmp_path,'old','future-version','before');new=tiny(tmp_path,'new','1.0.0rc7','after');ws=tmp_path/'data/workspace';ensure_workspace(old,ws);before=content(ws)
    with pytest.raises(ValueError,match='unknown workspace version'):ensure_workspace(new,ws)
    assert content(ws)==before

def test_failed_publish_restores_old_workspace_and_foreign_file(tmp_path,monkeypatch):
    old=tiny(tmp_path,'old','0.10.0rc6','before');new=tiny(tmp_path,'new','1.0.0rc7','after');ws=tmp_path/'data/workspace';ensure_workspace(old,ws)
    foreign=tmp_path/'foreign-file';foreign.write_text('never delete');before=content(ws)
    import zap2_gui.distribution as d
    replace=d.os.replace
    def crash(source,destination):
        if Path(source).name.startswith('.workspace-stage-'):raise OSError('injected publication cutpoint')
        return replace(source,destination)
    monkeypatch.setattr(d.os,'replace',crash)
    with pytest.raises(OSError,match='cutpoint'):ensure_workspace(new,ws)
    assert content(ws)==before and foreign.read_text()=='never delete'

def test_supported_p06_predecessor_preserves_normalized_plan_and_confirmation(tmp_path):
    # Real shipping resources; package generation metadata changes, semantics do not.
    spec=importlib.util.spec_from_file_location('release_builder',ROOT/'packaging/build_release.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    import tarfile
    archive,manifest=builder.build(ROOT,tmp_path/'candidate.tar.gz')
    extracted=tmp_path/'source'
    with tarfile.open(archive) as tar:tar.extractall(extracted)
    source=next(extracted.iterdir());old=tmp_path/'old';shutil.copytree(source,old)
    old_manifest=json.loads((old/'RELEASE_MANIFEST.json').read_text());old_manifest['version']='0.10.0rc6'
    # Distinct resource release; source bytes and manifest are coherent.
    note=old/'docs/PROJECT_STATUS.md';note.write_text(note.read_text()+'\nPredecessor migration fixture.\n');old_manifest['files']['docs/PROJECT_STATUS.md']['sha256']=hashlib.sha256(note.read_bytes()).hexdigest();old_manifest['releaseDigest']=hashlib.sha256(json.dumps(old_manifest['files'],sort_keys=True,separators=(',',':')).encode()).hexdigest();(old/'RELEASE_MANIFEST.json').write_text(json.dumps(old_manifest))
    ws=tmp_path/'data/workspace';first=ensure_workspace(old,ws)
    from zap2_gui.adapters.execution_plan import materialize_execution_plan
    from zap2_gui.adapters.runtime_state import prepare_runtime_plan,confirm_runtime_plan
    before=materialize_execution_plan(ws,'default').plan.to_payload()
    prepared=prepare_runtime_plan(ws,'status','default');confirm_runtime_plan(ws,prepared.plan_id)
    plan_bytes=prepared.plan_path.read_bytes()
    updated=ensure_workspace(source,ws)
    assert materialize_execution_plan(ws,'default').plan.to_payload()==before
    assert prepared.plan_path.read_bytes()==plan_bytes
    assert updated['previousReleaseDigest']==first['releaseDigest'] and (ws.parent/'backups'/('workspace-'+first['releaseDigest'][:16])).exists()

def test_all_gates_journeys_falsifiers_and_baseline_bindings_are_frozen():
    contract=q.validate_contract(ROOT);frozen=q.verify_freeze(ROOT)
    assert len(contract['gates'])==21 and len(contract['journeys'])==7
    assert all(g['falsifier'] for g in contract['gates'])
    assert len(frozen['files'])>800 and frozen['binding']['candidateVersion']=='1.3.0'
    assert {'SA-P07-01','SA-P07-02'}<=set(json.loads((ROOT/'runtime/p07/pre-forensics.json').read_text())['amendments'])

def outcomes(contract):
    return {p:[{'case':'fixture-only','result':'PASS','xml':'synthetic-unit'}] for item in contract['gates']+contract['journeys'] for p in item['probes']}

def test_deterministic_green_does_not_promote_missing_os_live_package_review():
    contract=q.load_contract(ROOT);report=q.evaluate(q.candidate_binding(ROOT),contract,outcomes(contract))
    assert not report['promotionAllowed'] and report['result']=='BLOCKED'
    assert next(x for x in report['gateMatrix'] if x['id']=='G02')['result']=='NOT_RUN'
    assert next(x for x in report['gateMatrix'] if x['id']=='G01')['result']=='PASS'
    assert 'G21' in report['blockingClaims'] and 'J1' in report['blockingClaims']

def test_failure_evidence_cannot_be_overwritten_by_another_pass():
    contract=q.load_contract(ROOT);binding=q.candidate_binding(ROOT)
    fail={'claimId':'G02','partition':'liveNetwork','result':'FAIL','artifacts':[]};passed={**fail,'result':'PASS'}
    report=q.evaluate(binding,contract,outcomes(contract),[fail,passed])
    assert next(x for x in report['gateMatrix'] if x['id']=='G02')['result']=='FAIL' and not report['promotionAllowed']

def test_positive_evaluator_fixture_requires_every_claim_partition_and_clean_floor():
    contract=q.load_contract(ROOT);binding=q.candidate_binding(ROOT)
    records=[{'claimId':item['id'],'partition':p,'result':'PASS','artifacts':[{'sha256':'fixture'}]} for item in contract['gates']+contract['journeys'] for p in item['requiredPartitions'] if p!='deterministic']
    report=q.evaluate(binding,contract,outcomes(contract),records)
    assert report['promotionAllowed'] # evaluator unit fixture, not acceptance receipt
    assert not q.evaluate(binding,contract,outcomes(contract),records,floor='FAIL')['promotionAllowed']
    assert not q.evaluate(binding,contract,outcomes(contract),records,issues=[{'error':'stale record'}])['promotionAllowed']

def owner_record(tmp_path,claim='G02',partition='liveNetwork'):
    binding=q.candidate_binding(ROOT);now=datetime.now(timezone.utc);artifact=tmp_path/'evidence.txt';artifact.write_text('synthetic owner-validator unit fixture')
    record={'claimId':claim,'partition':partition,'result':'PASS','binding':binding,'createdAt':(now-timedelta(minutes=1)).isoformat(),'expiresAt':(now+timedelta(days=1)).isoformat(),'producer':'fixture-producer','reviewer':'fixture-independent-reviewer','method':'unit fixture, not real network','environment':{'platform':'fixture'},'scope':{'core':'Xray','coreVersion':'fixture','transport':'tcp','security':'tls','runId':'fixture-run','configHash':'fixture-hash','connectionReceiptId':'fixture-receipt','appVersion':'fixture-app'},'limits':['unit fixture only'],'predicates':{k:'PASS' for k in ['sourceReceipt','semanticFidelity','coreValidate','targetTls','targetHttp','updatesHttp','discordHttp','gatewayWebsocket','electronNavigation']},'artifacts':[{'path':'evidence.txt','sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()}]}
    return record

def validate_record(tmp,record):
    path=tmp/'bundle.json';path.write_text(json.dumps({'schemaVersion':1,'records':[record]}))
    return q.validated_owner_records(path,q.candidate_binding(ROOT),q.load_contract(ROOT))

@pytest.mark.parametrize('mutation',['staleBinding','expired','future','missingArtifact','changedArtifact','traversal','missingTls','wrongLane','missingMethod','selfReview','missingAggregate'])
def test_external_receipt_rejects_stale_unbound_incomplete_or_self_review(tmp_path,mutation):
    record=owner_record(tmp_path)
    if mutation=='staleBinding':record['binding']['candidateDigest']='old'
    elif mutation=='expired':record['expiresAt']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    elif mutation=='future':record['createdAt']=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    elif mutation=='missingArtifact':record['artifacts']=[]
    elif mutation=='changedArtifact':(tmp_path/'evidence.txt').write_text('changed')
    elif mutation=='traversal':record['artifacts'][0]['path']='../outside'
    elif mutation=='missingTls':record['predicates']['targetTls']='UNKNOWN'
    elif mutation=='wrongLane':record['scope']['security']='none'
    elif mutation=='missingMethod':record.pop('method')
    elif mutation=='selfReview':record.update(claimId='G21',partition='review',reviewer=record['producer'])
    elif mutation=='missingAggregate':record.update(claimId='G03',partition='targetApp');record['predicates']['gatewayWebsocket']='NOT_RUN'
    records,issues=validate_record(tmp_path,record)
    assert not records and issues

def test_bounded_vless_failure_closes_journey_but_not_supported_lane(tmp_path):
    record=owner_record(tmp_path,'J4');record.update(branch='bounded-failure',nextExperiment='collect correlated target TLS evidence');record['predicates']['targetTls']='FAIL'
    records,issues=validate_record(tmp_path,record);assert records and not issues
    contract=q.load_contract(ROOT);report=q.evaluate(q.candidate_binding(ROOT),contract,outcomes(contract),records)
    assert next(x for x in report['journeyMatrix'] if x['id']=='J4')['result']=='PASS'
    assert next(x for x in report['gateMatrix'] if x['id']=='G02')['result']=='NOT_RUN'

def test_junit_failure_and_skip_are_not_pass(tmp_path):
    xml=tmp_path/'result.xml';xml.write_text('<testsuite><testcase classname="tests.test_one" name="good"/><testcase classname="tests.test_one" name="bad"><failure/></testcase><testcase classname="tests.test_two" name="skip"><skipped/></testcase></testsuite>')
    data=q.junit_outcomes([xml]);assert q.file_verdict(data,['tests/test_one.py'])=='FAIL';assert q.file_verdict(data,['tests/test_two.py'])=='NOT_RUN';assert q.file_verdict(data,['tests/absent.py'])=='NOT_RUN'

def test_test_worker_timeout_terminates_owned_child_group(tmp_path):
    # Child retains stdout after parent exits; bounded runner must still fail and kill it.
    marker=tmp_path/'child-survived'
    child='import time;from pathlib import Path;time.sleep(1.5);Path('+repr(str(marker))+').write_text("bad")'
    parent='import subprocess,sys;subprocess.Popen([sys.executable,"-c",'+repr(child)+']);print("parent exited",flush=True)'
    began=time.monotonic();result=run_bounded([sys.executable,'-c',parent],timeout=.15)
    assert result.returncode==124 and result.timed_out and time.monotonic()-began<7
    time.sleep(1.6);assert not marker.exists()

def test_deliberate_failure_support_contains_plan_run_and_typed_logs_without_secrets(tmp_path,monkeypatch):
    import zap2_gui.support_bundle as s
    import zap2_gui.adapters.runtime_kernel as kernel
    from zap2_gui.product_identity import identity_snapshot
    identity=identity_snapshot(ROOT);monkeypatch.setattr(s,'identity_snapshot',lambda root:identity);monkeypatch.setattr(kernel,'runtime_kernel_status',lambda root:SimpleNamespace(ownership_state='owned-partial'))
    secrets=['vless://raw-private.example','password-secret','UUID-secret','Bearer-secret']
    base=tmp_path/'.zap2/runtime';(base/'plans').mkdir(parents=True);(base/'sessions').mkdir();(base/'logs').mkdir()
    (base/'plans/p.json').write_text(json.dumps({'planId':secrets[0],'planHash':secrets[1],'action':'start','confirmed':True,'argv':secrets}))
    (base/'sessions/run.json').write_text(json.dumps({'runId':secrets[2],'state':'failed','action':'start','message':secrets[3]}))
    (base/'logs/run.jsonl').write_text(json.dumps({'eventId':secrets[3],'eventType':'session-started','level':'error','message':secrets})+'\n')
    # Minimal resource discovery explicit root is sufficient for this projection.
    data=s.support_snapshot(tmp_path);text=json.dumps(data)
    assert not any(secret in text for secret in secrets)
    assert data['lifecycle']['plans'][0]['confirmed'] and data['lifecycle']['runs'][0]['state']=='failed'
    assert data['lifecycle']['logEvents'][0]['level']=='error' and data['runtimeOwnershipState']=='owned-partial'
    assert 'confirmed owned cleanup' in data['lifecycle']['nextActionByOwnership']['owned-partial']

def test_single_shell_profile_checks_candidate_and_never_assigns_final():
    shell=(ROOT/'meta_tools/hyperpatch_acceptance.sh').read_text();runner=(ROOT/'tools/gui_checks/check_p07_acceptance.py').read_text()
    assert '--p07)' in shell and 'exec "${PYTHON_BIN}" tools/gui_checks/check_p07_acceptance.py' in shell
    assert 'ZAP2_P07_OWNER_BUNDLE' in runner and 'if rc:floor=' in runner and 'zipfile.ZipFile' in runner
    assert subprocess.run(['bash','-n',str(ROOT/'meta_tools/hyperpatch_acceptance.sh')]).returncode==0

def test_installed_cli_remains_available_on_same_release_with_active_session(tmp_path):
    spec=importlib.util.spec_from_file_location('builder',ROOT/'packaging/build_release.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    import tarfile
    archive,manifest=builder.build(ROOT,tmp_path/'release.tar.gz');source=tmp_path/'source'
    with tarfile.open(archive) as tar:tar.extractall(source)
    spec=importlib.util.spec_from_file_location('installer',ROOT/'packaging/install_tree.py');installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
    target=installer.install(next(source.iterdir()),tmp_path/'system')
    env=os.environ.copy();env.pop('PYTHONPATH',None);env.update(HOME=str(tmp_path/'home'),XDG_DATA_HOME=str(tmp_path/'data'),XDG_CONFIG_HOME=str(tmp_path/'config'),QT_QPA_PLATFORM='offscreen')
    launch=[sys.executable,'-I',str(target/'lib/zap2gui/launch.py'),'--action','default.workflow.status']
    assert subprocess.run(launch,cwd=tmp_path,env=env,capture_output=True,text=True).returncode==0
    ws=tmp_path/'data/zap2gui/workspace';marker=ws/'.zap2/runtime/sessions/other.session.json';marker.parent.mkdir(parents=True,exist_ok=True);marker.write_text(json.dumps({'state':'running','pid':12345}))
    result=subprocess.run(launch,cwd=tmp_path,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(marker.read_text())['state']=='running'

def test_interrupted_worker_terminates_nested_owned_groups(tmp_path):
    marker=tmp_path/'escaped';ready=tmp_path/'ready'
    child='import time;from pathlib import Path;Path('+repr(str(ready))+').write_text("ready");time.sleep(1.5);Path('+repr(str(marker))+').write_text("bad")'
    parent='import sys;sys.path.insert(0,'+repr(str(ROOT/'tools/gui_checks'))+');from p07_process import run_bounded,install_signal_cleanup;install_signal_cleanup();run_bounded([sys.executable,"-c",'+repr(child)+'],timeout=10)'
    process=subprocess.Popen([sys.executable,'-I','-c',parent],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:
        deadline=time.monotonic()+5
        while not ready.exists() and time.monotonic()<deadline:time.sleep(.02)
        assert ready.exists()
        process.send_signal(signal.SIGTERM);process.communicate(timeout=7)
        assert process.returncode!=0
        time.sleep(1.6);assert not marker.exists()
    finally:
        if process.poll() is None:process.kill();process.wait()

def test_malformed_support_log_fields_are_projected_as_unknown(tmp_path):
    from zap2_gui.support_bundle import lifecycle_projection
    base=tmp_path/'.zap2/runtime';(base/'plans').mkdir(parents=True);(base/'logs').mkdir()
    (base/'plans/p.json').write_text(json.dumps({'action':['secret'],'state':{'token':'secret'},'argv':['secret']}))
    (base/'logs/x.jsonl').write_text(json.dumps({'eventType':['secret'],'level':{'password':'secret'}})+'\n')
    data=lifecycle_projection(tmp_path)
    assert data['plans'][0]['action']=='unknown' and data['logEvents'][0]['eventType']=='OTHER'
    assert 'secret' not in json.dumps(data)

def test_signal_cleanup_is_reentrant_during_group_registration():
    # Inject a signal at the owned process registry cutpoint in a disposable child.
    code='import sys,os,signal;sys.path.insert(0,'+repr(str(ROOT/'tools/gui_checks'))+');from p07_process import _LOCK,install_signal_cleanup;install_signal_cleanup();\nwith _LOCK:os.kill(os.getpid(),signal.SIGTERM)'
    result=run_bounded([sys.executable,'-I','-c',code],timeout=2)
    assert result.returncode==143 and not result.timed_out

def test_g21_review_needs_real_commit_identity(tmp_path):
    record=owner_record(tmp_path,'G21','review');records,issues=validate_record(tmp_path,record)
    assert not records and 'candidate commit' in issues[0]['error']
    record['scope']['candidateCommit']='a'*40;records,issues=validate_record(tmp_path,record)
    assert records and not issues # validation fixture only; does not claim an actual review

@pytest.mark.parametrize('floor,error,promotion,release,expected',[
    ('PASS',False,False,False,True),
    ('PASS',False,False,True,False),
    ('PASS',False,True,True,True),
    ('FAIL',False,True,False,False),
    ('FAIL',False,True,True,False),
    ('PASS',True,False,False,False),
    ('PASS',True,True,True,False),
])
def test_rc_application_and_final_release_acceptance(floor,error,promotion,release,expected):
    from check_p07_acceptance import acceptance_passed
    report={'promotionAllowed':promotion,'result':'PASS' if promotion else 'BLOCKED'}
    if error:report['error']='source changed during qualification'
    assert acceptance_passed(floor,report,release=release) is expected
    assert report['promotionAllowed'] is promotion


def test_shell_release_mode_uses_same_pipeline():
    shell=(ROOT/'meta_tools/hyperpatch_acceptance.sh').read_text()
    assert '--p07-release)' in shell
    assert 'exec "${PYTHON_BIN}" tools/gui_checks/check_p07_acceptance.py --release' in shell

@pytest.mark.parametrize('release,stage_failure,expected',[(False,False,0),(True,False,1),(False,True,1),(True,True,1)])
def test_acceptance_archives_blocked_release_without_rolling_back_green_rc(tmp_path,monkeypatch,release,stage_failure,expected):
    import check_p07_acceptance as runner
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    monkeypatch.setattr(runner,'install_signal_cleanup',lambda:None)
    monkeypatch.setattr(runner,'run_bounded',lambda *a,**k:SimpleNamespace(output='fixture stage\n',returncode=1 if stage_failure else 0))
    # Exercise the real evaluator and missing-owner behavior; external stages are fixtures.
    monkeypatch.setattr(runner,'validate_contract',lambda:None)
    monkeypatch.setattr(runner,'verify_freeze',lambda:None)
    monkeypatch.delenv('ZAP2_P07_OWNER_BUNDLE',raising=False)
    assert runner.main(['--release'] if release else [])==expected
    logdir=next(p for p in (tmp_path/'.zap2/runtime/acceptance').iterdir() if p.is_dir())
    summary=json.loads((logdir/'summary.json').read_text())
    report=json.loads((logdir/'qualification.json').read_text())
    assert summary['applicationAllowed'] is (not stage_failure)
    assert summary['promotionAllowed'] is False
    assert summary['qualificationResult']=='BLOCKED'
    assert len(report['gateMatrix'])==21 and len(report['journeyMatrix'])==7
    assert logdir.with_suffix('.zip').is_file()
    assert len(summary['steps'])==(1 if stage_failure else 7)
