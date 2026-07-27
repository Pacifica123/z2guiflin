"""Universal HAR -> evidence groups -> Blockcheck preparation.

The workbench is service-neutral. It groups exact observed hosts by domain
family, strongest browser-visible L7 hint and reason for attention. It prepares
sanitized Blockcheck inputs and a preset blueprint, but never starts privileged
network actions or edits hostlists automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from ..models.service_targets import SERVICE_TARGET_CUSTOM
from ..project_paths import discover_layout
from .blockcheck_gui import (
    BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY,
    BLOCKCHECK_SCAN_ALL_TARGETS,
    BlockcheckOptions,
    blockcheck_plan_to_text,
)
from .har_discovery import HarHostSummary, HarSummary, write_har_summary

HAR_WORKBENCH_DIR = Path(".zap2") / "discovery" / "har"
HAR_WORKBENCH_PREFIX = "workbench-"
HAR_WORKBENCH_MANIFEST = "workbench.json"
HAR_WORKBENCH_BLUEPRINT = "preset-blueprint.json"
HAR_CANDIDATE_INDEX = "candidate-index.json"
_DYNAMIC_HOST_RE = re.compile(r"(?:^|[.-])(?:rr\d+|r\d+|sn-[a-z0-9-]+|edge\d+|cdn\d+|[a-f0-9]{12,})(?:[.-]|$)", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result[:72] or "unknown"


def _attention_rank(value: str) -> int:
    return {"high": 3, "medium": 2, "low": 1, "none": 0}.get(value, 0)


@dataclass(frozen=True)
class HarEvidenceGroup:
    group_id: str
    title: str
    domain_family: str
    reason: str
    attention_level: str
    protocol: str
    l7: str
    ports: tuple[str, ...]
    hosts: tuple[str, ...]
    issue_hosts: tuple[str, ...]
    covered_hosts: tuple[str, ...]
    uncovered_hosts: tuple[str, ...]
    suggested_hostlist_entries: tuple[str, ...]
    confidence: str
    evidence: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()
    blockcheckable: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.group_id,
            "title": self.title,
            "domainFamily": self.domain_family,
            "reason": self.reason,
            "attentionLevel": self.attention_level,
            "protocol": self.protocol,
            "l7": self.l7,
            "ports": list(self.ports),
            "hosts": list(self.hosts),
            "issueHosts": list(self.issue_hosts),
            "coveredHosts": list(self.covered_hosts),
            "uncoveredHosts": list(self.uncovered_hosts),
            "suggestedHostlistEntries": list(self.suggested_hostlist_entries),
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "caveats": list(self.caveats),
            "blockcheckable": self.blockcheckable,
        }

    def blockcheck_options(self) -> BlockcheckOptions:
        if not self.blockcheckable or not self.hosts:
            raise ValueError(f"Группа {self.group_id} не поддерживает domain Blockcheck")
        return BlockcheckOptions(
            domains=" ".join(self.hosts),
            service_target_preset_id=SERVICE_TARGET_CUSTOM,
            scan_mode=BLOCKCHECK_SCAN_ALL_TARGETS,
            test="standard",
            scanlevel="quick",
            ipvs="4",
            enable_http=self.l7 == "http",
            enable_https_tls12=self.l7 in {"tls", "websocket"},
            enable_https_tls13=self.l7 in {"tls", "websocket"},
            enable_http3=self.l7 == "quic",
            skip_dnscheck="error:dns" not in self.evidence,
            repeats=1,
            curl_max_time=3,
            timeout_seconds=0,
            dead_target_guard=BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY,
        )


@dataclass(frozen=True)
class HarWorkbench:
    created_at: str
    source_name: str
    summary_path: Path
    workbench_dir: Path
    groups: tuple[HarEvidenceGroup, ...]
    warnings: tuple[str, ...] = ()
    manifest_path: Path | None = None
    blueprint_path: Path | None = None
    candidate_index_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": 2,
            "createdAt": self.created_at,
            "sourceName": self.source_name,
            "summaryPath": str(self.summary_path),
            "groups": [item.to_dict() for item in self.groups],
            "warnings": list(self.warnings),
            "safety": {
                "executesBlockcheck": False,
                "requiresSudo": False,
                "mutatesFirewallOrServices": False,
                "editsHostlists": False,
                "storesRawHar": False,
                "storesSecrets": False,
            },
        }

    def blockcheck_groups(self) -> tuple[HarEvidenceGroup, ...]:
        return tuple(item for item in self.groups if item.blockcheckable and item.hosts)

    def to_text(self) -> str:
        lines = [
            "Universal HAR workbench",
            f"created at: {self.created_at}",
            f"source: {self.source_name}",
            f"workbench: {self.workbench_dir}",
            f"sanitized summary: {self.summary_path}",
            f"manifest: {self.manifest_path or self.workbench_dir / HAR_WORKBENCH_MANIFEST}",
            f"candidate index: {self.candidate_index_path or self.workbench_dir / HAR_CANDIDATE_INDEX}",
            f"preset blueprint: {self.blueprint_path or self.workbench_dir / HAR_WORKBENCH_BLUEPRINT}",
            "scope: any resource; no service-name filter",
            "executes Blockcheck now: no",
            "requires sudo now: no",
            "mutates firewall/services now: no",
            "edits hostlists now: no",
            "stores raw HAR: no",
            "",
            "Groups:",
        ]
        if not self.groups:
            lines.append("  - none")
        for item in self.groups:
            coverage = f"covered={len(item.covered_hosts)}, uncovered={len(item.uncovered_hosts)}"
            lines.extend(
                [
                    f"  - {item.group_id}: {item.title}",
                    f"    family={item.domain_family}; reason={item.reason}; attention={item.attention_level}",
                    f"    {item.protocol.upper()} {','.join(item.ports)}; L7={item.l7}; confidence={item.confidence}",
                    f"    targets: {', '.join(item.hosts)}",
                    f"    coverage: {coverage}",
                ]
            )
            if item.suggested_hostlist_entries:
                lines.append(f"    hostlist candidates: {', '.join(item.suggested_hostlist_entries)}")
            for caveat in item.caveats:
                lines.append(f"    caveat: {caveat}")

        lines.extend(
            [
                "",
                "Automatic boundary:",
                "  - import, redaction, exact-host discovery, family grouping and Blockcheck option preparation are automatic",
                "  - exact dynamic CDN hostnames remain Blockcheck targets; family labels are only grouping metadata",
                "  - hostlist candidates are suggestions and are never inserted automatically",
                "  - browser-cancelled evidence such as NS_BINDING_ABORTED is visible but does not alone prove blocking",
                "  - privileged Blockcheck runs remain owner-confirmed",
                "  - an executable preset is assembled only after a strategy is validated for every required group",
                "  - non-HTTP UDP flows remain outside HAR and are handled by separate diagnostics/profiles",
            ]
        )
        if self.warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(f"  - {item}" for item in self.warnings)
        return "\n".join(lines)


def _workbench_root(root: Path | None = None) -> Path:
    return discover_layout(root).root / HAR_WORKBENCH_DIR


def _best_l7(item: HarHostSummary) -> str:
    hints = set(item.l7_hints)
    if "quic" in hints:
        return "quic"
    if "websocket" in hints:
        return "websocket"
    if "tls" in hints:
        return "tls"
    return "http"


def _reason(item: HarHostSummary) -> str | None:
    if item.transport_failure_count:
        return "transport-failure"
    if item.browser_cancel_count:
        return "browser-cancelled"
    if item.status_zero_count:
        return "status-zero"
    if item.http_server_error_count:
        return "http-server-error"
    if item.http_client_error_count:
        return "http-client-error"
    if item.is_uncovered:
        return "uncovered-observed"
    return None


def _reason_title(reason: str) -> str:
    return {
        "transport-failure": "transport/TLS/DNS failure candidates",
        "browser-cancelled": "browser-cancelled requests requiring review",
        "status-zero": "status=0 requests without a classified browser error",
        "http-server-error": "HTTP 5xx server-side failures",
        "http-client-error": "HTTP 4xx responses requiring context review",
        "uncovered-observed": "observed hosts missing from local hostlists",
    }.get(reason, reason)


def _reason_confidence(reason: str, l7: str) -> str:
    if reason == "transport-failure":
        return f"high transport relevance; {l7} inferred from HAR scheme/version"
    if reason == "browser-cancelled":
        return f"low-to-medium; browser cancellation can be normal; {l7} inferred from HAR"
    if reason == "status-zero":
        return f"low until repeated or confirmed by Blockcheck; {l7} inferred from HAR"
    if reason == "http-server-error":
        return "medium for service failure, low for DPI attribution"
    if reason == "http-client-error":
        return "low for DPI attribution; 4xx often means application/auth policy"
    return f"hostlist discovery evidence; {l7} inferred from HAR"


def _group_caveats(reason: str) -> tuple[str, ...]:
    if reason == "browser-cancelled":
        return ("NS_BINDING_ABORTED/ERR_ABORTED can be normal when media segments or navigation are cancelled",)
    if reason == "status-zero":
        return ("status=0 without a safe error code is incomplete evidence; repeat capture and run Blockcheck",)
    if reason == "http-client-error":
        return ("HTTP 4xx proves the server replied; it is not direct evidence of transport blocking",)
    if reason == "http-server-error":
        return ("HTTP 5xx may be a service-side failure; compare with repeated runs",)
    if reason == "uncovered-observed":
        return ("successful observation does not mean the host must be added; review whether it is required for the resource",)
    return ()


def _suggest_hostlist_entries(items: list[HarHostSummary]) -> tuple[str, ...]:
    uncovered = [item for item in items if item.is_uncovered]
    if not uncovered:
        return ()
    family = uncovered[0].domain_family
    dynamic = any(_DYNAMIC_HOST_RE.search(item.host) for item in uncovered)
    multiple = len({item.host for item in uncovered}) >= 2
    if family != "unknown" and (dynamic or multiple) and all(item.host == family or item.host.endswith(f".{family}") for item in uncovered):
        return (family,)
    return tuple(sorted({item.host for item in uncovered}))


def _group_hosts(summary: HarSummary) -> tuple[HarEvidenceGroup, ...]:
    buckets: dict[tuple[str, str, str], list[HarHostSummary]] = {}
    for item in summary.host_summaries:
        reason = _reason(item)
        if reason is None:
            continue
        l7 = _best_l7(item)
        buckets.setdefault((item.domain_family, l7, reason), []).append(item)

    groups: list[HarEvidenceGroup] = []
    for (family, l7, reason), items in sorted(buckets.items()):
        items.sort(key=lambda item: (-_attention_rank(item.attention_level), -item.request_count, item.host))
        hosts = tuple(item.host for item in items)
        issue_hosts = tuple(item.host for item in items if item.has_attention)
        covered = tuple(item.host for item in items if item.covered_by_any_hostlist)
        uncovered = tuple(item.host for item in items if item.is_uncovered)
        attention = max((item.attention_level for item in items), key=_attention_rank, default="none")
        ports = tuple(sorted({port for item in items for port in item.ports}, key=lambda value: int(value) if value.isdigit() else value))
        if not ports:
            ports = ("443",) if l7 in {"tls", "websocket", "quic"} else ("80",)
        evidence = tuple(
            sorted(
                {
                    value
                    for item in items
                    for value in (
                        *(f"scheme:{part}" for part in item.schemes),
                        *(f"http:{part}" for part in item.http_versions),
                        *(f"error:{part}" for part in item.error_categories),
                        *(f"code:{part}" for part in item.error_codes),
                        *(f"issue:{part}" for part in item.issue_classes),
                    )
                }
            )
        )
        protocol = "udp" if l7 == "quic" else "tcp"
        group_id = f"har-{_slug(family)}-{l7}-{reason}"
        groups.append(
            HarEvidenceGroup(
                group_id=group_id,
                title=f"{family}: {_reason_title(reason)}",
                domain_family=family,
                reason=reason,
                attention_level=attention,
                protocol=protocol,
                l7=l7,
                ports=ports,
                hosts=hosts,
                issue_hosts=issue_hosts,
                covered_hosts=covered,
                uncovered_hosts=uncovered,
                suggested_hostlist_entries=_suggest_hostlist_entries(items),
                confidence=_reason_confidence(reason, l7),
                evidence=evidence,
                caveats=_group_caveats(reason),
            )
        )
    groups.sort(key=lambda item: (-_attention_rank(item.attention_level), item.domain_family, item.l7, item.reason))
    return tuple(groups)


def _write_group_files(workbench_dir: Path, group: HarEvidenceGroup) -> None:
    group_dir = workbench_dir / "groups" / group.group_id
    group_dir.mkdir(parents=True, exist_ok=True)
    (group_dir / "targets.txt").write_text("\n".join(group.hosts) + ("\n" if group.hosts else ""), encoding="utf-8")
    (group_dir / "hostlist-candidates.txt").write_text(
        "\n".join(group.suggested_hostlist_entries) + ("\n" if group.suggested_hostlist_entries else ""),
        encoding="utf-8",
    )
    (group_dir / "evidence.json").write_text(
        json.dumps(group.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if group.blockcheckable and group.hosts:
        options = group.blockcheck_options()
        (group_dir / "blockcheck-options.json").write_text(
            json.dumps(
                {
                    "domains": list(options.normalized_domains()),
                    "serviceTargetPresetId": options.service_target_preset_id,
                    "scanMode": options.scan_mode,
                    "test": options.test,
                    "scanlevel": options.scanlevel,
                    "ipvs": options.ipvs,
                    "enableHttp": options.enable_http,
                    "enableHttpsTls12": options.enable_https_tls12,
                    "enableHttpsTls13": options.enable_https_tls13,
                    "enableHttp3": options.enable_http3,
                    "skipDnscheck": options.skip_dnscheck,
                    "deadTargetGuard": options.dead_target_guard,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def _candidate_index(summary: HarSummary, groups: tuple[HarEvidenceGroup, ...]) -> dict[str, Any]:
    attention_covered = sorted(item.host for item in summary.host_summaries if item.has_attention and item.covered_by_any_hostlist)
    attention_uncovered = sorted(item.host for item in summary.host_summaries if item.has_attention and item.is_uncovered)
    observed_uncovered = sorted(item.host for item in summary.host_summaries if not item.has_attention and item.is_uncovered)
    return {
        "schemaVersion": 1,
        "sourceName": summary.source_name,
        "attentionCoveredHosts": attention_covered,
        "attentionUncoveredHosts": attention_uncovered,
        "observedUncoveredHosts": observed_uncovered,
        "groupIds": [item.group_id for item in groups],
        "interpretation": {
            "attentionCoveredHosts": "hostlist already covers the hostname; strategy/L7 investigation is more relevant than adding a duplicate entry",
            "attentionUncoveredHosts": "both hostlist coverage and strategy require review",
            "observedUncoveredHosts": "dependency discovered without a clear failure; add only after owner review",
        },
    }


def _preset_blueprint(workbench: HarWorkbench) -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "title": f"Universal HAR preset blueprint / {workbench.source_name}",
        "status": "awaiting-blockcheck-evidence",
        "profileOrder": [item.group_id for item in workbench.groups],
        "groups": [
            {
                **item.to_dict(),
                "strategySelection": None,
                "hostlistDecision": "review-required" if item.suggested_hostlist_entries else "already-covered-or-not-needed",
                "readyForExecutablePreset": False,
            }
            for item in workbench.groups
        ],
        "assemblyRule": (
            "Each required HAR group becomes executable only after one nfqws2 strategy is validated against every exact target host. "
            "Domain-family labels group related hosts but never replace exact Blockcheck targets automatically."
        ),
    }


def build_har_workbench(path: str | Path, *, root: Path | None = None) -> HarWorkbench:
    summary = write_har_summary(path, root=root)
    if summary.output_path is None:
        raise ValueError("sanitized HAR summary path was not created")
    created_at = _now()
    stamp = created_at.replace(":", "").replace("-", "")
    workbench_dir = _workbench_root(root) / f"{HAR_WORKBENCH_PREFIX}{stamp}"
    workbench_dir.mkdir(parents=True, exist_ok=False)
    groups = _group_hosts(summary)
    warnings = list(summary.warnings)
    if not groups:
        warnings.append("HAR не содержит ошибок и новых hostlist-кандидатов; workbench создан без Blockcheck-групп")
    if any(item.reason == "browser-cancelled" for item in groups):
        warnings.append("browser-cancelled группы требуют повторной проверки: отмена запроса может быть нормальной для навигации или media segments")
    workbench = HarWorkbench(
        created_at=created_at,
        source_name=summary.source_name,
        summary_path=summary.output_path,
        workbench_dir=workbench_dir,
        groups=groups,
        warnings=tuple(warnings),
        manifest_path=workbench_dir / HAR_WORKBENCH_MANIFEST,
        blueprint_path=workbench_dir / HAR_WORKBENCH_BLUEPRINT,
        candidate_index_path=workbench_dir / HAR_CANDIDATE_INDEX,
    )
    for group in groups:
        _write_group_files(workbench_dir, group)
    workbench.manifest_path.write_text(
        json.dumps(workbench.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    workbench.candidate_index_path.write_text(
        json.dumps(_candidate_index(summary, groups), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    workbench.blueprint_path.write_text(
        json.dumps(_preset_blueprint(workbench), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return workbench


def _group_from_payload(data: dict[str, Any]) -> HarEvidenceGroup:
    return HarEvidenceGroup(
        group_id=str(data.get("id", "")),
        title=str(data.get("title", "")),
        domain_family=str(data.get("domainFamily", "unknown")),
        reason=str(data.get("reason", "")),
        attention_level=str(data.get("attentionLevel", "none")),
        protocol=str(data.get("protocol", "tcp")),
        l7=str(data.get("l7", "tls")),
        ports=tuple(str(item) for item in data.get("ports", []) if str(item).strip()),
        hosts=tuple(str(item) for item in data.get("hosts", []) if str(item).strip()),
        issue_hosts=tuple(str(item) for item in data.get("issueHosts", []) if str(item).strip()),
        covered_hosts=tuple(str(item) for item in data.get("coveredHosts", []) if str(item).strip()),
        uncovered_hosts=tuple(str(item) for item in data.get("uncoveredHosts", []) if str(item).strip()),
        suggested_hostlist_entries=tuple(str(item) for item in data.get("suggestedHostlistEntries", []) if str(item).strip()),
        confidence=str(data.get("confidence", "")),
        evidence=tuple(str(item) for item in data.get("evidence", []) if str(item).strip()),
        caveats=tuple(str(item) for item in data.get("caveats", []) if str(item).strip()),
        blockcheckable=bool(data.get("blockcheckable", False)),
    )


def load_har_workbench(path: str | Path) -> HarWorkbench:
    manifest = Path(path)
    if manifest.is_dir():
        manifest = manifest / HAR_WORKBENCH_MANIFEST
    data = json.loads(manifest.read_text(encoding="utf-8"))
    workbench_dir = manifest.parent
    return HarWorkbench(
        created_at=str(data.get("createdAt", "unknown")),
        source_name=str(data.get("sourceName", "unknown")),
        summary_path=Path(str(data.get("summaryPath", ""))),
        workbench_dir=workbench_dir,
        groups=tuple(_group_from_payload(item) for item in data.get("groups", []) if isinstance(item, dict)),
        warnings=tuple(str(item) for item in data.get("warnings", []) if str(item).strip()),
        manifest_path=manifest,
        blueprint_path=workbench_dir / HAR_WORKBENCH_BLUEPRINT,
        candidate_index_path=workbench_dir / HAR_CANDIDATE_INDEX,
    )


def latest_har_workbench(*, root: Path | None = None) -> HarWorkbench | None:
    root_dir = _workbench_root(root)
    candidates = sorted(path for path in root_dir.glob(f"{HAR_WORKBENCH_PREFIX}*") if path.is_dir())
    return load_har_workbench(candidates[-1]) if candidates else None


def get_har_workbench_group(group_id: str, *, root: Path | None = None) -> HarEvidenceGroup:
    workbench = latest_har_workbench(root=root)
    if workbench is None:
        raise ValueError("HAR workbench отсутствует; сначала выполните --har-workbench HAR_OR_ZIP")
    for item in workbench.groups:
        if item.group_id == group_id:
            return item
    raise ValueError(f"Группа HAR workbench не найдена: {group_id}")


def har_workbench_to_text(path: str, *, root: Path | None = None) -> str:
    return build_har_workbench(path, root=root).to_text()


def har_workbench_report_to_text(*, root: Path | None = None) -> str:
    workbench = latest_har_workbench(root=root)
    if workbench is None:
        return "\n".join(
            [
                "Universal HAR workbench",
                "status: no saved workbench",
                f"expected dir: {_workbench_root(root)}",
                "next: PYTHONPATH=gui python -m zap2_gui.app --har-workbench /path/to/capture.har",
            ]
        )
    return workbench.to_text()


def har_group_plan_to_text(group_id: str, *, root: Path | None = None) -> str:
    group = get_har_workbench_group(group_id, root=root)
    return "\n\n".join(
        [
            "\n".join(
                [
                    f"HAR group: {group.group_id}",
                    f"title: {group.title}",
                    f"family/reason: {group.domain_family}/{group.reason}",
                    f"protocol/L7: {group.protocol}/{group.l7}",
                    f"targets: {', '.join(group.hosts)}",
                    f"attention/confidence: {group.attention_level}/{group.confidence}",
                ]
            ),
            blockcheck_plan_to_text(root=root, options=group.blockcheck_options()),
        ]
    )
