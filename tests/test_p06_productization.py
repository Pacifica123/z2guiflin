"""P06: supported staging, migration conflicts, projection freshness and secret boundaries."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,importlib.util,json,os,re,shutil,subprocess,sys,tarfile,zipfile
import pytest
from zap2_gui import __version__
from zap2_gui.distribution import ensure_workspace,manifest_at
ROOT=Path(__file__).resolve().parents[1]

def module(rel):
    spec=importlib.util.spec_from_file_location(Path(rel).stem,ROOT/rel)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

@pytest.fixture(scope='module')
def release(tmp_path_factory):
    tmp=tmp_path_factory.mktemp('p06-release');builder=module('packaging/build_release.py')
    archive,manifest=builder.build(ROOT,tmp/'release.tar.gz')
    source=tmp/'source'
    with tarfile.open(archive) as tar:
        assert all(not m.issym() and not m.islnk() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in tar.getmembers())
        tar.extractall(source)
    source=source/('zap2gui-linux-'+__version__)
    target=module('packaging/install_tree.py').install(source,tmp/'system')
    return SimpleNamespace(tmp=tmp,builder=builder,archive=archive,manifest=manifest,source=source,target=target)

def records(root):return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}

def tiny(tmp,version='old',text='one'):
    root=tmp/version;root.mkdir();(root/'tools').mkdir();(root/'tools/managed').write_text(text);(root/'presets').mkdir();(root/'presets/user.json').write_text('seed-'+version)
    files={p.relative_to(root).as_posix():{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'mode':0o644} for p in root.rglob('*') if p.is_file()}
    manifest={'schemaVersion':1,'version':version,'files':files,'releaseDigest':hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
    (root/'RELEASE_MANIFEST.json').write_text(json.dumps(manifest));return root

def test_source_archive_is_byte_reproducible(release):
    other,_=release.builder.build(ROOT,release.tmp/'second.tar.gz');assert other.read_bytes()==release.archive.read_bytes()
    assert release.manifest['version']==__version__ and len(release.manifest['files'])>100
    manifest_at(release.source)

@pytest.mark.parametrize('path',['.zap2/tunnel/secret.json','.git/config','gui/__pycache__/bad.pyc','core/zapret2/nfq2/nfqws2','profiles/.env.token','node_modules/x','meta_tools/devctl/project/devctl.py','UserTestSpace/output.txt','runtime/p06/container-validation.json'])
def test_release_excludes_runtime_secrets_cache_and_compiled_outputs(path):
    assert not module('packaging/build_release.py').allowed(path)

def test_package_recipe_pins_source_and_helper_ownership(release):
    recipe=release.tmp/'PKGBUILD';release.builder.arch_recipe(release.archive,release.manifest,recipe)
    text=recipe.read_text();assert hashlib.sha256(release.archive.read_bytes()).hexdigest() in text and 'SKIP' not in text
    helper=release.target/'lib/zap2gui/zap2-runtime-executor'
    assert helper.stat().st_mode&0o777==0o755
    assert helper.read_bytes()==(ROOT/'tools/privileged/zap2-runtime-executor').read_bytes()
    assert not (release.target/'lib/systemd/system').exists() and not (release.target/'share/systemd/user').exists()
    assert (release.target/'share/applications/zap2-gui.desktop').exists()
    assert (release.target/'share/licenses/zap2gui-linux/zapret2-LICENSE').exists()

@pytest.mark.parametrize('args',[['--package-preflight'],['--action','default.workflow.status'],['--action','default.workflow.plan.start'],['--list-presets'],['--about'],['--find','runtime']])
def test_installed_cli_outside_checkout_without_pythonpath(release,tmp_path,args):
    before=records(release.target)
    env=os.environ.copy();env.pop('PYTHONPATH',None);env.update(HOME=str(tmp_path/'home'),XDG_DATA_HOME=str(tmp_path/'data'),XDG_CONFIG_HOME=str(tmp_path/'config'),QT_QPA_PLATFORM='offscreen')
    completed=subprocess.run([sys.executable,'-I',str(release.target/'lib/zap2gui/launch.py'),*args],cwd=tmp_path,env=env,text=True,capture_output=True,timeout=60)
    assert completed.returncode==0,completed.stdout+completed.stderr
    assert records(release.target)==before
    if args==['--package-preflight']:assert not (tmp_path/'data').exists()
    else:assert (tmp_path/'data/zap2gui/workspace/.zap2/installation/receipt.json').exists()

def test_installed_gui_code_and_identity_button(release,tmp_path):
    before=records(release.target)
    code=f"import sys;sys.dont_write_bytecode=True;sys.path.insert(0,{str(release.target/'lib/zap2gui/python')!r});from pathlib import Path;from zap2_gui.distribution import prepare_installed;root=prepare_installed(Path({str(release.target/'share/zap2gui')!r}));from PyQt6.QtWidgets import QApplication,QPushButton;from zap2_gui.windows.main_window import create_main_window;app=QApplication([]);w=create_main_window(root);assert w.findChild(QPushButton,'productIdentityButton');w.show();app.processEvents();w.close();print('installed GUI: PASS')"
    env=os.environ.copy();env.pop('PYTHONPATH',None);env.update(HOME=str(tmp_path/'home'),XDG_DATA_HOME=str(tmp_path/'data'),XDG_CONFIG_HOME=str(tmp_path/'config'),QT_QPA_PLATFORM='offscreen')
    result=subprocess.run([sys.executable,'-I','-c',code],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert records(release.target)==before

def test_upgrade_preserves_user_state_and_seeds_and_receipts(tmp_path):
    old=tiny(tmp_path);new=tiny(tmp_path,'new','two');ws=tmp_path/'data/workspace'
    first=ensure_workspace(old,ws);assert ensure_workspace(old,ws)==first
    (ws/'presets/user.json').write_text('user edit')
    (ws/'.zap2/user-state.json').write_text('private state')
    updated=ensure_workspace(new,ws)
    assert (ws/'tools/managed').read_text()=='two'
    assert (ws/'presets/user.json').read_text()=='user edit' and (ws/'.zap2/user-state.json').read_text()=='private state'
    assert updated['previousReleaseDigest']==first['releaseDigest']
    backup=ws.parent/'backups'/('workspace-'+first['releaseDigest'][:16]);assert (backup/'tools/managed').read_text()=='one'

def test_upgrade_conflict_is_non_mutating(tmp_path):
    old=tiny(tmp_path);new=tiny(tmp_path,'new','two');ws=tmp_path/'data/workspace';ensure_workspace(old,ws)
    (ws/'tools/managed').write_text('local edit');before=records(ws)
    with pytest.raises(ValueError,match='conflict'):ensure_workspace(new,ws)
    assert records(ws)==before

@pytest.mark.parametrize('state',['running','stale','migration-required','applied','unknown','failed','conflict'])
def test_upgrade_blocks_unreconciled_owned_runtime(tmp_path,state):
    old=tiny(tmp_path);new=tiny(tmp_path,'new','two');ws=tmp_path/'data/workspace';ensure_workspace(old,ws)
    state_path=ws/'.zap2/runtime/sessions/default.owner-rules.json';state_path.parent.mkdir(parents=True);state_path.write_text(json.dumps({'state':state}))
    before=records(ws)
    with pytest.raises(ValueError,match='reconcile'):ensure_workspace(new,ws)
    assert records(ws)==before

def test_unknown_schema_and_interrupted_rename_fail_closed(tmp_path):
    old=tiny(tmp_path);new=tiny(tmp_path,'new','two');ws=tmp_path/'data/workspace';ensure_workspace(old,ws)
    receipt=ws/'.zap2/installation/receipt.json';data=json.loads(receipt.read_text());data['schemaVersion']=99;receipt.write_text(json.dumps(data));before=records(ws)
    with pytest.raises(ValueError,match='unknown newer'):ensure_workspace(new,ws)
    assert records(ws)==before
    backup=ws.parent/'backups';backup.mkdir();ws.rename(backup/'recovery')
    with pytest.raises(ValueError,match='recovery'):ensure_workspace(new,ws)
    assert not ws.exists() and (backup/'recovery/.zap2/installation/receipt.json').exists()

def test_malicious_receipt_and_symlinks_cannot_redirect_upgrade(tmp_path):
    old=tiny(tmp_path);new=tiny(tmp_path,'new','two');ws=tmp_path/'data/workspace';ensure_workspace(old,ws)
    receipt=ws/'.zap2/installation/receipt.json';data=json.loads(receipt.read_text());data['files']['../../outside']={'sha256':'x'};receipt.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='unsafe historical'):ensure_workspace(old,ws)
    data['files'].pop('../../outside');receipt.write_text(json.dumps(data));(ws/'redirect').symlink_to(tmp_path)
    with pytest.raises(ValueError,match='symlink'):ensure_workspace(new,ws)

def test_manifest_digest_tampering_rejected(tmp_path):
    old=tiny(tmp_path);p=old/'RELEASE_MANIFEST.json';data=json.loads(p.read_text());data['releaseDigest']='wrong';p.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='digest'):manifest_at(old)

def test_uninstall_removes_only_package_owned_files(release,tmp_path):
    installer=module('packaging/install_tree.py');target=installer.install(release.source,tmp_path/'stage')
    unrelated=target/'share/unrelated';unrelated.write_text('keep');user=tmp_path/'user-state';user.write_text('preserve')
    removed=installer.uninstall_staged(target)
    assert removed and unrelated.read_text()=='keep' and user.read_text()=='preserve'
    assert not (target/'bin/zap2-gui').exists()

def test_generated_authorities_and_original_history_are_fresh():
    result=subprocess.run([sys.executable,str(ROOT/'meta_tools/generate_p06_reference.py'),'--check'],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    pre=json.loads((ROOT/'runtime/p06/pre-forensics.json').read_text())
    for path,digest in pre['authorities'].items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
    migration=json.loads((ROOT/'docs/history/migration-index.json').read_text())
    for entry in migration['files'].values():
        assert hashlib.sha256((ROOT/entry['historyPath']).read_bytes()).hexdigest()==entry['sha256'],entry

def test_current_links_resolve():
    paths=[ROOT/'README.md',* (ROOT/'docs').glob('*.md')]
    paths += [p for p in (ROOT/'docs').rglob('*.md') if 'history' not in p.relative_to(ROOT/'docs').parts]
    for path in paths:
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            if '://' in target or target.startswith('#'):continue
            assert (path.parent/target.split('#')[0]).exists(),(path,target)

def test_support_export_allowlist_keeps_typed_failure_without_secrets(tmp_path,monkeypatch):
    import zap2_gui.support_bundle as support
    import zap2_gui.adapters.discord_tunnel as tunnel
    from zap2_gui.models.network_evidence import ProbeSpan,CapabilityVerdict
    secrets=['vless://credential@example.invalid','12345678-secret-uuid','supersecret-token','Authorization: Bearer hidden','passwordXYZ']
    ident={'productVersion':__version__,'upstream':{'name':secrets[0]},'schemas':{'executionPlan':1},'helper':{'state':'ready','sourceSha256':'a'*64,'installedSha256':'b'*64},'externalCore':{'identityHash':secrets[1]},'evidence':{'runId':secrets[2],'configHash':secrets[3]}}
    monkeypatch.setattr(support,'identity_snapshot',lambda root:ident)
    monkeypatch.setattr(tunnel,'_load_running_tunnel_session',lambda *a:{'state':'running'})
    monkeypatch.setattr(tunnel,'_load_bound_evidence_graph',lambda *a:SimpleNamespace(spans=[ProbeSpan(secrets[1],'target_tls',secrets[2],'FAIL','target_tls_timeout',secrets[0],detail={'log':secrets[3],'password':secrets[4]})],verdicts=[CapabilityVerdict('vesktop.bootstrap',secrets[2],'UNKNOWN',(),(),missing_requirements=(secrets[0],),reason=secrets[3])]))
    output=support.write_support_bundle(tmp_path/'support.zip',ROOT)
    with zipfile.ZipFile(output) as z:
        assert z.namelist()==['support.json'];text=z.read('support.json').decode();data=json.loads(text)
    assert not any(secret in text for secret in secrets)
    assert data['observations'][0]['failureClass']=='target_tls_timeout' and data['observations'][0]['result']=='FAIL'
    assert data['capabilities'][0]['support']=='UNKNOWN' and data['capabilities'][0]['missingRequirements']==1
    assert output.stat().st_mode&0o777==0o600
    with pytest.raises(ValueError,match='exists'):support.write_support_bundle(output,ROOT)

def test_about_independent_identity_axes():
    from zap2_gui.product_identity import identity_snapshot
    data=identity_snapshot(ROOT)
    assert data['productVersion']==__version__ and data['upstream']['version']=='1.0.6'
    assert data['schemas']['connectionReceipt']==2 and data['schemas']['workspaceInstallation']==1
    assert set(data['evidence'])=={'runId','connectionReceiptId','configHash'}
    assert data['service'].startswith('plan-only')

def test_one_p06_profile_is_shared_by_devctl_and_shell():
    shell=(ROOT/'meta_tools/hyperpatch_acceptance.sh').read_text();pipeline=(ROOT/'tools/gui_checks/check_p06_acceptance.py').read_text()
    assert '--p06)' in shell and 'exec "${PYTHON_BIN}" tools/gui_checks/check_p06_acceptance.py' in shell
    assert 'check_p06_regression.py' in pipeline and 'zipfile.ZipFile' in pipeline and 'if rc:status=1;break' in pipeline


def test_source_allowlist_does_not_discover_unknown_user_files(tmp_path):
    builder=module('packaging/build_release.py');(tmp_path/'packaging').mkdir();(tmp_path/'profiles').mkdir()
    (tmp_path/'profiles/private.json').write_text('vless://private-user-secret')
    (tmp_path/'packaging/release-files.json').write_text(json.dumps({'schemaVersion':1,'files':['packaging/release-files.json']}))
    assert [p.relative_to(tmp_path).as_posix() for p in builder.source_files(tmp_path)]==['packaging/release-files.json']

def test_acceptance_shells_are_valid_and_vm_mode_requires_explicit_intent():
    for rel in ['meta_tools/hyperpatch_acceptance.sh','meta_tools/p06_vm_acceptance.sh']:
        assert subprocess.run(['bash','-n',str(ROOT/rel)]).returncode==0
    result=subprocess.run(['bash',str(ROOT/'meta_tools/p06_vm_acceptance.sh')],capture_output=True,text=True)
    assert result.returncode==2 and '--allow-system-install' in result.stderr
