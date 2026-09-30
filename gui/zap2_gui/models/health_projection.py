"""Health views preserve typed predicates, run binding and UNKNOWN boundaries."""
from __future__ import annotations
from dataclasses import dataclass
from .network_evidence import EvidenceGraph, CapabilityVerdict, capability_from_required_spans

@dataclass(frozen=True)
class HealthRow:
    layer: str
    label: str
    status: str
    evidence: str
    next_action: str


def verdict_status(verdict: CapabilityVerdict) -> str:
    if verdict.failed_requirements: return 'FAIL'
    if not verdict.requirements or verdict.missing_requirements or verdict.stale_evidence_ignored: return 'UNKNOWN'
    return 'PASS' if verdict.support == 'SUPPORTED' else 'UNKNOWN'


def project_health(runtime: object | None, graph: EvidenceGraph | None, *, current_run_id: str = '') -> tuple[HealthRow, ...]:
    state = getattr(runtime, 'ownership_state', 'unknown')
    runtime_status = {'owned-active':'PASS', 'absent':'STOPPED', 'owned-stale':'UNKNOWN', 'owned-partial':'FAIL', 'foreign-conflict':'FAIL', 'migration-required':'UNKNOWN'}.get(state, 'UNKNOWN')
    rows = [HealthRow('runtime','Процесс и firewall',runtime_status,state,getattr(runtime,'next_safe_action','default.workflow.status'))]
    if graph is None or not current_run_id or graph.run_id != current_run_id:
        rows.extend(HealthRow(layer,label,'UNKNOWN','Нет текущих связанных данных','discord.tunnel.evidence') for layer,label in [('local','Локальный SOCKS'),('network','HTTPS / TLS'),('app','Discord / Vesktop')])
        return tuple(rows)
    local = capability_from_required_spans(capability_id='local', run_id=current_run_id, spans=graph.spans, requirements=(('process',None),('listener',None),('socks_method',None)))
    rows.append(HealthRow('local','Локальный SOCKS',verdict_status(local),','.join(local.evidence_refs),'discord.tunnel.evidence'))
    # Use P01 mandatory target/capability logic, including Gateway and navigation.
    from ..adapters.discord_tunnel import _refresh_capability_verdicts
    current = EvidenceGraph.from_dict(graph.to_dict())
    current.verdicts = []
    _refresh_capability_verdicts(current)
    for v in current.verdicts:
        layer = 'network' if v.capability_id.startswith('route.') else 'app'
        rows.append(HealthRow(layer,v.capability_id,verdict_status(v), '; '.join((*v.failed_requirements,*v.missing_requirements,*v.evidence_refs)),v.next_experiment))
    return tuple(rows)
