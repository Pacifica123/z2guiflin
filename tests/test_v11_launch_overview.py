"""v1.1 regressions: actual unchecked VLESS registry row and missing build receipt."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,os,shutil,subprocess
import pytest
from zap2_gui.adapters.launch_error_classifier import classify_launch_issue
from zap2_gui.adapters import launch_composer as composer
from zap2_gui.adapters.core_provenance import write_core_build_receipt
from zap2_gui.adapters.gui_first_overview import gui_first_runtime_overview
ROOT=Path(__file__).resolve().parents[1]
CAPTURED='''Launch composer start
selected: zapret-default
GUI privileged workflow start: FAILED
return code: 2
stderr:
core generation gate: whole-generation build receipt отсутствует; clean build обязателен до runtime start
Final status
Launch composer status
selected: zapret-default
[x] zapret-default :: Zapret default :: supported :: sudo :: state=stopped :: ready=ready
[ ] tunnel-vless :: VLESS tunnel :: supported :: no-sudo :: state=stopped :: ready=needs VLESS profile
'''

@pytest.fixture
def project(tmp_path):
    root=tmp_path/'project'
    shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('.git','.zap2','__pycache__','.pytest_cache'))
    binary=root/'core/zapret2/nfq2/nfqws2';binary.write_text('#!/bin/sh\nexit 0\n');binary.chmod(0o755)
    return root

def test_actual_owner_output_exposes_build_failure_not_unselected_vless():
    issue=classify_launch_issue(action='Combined toggle start',text=CAPTURED,selected_components=('zapret-default',),all_selected_running=False)
    assert issue.code=='Z2-ZAPRET-BUILD-PROVENANCE'
    assert issue.envelope.next_action=='default.build.plan'
    assert 'needs VLESS profile' in issue.details # complete diagnostic context preserved

@pytest.mark.parametrize('status',['needs VLESS profile','needs core binary path','core binary missing'])
def test_unselected_vless_rows_never_classify_as_failure(status):
    text=f'Final status\n[x] zapret-default :: state=running :: ready=ready\n[ ] tunnel-vless :: state=stopped :: ready={status}'
    assert classify_launch_issue(action='Combined toggle start',text=text,selected_components=('zapret-default',),all_selected_running=True) is None
    assert classify_launch_issue(action='Combined toggle start',text=text,all_selected_running=True) is None

@pytest.mark.parametrize('selected,expected',[(('zapret-default',),None),(('tunnel-vless',),'Z2-TUNNEL-PROFILE-MISSING')])
def test_explicit_selection_controls_profile_failure(selected,expected):
    issue=classify_launch_issue(action='Launch composer start',text='needs VLESS profile',selected_components=selected)
    assert (issue.code if issue else None)==expected

def test_binary_without_receipt_blocks_before_confirm_or_sudo(project,monkeypatch):
    before={p.relative_to(project):p.read_bytes() for p in project.rglob('*') if p.is_file()}
    calls=[]
    monkeypatch.setattr(composer,'gui_confirm_plan',lambda **k:calls.append('confirm'))
    monkeypatch.setattr(composer,'gui_privileged_default_start',lambda **k:calls.append('sudo'))
    result=composer.launch_composer_start_to_text(root=project,components='zapret-default')
    assert 'needs verified core build' in result and 'No components were started' in result
    assert not calls
    assert not (project/'.zap2/runtime/confirmations').exists() or not list((project/'.zap2/runtime/confirmations').glob('*'))
    assert composer._zapret_ready(project,'default').startswith('needs verified core build')
    overview=gui_first_runtime_overview(project)
    assert overview.primary_action=='build' and 'Собрать ядро' in overview.next_gui_action
    assert any('receipt' in s for s in overview.issues)
    assert all((project/rel).read_bytes()==data for rel,data in before.items())

def test_verified_generation_is_ready_and_changed_binary_blocks(project):
    binary=project/'core/zapret2/nfq2/nfqws2'
    write_core_build_receipt(project,[binary],'nfqws2') # explicit synthetic build fixture
    assert composer._zapret_ready(project,'default')=='ready'
    assert gui_first_runtime_overview(project).primary_action=='start'
    binary.write_text('#!/bin/sh\nexit 1\n')
    assert composer._zapret_ready(project,'default').startswith('needs verified core build')

@pytest.fixture
def qt_app(tmp_path,monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path/'config'))
    QtWidgets=pytest.importorskip('PyQt6.QtWidgets',reason='PyQt6 не установлен: GUI-тест пропущен (pacman -S python-pyqt6)')
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app

def test_overview_checkbox_and_blocker_states(qt_app,project):
    from PyQt6 import QtWidgets
    from zap2_gui.widgets.runtime_controls import make_runtime_control_page
    page=make_runtime_control_page(project);page.resize(960,840);page.show();qt_app.processEvents()
    find=lambda cls,name:page.findChild(cls,name)
    zapret=find(QtWidgets.QCheckBox,'launchComponentZapretDefault');vless=find(QtWidgets.QCheckBox,'launchComponentTunnelVless')
    primary=find(QtWidgets.QPushButton,'primaryRunButton');core=find(QtWidgets.QLineEdit,'launchComposerCoreBinary')
    assert zapret.isChecked() and not vless.isChecked()
    assert not primary.isEnabled() and primary.text()=='Запустить'
    assert find(QtWidgets.QPushButton,'overviewBuildButton').isVisible()
    assert find(QtWidgets.QLabel,'vlessReadiness').text()=='Не выбран'
    assert not core.isVisible()
    vless.setChecked(True);qt_app.processEvents()
    assert core.isVisible() and 'VLESS' in find(QtWidgets.QLabel,'vlessReadiness').text()
    vless.setChecked(False);zapret.setChecked(False);qt_app.processEvents()
    assert not primary.isEnabled() and not find(QtWidgets.QPushButton,'composerStartButton').isEnabled()
    assert find(QtWidgets.QLabel,'runtimeStatusIndicator').text()=='○ Нет выбора'
    page.close()

@pytest.mark.parametrize('confirm',[False,True])
def test_visible_build_requires_explicit_confirmation(qt_app,project,monkeypatch,confirm):
    from PyQt6 import QtWidgets
    from zap2_gui.widgets import runtime_controls as controls
    calls=[];standard=QtWidgets.QMessageBox.StandardButton
    class Question:
        StandardButton=standard
        def __init__(self,*a):pass
        def setWindowTitle(self,*a):pass
        def setText(self,*a):pass
        def setInformativeText(self,*a):pass
        def setDetailedText(self,text):assert 'plan fixture' in text
        def setStandardButtons(self,*a):pass
        def setDefaultButton(self,value):assert value==standard.No
        def exec(self):return standard.Yes if confirm else standard.No
    monkeypatch.setattr(QtWidgets,'QMessageBox',Question)
    monkeypatch.setattr(controls,'gui_default_build_deps',lambda **k:'deps fixture')
    monkeypatch.setattr(controls,'gui_prepare_default_build',lambda **k:'plan fixture')
    monkeypatch.setattr(controls,'gui_confirm_default_build',lambda **k:calls.append('confirm') or 'confirmed fixture')
    monkeypatch.setattr(controls,'gui_execute_default_build',lambda **k:calls.append('build') or 'build fixture')
    page=controls.make_runtime_control_page(project)
    page.findChild(QtWidgets.QPushButton,'overviewBuildButton').click()
    assert calls==(['confirm','build'] if confirm else [])
    page.close()

def test_local_package_workflow_creates_archive_and_matching_recipe(tmp_path):
    out=tmp_path/'package inputs'
    result=subprocess.run(['bash',str(ROOT/'meta_tools/build_local_package.sh'),'--out',str(out)],cwd=tmp_path,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    archive=out/'zap2gui-linux-1.3.0.tar.gz';recipe=(out/'PKGBUILD').read_text()
    assert hashlib.sha256(archive.read_bytes()).hexdigest() in recipe
    assert "pkgver=1.3.0" in recipe
    assert 'makepkg -si' in result.stdout

def test_p07_source_freeze_remains_historical():
    old=json.loads((ROOT/'runtime/p07/candidate-freeze.json').read_text())
    assert old['binding']['candidateVersion']=='1.0.0rc7'
    assert json.loads((ROOT/'docs/developer/p07-contract.json').read_text())['candidateVersion']=='1.0.0rc7'
