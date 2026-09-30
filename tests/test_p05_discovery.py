from pathlib import Path
from types import SimpleNamespace
import pytest
from zap2_gui.models.discovery import build_index, search, direct_invoke_allowed, contextual_help
from zap2_gui.models.action_catalog import ACTION_CONTRACTS
from zap2_gui.models.network_evidence import EvidenceGraph, ProbeSpan
from zap2_gui.models.health_projection import project_health
from zap2_gui.models.error_envelope import error_envelope
from zap2_gui.adapters.launch_error_classifier import classify_launch_issue

@pytest.mark.parametrize('query,expected', [('VLESS','tunnel.connection.vless.import'),('откат firewall','runtime.owner-rules.plan.revert'),('NFQUEUE','runtimeResource'),('безопасно запустить','Plan'),('discord','tunnelConnection'),('runtime.session.status','runtime.session.status'),('тёмная','setting.theme'),('sokcs','tunnelConnection')])
def test_seeded_queries(query,expected):
    assert expected in [e.semantic_id for e in search(query,limit=100)]
    assert search(query) == search(query.upper())


def test_catalog_help_coverage_and_invoke_boundary():
    index={e.semantic_id:e for e in build_index()}
    assert len(index)==len(build_index())
    for c in ACTION_CONTRACTS:
        assert c.internal or c.action_id in index
        assert all(part in contextual_help(c.action_id) for part in ['Что:','Когда:','Эффект:','Условия:'])
        if c.privilege != 'none' or c.effect not in {'show','list','inspect','validate'} or not c.safe_invoke:
            assert not direct_invoke_allowed(c.action_id)
    assert direct_invoke_allowed('default.workflow.status')


def graph():
    g=EvidenceGraph('run','default','connection','receipt','core','config')
    for kind in ['process','listener','socks_method']:
        g.add_span(ProbeSpan(kind,kind,'run','PASS'))
    return g


def test_local_pass_never_promotes_network_or_app():
    g=graph(); rows=project_health(None,g,current_run_id='run')
    assert next(r for r in rows if r.layer=='local').status=='PASS'
    assert all(r.status=='UNKNOWN' for r in rows if r.layer in {'network','app'})
    from zap2_gui.adapters.discord_tunnel import VESKTOP_MANDATORY_HTTP_TARGETS
    host=VESKTOP_MANDATORY_HTTP_TARGETS[0]
    for kind in ['socks_connect','target_http']:g.add_span(ProbeSpan(kind,kind,'run','PASS',target=host))
    g.add_span(ProbeSpan('tls','target_tls','run','FAIL',failure_class='TLS_EOF',target=host))
    rows=project_health(None,g,current_run_id='run')
    assert next(r for r in rows if r.layer=='local').status=='PASS'
    assert next(r for r in rows if r.label=='route.https:'+host).status=='FAIL'
    assert next(r for r in rows if r.label=='vesktop.bootstrap').status=='FAIL'
    assert not g.verdicts  # view does not mutate graph/store


def test_old_run_missing_or_stale_runtime_never_green():
    for g in [None,graph()]:
        rows=project_health(SimpleNamespace(ownership_state='owned-stale',next_safe_action='inspect'),g,current_run_id='another-run')
        assert rows[0].status=='UNKNOWN'
        assert all(r.status=='UNKNOWN' for r in rows[1:])

@pytest.mark.parametrize('code,next_action', [('nft-conflict','runtime.owner-rules.reconcile'),('stale-pid','runtime.owner-rules.reconcile'),('missing-core','default.build.dependencies.inspect'),('SOCKS','discord.tunnel.evidence'),('TLS-EOF','discord.tunnel.evidence'),('unsupported-transport','discord.tunnel.evidence'),('migration','runtime.owner-rules.reconcile')])
def test_errors_have_cause_evidence_and_resolvable_next_action(code,next_action):
    envelope=error_envelope(code,'Причина',('span-1:FAIL',))
    assert envelope.next_action==next_action
    assert 'span-1:FAIL' in envelope.text() and 'Далее:' in envelope.text()


def test_classifier_existing_errors_have_envelope():
    issue=classify_launch_issue(action='start',error='core binary missing')
    assert issue and issue.envelope.evidence and issue.envelope.next_action
    assert 'Далее:' in issue.full_text()


def test_gui_all_focus_targets_and_palette_policy(tmp_path,monkeypatch):
    pytest.importorskip('PyQt6')
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    from PyQt6.QtWidgets import QApplication,QPlainTextEdit
    from zap2_gui.windows.main_window import create_main_window
    app=QApplication.instance() or QApplication([])
    # Use project for resources, isolated runtime copied by regression runner.
    window=create_main_window(Path(__file__).resolve().parents[1])
    palette=window.discovery_palette
    for e in build_index():
        if e.kind=='setting': assert window.focus_discovery_target(e.page,e.focus_target),e.semantic_id
        else:
            assert window.focus_discovery_target(e.page,None)
            assert palette.findChild(QPlainTextEdit,e.focus_target) is not None
    palette.query.setText('default.workflow.start')
    from PyQt6.QtWidgets import QPushButton
    invoke=next(b for b in palette.findChildren(QPushButton) if b.text().startswith('Выполнить'))
    assert not invoke.isEnabled()
    assert window.findChild(QPushButton,'globalDiscoveryButton')
    window.health_panel.setChecked(True)
    window.health_panel.refresh_health()
    palette.query.setText('default.workflow.status')
    assert invoke.isEnabled()
    invoke.click()
    from PyQt6.QtTest import QTest
    import time
    deadline=time.monotonic()+5
    while not invoke.isEnabled() and time.monotonic()<deadline:
        app.processEvents(); QTest.qWait(10)
    assert 'Default workflow status:' in palette.details.toPlainText()
    window.close()


def test_all_current_mandatory_predicates_can_pass_but_missing_gateway_cannot():
    from zap2_gui.adapters.discord_tunnel import VESKTOP_MANDATORY_HTTP_TARGETS,VESKTOP_GATEWAY_TARGET,VESKTOP_MAIN_WINDOW_TARGET
    g=graph()
    for host in VESKTOP_MANDATORY_HTTP_TARGETS:
        for kind in ['socks_connect','target_tls','target_http']:
            g.add_span(ProbeSpan(kind+host,kind,'run','PASS',target=host))
    g.add_span(ProbeSpan('navigation','electron_navigation','run','PASS',target=VESKTOP_MAIN_WINDOW_TARGET))
    assert next(r for r in project_health(None,g,current_run_id='run') if r.label=='vesktop.bootstrap').status=='UNKNOWN'
    g.add_span(ProbeSpan('gateway','websocket','run','PASS',target=VESKTOP_GATEWAY_TARGET))
    assert next(r for r in project_health(None,g,current_run_id='run') if r.label=='vesktop.bootstrap').status=='PASS'
    g.spans[-1]=ProbeSpan('gateway','websocket','previous-run','PASS',target=VESKTOP_GATEWAY_TARGET)
    assert next(r for r in project_health(None,g,current_run_id='run') if r.label=='vesktop.bootstrap').status=='UNKNOWN'


def test_health_loader_rejects_dead_stopped_wrong_core_and_bad_graph(monkeypatch,tmp_path):
    from zap2_gui.adapters import discovery_health,discord_tunnel
    session_path=tmp_path/'default.session.json'
    session_path.write_text('{}')
    monkeypatch.setattr(discovery_health,'runtime_kernel_status',lambda root: None)
    monkeypatch.setattr(discovery_health,'tunnel_store_paths',lambda root: SimpleNamespace())
    monkeypatch.setattr(discovery_health,'_session_path',lambda paths,profile: session_path)
    monkeypatch.setattr(discovery_health,'_load_bound_evidence_graph',lambda paths,profile,session: graph())
    for state,cmdline in [('stopped','xray'),('running','other-core'),('running','')]:
        monkeypatch.setattr(discord_tunnel,'_load_running_tunnel_session',lambda paths,profile,s=state:dict(state=s,pid=55,coreBinary='xray',runId='run'))
        monkeypatch.setattr(discord_tunnel,'_read_cmdline',lambda pid,c=cmdline:c)
        assert all(r.status=='UNKNOWN' for r in discovery_health.load_health(tmp_path)[1:])
    monkeypatch.setattr(discord_tunnel,'_load_running_tunnel_session',lambda paths,profile:dict(state='running',pid=55,coreBinary='xray',runId='run'))
    monkeypatch.setattr(discord_tunnel,'_read_cmdline',lambda pid:'xray run')
    def invalid(*args):raise ValueError('config/run/core/receipt mismatch')
    monkeypatch.setattr(discovery_health,'_load_bound_evidence_graph',invalid)
    assert all(r.status=='UNKNOWN' for r in discovery_health.load_health(tmp_path)[1:])

@pytest.mark.parametrize('symptom', ['nft conflict','stale pid','core binary missing','SOCKS peer closed','TLS EOF','unsupported transport','migration-required'])
def test_real_error_classifier_fixtures(symptom):
    issue=classify_launch_issue(action='start',error=symptom)
    assert issue and issue.envelope.cause and issue.envelope.evidence
    assert 'Далее:' in issue.full_text()


def test_one_acceptance_profile_is_shared_with_devctl():
    root=Path(__file__).resolve().parents[1]
    shell=(root/'meta_tools/hyperpatch_acceptance.sh').read_text()
    assert '--p05' in shell and 'check_p05_acceptance.py' in shell
    pipeline=(root/'tools/gui_checks/check_p05_acceptance.py').read_text()
    assert all(stage in pipeline for stage in ['check_p05_focused.py','generate_p04d_action_bindings.py','check_p03_core_generation.py','check_project_tree.py','check_p05_regression.py','summary.json','ZIP_DEFLATED'])
    assert 'sudo' not in pipeline and '--default-start' not in pipeline


@pytest.mark.parametrize('query',['theme','тема','setting.theme'])
def test_theme_primary_control_is_visible_in_default_result_limit(query):
    assert search(query)[0].semantic_id == 'setting.theme'
