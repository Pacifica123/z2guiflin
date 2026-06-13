"""Read-only external working reference audit for the Discord v0.4 lane.

Stage 7o0 deliberately imports curated summaries, not runnable third-party
scripts.  The adapter exposes the audit to CLI/tests so the next candidate
strategy stage can be based on explicit reference evidence instead of ad-hoc
copying of flags.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..project_paths import discover_layout

AUDIT_RELATIVE_PATH = Path("references/external/stage7o0_external_reference_audit.json")


@dataclass(frozen=True)
class ExternalReferenceSource:
    source_id: str
    archive: str
    family: str
    tcp_ports: tuple[str, ...]
    udp_ports: tuple[str, ...]
    packet_window: str
    owner_scoped: bool
    edge_ip_scoped: bool
    strategy_families: tuple[str, ...]
    risks: tuple[str, ...]


@dataclass(frozen=True)
class ExternalReferenceCandidateFamily:
    candidate_id: str
    stage: str
    capture_shape: str
    profile_shape: str
    why: str


@dataclass(frozen=True)
class ExternalReferenceAudit:
    schema_version: int
    stage: str
    audit_id: str
    title: str
    status: str
    safety: dict[str, Any]
    sources: tuple[ExternalReferenceSource, ...]
    cross_source_findings: tuple[str, ...]
    candidate_families: tuple[ExternalReferenceCandidateFamily, ...]
    recommended_next_stages: tuple[str, ...]
    path: Path

    @property
    def external_scripts_execute(self) -> bool:
        return bool(self.safety.get("executesExternalScripts"))

    @property
    def mutates_firewall_or_services(self) -> bool:
        return bool(self.safety.get("mutatesFirewallOrServices"))

    @property
    def safe_for_reference_only(self) -> bool:
        return not self.external_scripts_execute and not self.mutates_firewall_or_services


def _as_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    if isinstance(value, tuple):
        return tuple(str(item) for item in value)
    if value is None:
        return ()
    return (str(value),)


def _capture_ports(capture: dict[str, Any], key: str, fallback_key: str | None = None) -> tuple[str, ...]:
    raw = capture.get(key)
    if raw is None and fallback_key is not None:
        raw = capture.get(fallback_key)
    return _as_tuple(raw)


def _packet_window(capture: dict[str, Any]) -> str:
    tcp_out = capture.get("tcpPktOut")
    tcp_in = capture.get("tcpPktIn")
    udp_out = capture.get("udpPktOut")
    udp_in = capture.get("udpPktIn")
    parts: list[str] = []
    if tcp_out or tcp_in:
        parts.append(f"tcp out/in={tcp_out or 'n/a'}/{tcp_in or 'n/a'}")
    if udp_out or udp_in:
        parts.append(f"udp out/in={udp_out or 'n/a'}/{udp_in or 'n/a'}")
    return "; ".join(parts) or "not declared"


def load_external_reference_audit(root: Path | None = None) -> ExternalReferenceAudit:
    layout = discover_layout(root)
    path = layout.root / AUDIT_RELATIVE_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    if int(data.get("schemaVersion", 0)) != 1:
        raise ValueError(f"Неподдерживаемая schemaVersion в {path}")
    sources: list[ExternalReferenceSource] = []
    for item in data.get("sources", []):
        capture = item.get("captureEnvelope") if isinstance(item.get("captureEnvelope"), dict) else {}
        sources.append(
            ExternalReferenceSource(
                source_id=str(item.get("id", "")),
                archive=str(item.get("archive", "")),
                family=str(item.get("family", "")),
                tcp_ports=_capture_ports(capture, "tcpPorts", "tcpPortsObserved"),
                udp_ports=_capture_ports(capture, "udpPorts", "udpPortsObserved"),
                packet_window=_packet_window(capture),
                owner_scoped=bool(capture.get("ownerScoped")),
                edge_ip_scoped=bool(capture.get("edgeIpScoped")),
                strategy_families=_as_tuple(item.get("strategyFamilies")),
                risks=_as_tuple(item.get("risks")),
            )
        )
    candidates: list[ExternalReferenceCandidateFamily] = []
    for item in data.get("candidateFamilies", []):
        candidates.append(
            ExternalReferenceCandidateFamily(
                candidate_id=str(item.get("id", "")),
                stage=str(item.get("stage", "")),
                capture_shape=str(item.get("captureShape", "")),
                profile_shape=str(item.get("profileShape", "")),
                why=str(item.get("why", "")),
            )
        )
    return ExternalReferenceAudit(
        schema_version=int(data["schemaVersion"]),
        stage=str(data.get("stage", "")),
        audit_id=str(data.get("id", "")),
        title=str(data.get("title", "")),
        status=str(data.get("status", "")),
        safety=dict(data.get("safety", {})),
        sources=tuple(sources),
        cross_source_findings=_as_tuple(data.get("crossSourceFindings")),
        candidate_families=tuple(candidates),
        recommended_next_stages=_as_tuple(data.get("recommendedNextStages")),
        path=path,
    )


def external_reference_audit_to_text(root: Path | None = None) -> str:
    audit = load_external_reference_audit(root)
    lines: list[str] = [
        "External working reference audit",
        f"stage: {audit.stage}",
        f"audit id: {audit.audit_id}",
        f"status: {audit.status}",
        f"sources: {len(audit.sources)}",
        f"candidate families: {len(audit.candidate_families)}",
        f"safe reference-only: {'yes' if audit.safe_for_reference_only else 'no'}",
        f"audit file: {audit.path}",
        "executes external scripts now: no",
        "mutates services/firewall now: no",
        "changes default strategy now: no",
        "",
        "Reference sources:",
    ]
    for source in audit.sources:
        tcp = ", ".join(source.tcp_ports) if source.tcp_ports else "not declared"
        udp = ", ".join(source.udp_ports) if source.udp_ports else "not declared"
        families = "; ".join(source.strategy_families[:3]) if source.strategy_families else "not declared"
        lines.extend(
            [
                f"- {source.source_id}: {source.family}",
                f"  archive: {source.archive}",
                f"  tcp capture: {tcp}",
                f"  udp capture: {udp}",
                f"  packet window: {source.packet_window}",
                f"  owner-scoped: {'yes' if source.owner_scoped else 'no'}; edge-ip-scoped: {'yes' if source.edge_ip_scoped else 'no'}",
                f"  families: {families}",
            ]
        )
    lines.append("")
    lines.append("Cross-source findings:")
    for finding in audit.cross_source_findings:
        lines.append(f"- {finding}")
    lines.append("")
    lines.append("Future candidate families, not imported as runnable strategies yet:")
    for candidate in audit.candidate_families:
        lines.extend(
            [
                f"- {candidate.candidate_id} ({candidate.stage})",
                f"  capture: {candidate.capture_shape}",
                f"  profile: {candidate.profile_shape}",
                f"  why: {candidate.why}",
            ]
        )
    lines.append("")
    lines.append("Recommended next stages:")
    for stage in audit.recommended_next_stages:
        lines.append(f"- {stage}")
    return "\n".join(lines)
