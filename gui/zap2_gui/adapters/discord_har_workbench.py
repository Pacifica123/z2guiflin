"""HAR -> evidence groups -> Blockcheck preparation for Discord.

Workbench intentionally stops before privileged execution. It writes sanitized
metadata, groups browser-visible domains by the strongest available L7 hint and
prepares Blockcheck options. Discord Voice is attached as a separate source
catalog because browser HAR does not contain the UDP media flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from ..models.service_targets import SERVICE_TARGET_CUSTOM
from ..project_paths import discover_layout
from .blockcheck_gui import (
    BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY,
    BLOCKCHECK_SCAN_ALL_TARGETS,
    BlockcheckOptions,
    blockcheck_plan_to_text,
)
from .discord_har_discovery import DiscordHarSummary, HarHostSummary, write_discord_har_summary
from .discord_voice_profiles import DISCORD_VOICE_PRESET_IDS


HAR_WORKBENCH_PREFIX = "har-workbench-"
HAR_WORKBENCH_MANIFEST = "workbench.json"
HAR_WORKBENCH_BLUEPRINT = "preset-blueprint.json"


@dataclass(frozen=True)
class HarEvidenceGroup:
    group_id: str
    title: str
    protocol: str
    l7: str
    ports: tuple[str, ...]
    hosts: tuple[str, ...]
    issue_hosts: tuple[str, ...]
    confidence: str
    evidence: tuple[str, ...] = ()
    blockcheckable: bool = True
    source_preset_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.group_id,
            "title": self.title,
            "protocol": self.protocol,
            "l7": self.l7,
            "ports": list(self.ports),
            "hosts": list(self.hosts),
            "issueHosts": list(self.issue_hosts),
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "blockcheckable": self.blockcheckable,
            "sourcePresetIds": list(self.source_preset_ids),
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
            skip_dnscheck=True,
            repeats=1,
            curl_max_time=3,
            timeout_seconds=0,
            dead_target_guard=BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY,
        )


@dataclass(frozen=True)
class DiscordHarWorkbench:
    created_at: str
    source_name: str
    summary_path: Path
    workbench_dir: Path
    groups: tuple[HarEvidenceGroup, ...]
    warnings: tuple[str, ...] = ()
    manifest_path: Path | None = None
    blueprint_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "createdAt": self.created_at,
            "sourceName": self.source_name,
            "summaryPath": str(self.summary_path),
            "groups": [item.to_dict() for item in self.groups],
            "warnings": list(self.warnings),
            "safety": {
                "executesBlockcheck": False,
                "requiresSudo": False,
                "mutatesFirewallOrServices": False,
                "storesRawHar": False,
                "storesSecrets": False,
            },
        }

    def blockcheck_groups(self) -> tuple[HarEvidenceGroup, ...]:
        return tuple(item for item in self.groups if item.blockcheckable and item.hosts)

    def to_text(self) -> str:
        lines = [
            "Discord HAR workbench",
            f"created at: {self.created_at}",
            f"source: {self.source_name}",
            f"workbench: {self.workbench_dir}",
            f"sanitized summary: {self.summary_path}",
            f"manifest: {self.manifest_path or self.workbench_dir / HAR_WORKBENCH_MANIFEST}",
            f"preset blueprint: {self.blueprint_path or self.workbench_dir / HAR_WORKBENCH_BLUEPRINT}",
            "executes Blockcheck now: no",
            "requires sudo now: no",
            "mutates firewall/services now: no",
            "stores raw HAR: no",
            "",
            "Groups:",
        ]
        for item in self.groups:
            hosts = ", ".join(item.hosts) if item.hosts else "нет domain targets"
            issues = ", ".join(item.issue_hosts) if item.issue_hosts else "не отмечены"
            mode = "Blockcheck" if item.blockcheckable else "source profile only"
            lines.extend(
                [
                    f"  - {item.group_id}: {item.title}",
                    f"    {item.protocol.upper()} {','.join(item.ports)}; L7={item.l7}; confidence={item.confidence}; mode={mode}",
                    f"    hosts: {hosts}",
                    f"    issue hosts: {issues}",
                ]
            )
            if item.source_preset_ids:
                lines.append(f"    voice presets: {', '.join(item.source_preset_ids)}")
        lines.extend(
            [
                "",
                "Automatic boundary:",
                "  - import, redaction, grouping, Blockcheck option preparation and preset blueprint are automatic",
                "  - privileged Blockcheck runs remain owner-confirmed",
                "  - one final executable preset is not assembled until one strategy is proven for every required host in its group",
                "  - Discord Voice remains a separate UDP experiment because HAR does not contain media packets",
            ]
        )
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"  - {item}" for item in self.warnings)
        return "\n".join(lines)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _workbench_root(root: Path | None = None) -> Path:
    layout = discover_layout(root)
    return layout.root / ".zap2" / "discovery"


def _host_has_issue(item: HarHostSummary) -> bool:
    return item.error_count > 0 or item.failed_status_count > 0


def _best_l7(item: HarHostSummary) -> str:
    hints = set(item.l7_hints)
    if "quic" in hints:
        return "quic"
    if "websocket" in hints:
        return "websocket"
    if "tls" in hints:
        return "tls"
    return "http"


def _group_hosts(summary: DiscordHarSummary) -> tuple[HarEvidenceGroup, ...]:
    buckets: dict[str, list[HarHostSummary]] = {"http": [], "tls": [], "websocket": [], "quic": []}
    for item in summary.host_summaries:
        if item.category == "external-other":
            continue
        buckets[_best_l7(item)].append(item)

    definitions = {
        "http": ("HAR HTTP", "tcp", ("80",), "scheme/http metadata"),
        "tls": ("HAR HTTPS/TLS", "tcp", ("443",), "scheme/HTTP version metadata"),
        "websocket": ("HAR WebSocket over TLS", "tcp", ("443",), "wss/status 101 metadata"),
        "quic": ("HAR HTTP/3/QUIC evidence", "udp", ("443",), "HTTP h3 metadata; browser-dependent"),
    }
    groups: list[HarEvidenceGroup] = []
    for l7 in ("http", "tls", "websocket", "quic"):
        items = buckets[l7]
        if not items:
            continue
        issue_items = [item for item in items if _host_has_issue(item)]
        selected = issue_items or items
        suffix = "problems" if issue_items else "observed"
        title, protocol, ports, confidence = definitions[l7]
        groups.append(
            HarEvidenceGroup(
                group_id=f"har-{l7}-{suffix}",
                title=f"{title}: {'ошибки' if issue_items else 'наблюдаемые hosts'}",
                protocol=protocol,
                l7=l7,
                ports=ports,
                hosts=tuple(item.host for item in selected),
                issue_hosts=tuple(item.host for item in issue_items),
                confidence=confidence,
                evidence=tuple(
                    sorted(
                        {
                            evidence
                            for item in selected
                            for evidence in (
                                *(f"scheme:{value}" for value in item.schemes),
                                *(f"http:{value}" for value in item.http_versions),
                                *(f"error:{value}" for value in item.error_categories),
                            )
                        }
                    )
                ),
            )
        )

    groups.append(
        HarEvidenceGroup(
            group_id="discord-voice-source-candidates",
            title="Discord Voice UDP source candidates",
            protocol="udp",
            l7="stun,discord",
            ports=("50000-50099", "19294-19344", "50000-50100", "443-65535"),
            hosts=(),
            issue_hosts=(),
            confidence="source configs + upstream protocol signatures; not HAR evidence",
            evidence=(
                "Flowseal UDP ranges and L7 discord,stun",
                "zapret2 GUI Windows voice profiles",
                "bol-van Linux custom.d Discord/STUN examples",
            ),
            blockcheckable=False,
            source_preset_ids=DISCORD_VOICE_PRESET_IDS,
        )
    )
    return tuple(groups)


def _write_group_files(workbench_dir: Path, group: HarEvidenceGroup) -> None:
    group_dir = workbench_dir / "groups" / group.group_id
    group_dir.mkdir(parents=True, exist_ok=True)
    (group_dir / "targets.txt").write_text("\n".join(group.hosts) + ("\n" if group.hosts else ""), encoding="utf-8")
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
                    "deadTargetGuard": options.dead_target_guard,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def _preset_blueprint(workbench: DiscordHarWorkbench) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "title": f"Discord HAR preset blueprint / {workbench.source_name}",
        "status": "awaiting-blockcheck-evidence",
        "profileOrder": [item.group_id for item in workbench.groups],
        "groups": [
            {
                **item.to_dict(),
                "strategySelection": None if item.blockcheckable else {"candidatePresetIds": list(item.source_preset_ids)},
                "readyForExecutablePreset": not item.blockcheckable,
            }
            for item in workbench.groups
        ],
        "assemblyRule": (
            "A browser-visible group becomes executable only after one nfqws2 strategy is validated against every required host. "
            "Voice candidates are alternative presets and are not merged automatically."
        ),
    }


def build_discord_har_workbench(path: str | Path, *, root: Path | None = None) -> DiscordHarWorkbench:
    summary = write_discord_har_summary(path, root=root)
    if summary.output_path is None:
        raise ValueError("sanitized HAR summary path was not created")
    created_at = _now()
    stamp = created_at.replace(":", "").replace("-", "")
    workbench_dir = _workbench_root(root) / f"{HAR_WORKBENCH_PREFIX}{stamp}"
    workbench_dir.mkdir(parents=True, exist_ok=False)
    groups = _group_hosts(summary)
    warnings = list(summary.warnings)
    if not any(item.blockcheckable for item in groups):
        warnings.append("HAR не содержит Discord-related HTTP/TLS/QUIC hosts для Blockcheck")
    if not any(item.issue_hosts for item in groups):
        warnings.append("HAR не содержит явных status/error failures; группы построены по наблюдаемым hosts")
    workbench = DiscordHarWorkbench(
        created_at=created_at,
        source_name=summary.source_name,
        summary_path=summary.output_path,
        workbench_dir=workbench_dir,
        groups=groups,
        warnings=tuple(warnings),
        manifest_path=workbench_dir / HAR_WORKBENCH_MANIFEST,
        blueprint_path=workbench_dir / HAR_WORKBENCH_BLUEPRINT,
    )
    for group in groups:
        _write_group_files(workbench_dir, group)
    workbench.manifest_path.write_text(
        json.dumps(workbench.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
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
        protocol=str(data.get("protocol", "")),
        l7=str(data.get("l7", "")),
        ports=tuple(str(item) for item in data.get("ports", []) if str(item).strip()),
        hosts=tuple(str(item) for item in data.get("hosts", []) if str(item).strip()),
        issue_hosts=tuple(str(item) for item in data.get("issueHosts", []) if str(item).strip()),
        confidence=str(data.get("confidence", "")),
        evidence=tuple(str(item) for item in data.get("evidence", []) if str(item).strip()),
        blockcheckable=bool(data.get("blockcheckable", False)),
        source_preset_ids=tuple(str(item) for item in data.get("sourcePresetIds", []) if str(item).strip()),
    )


def load_discord_har_workbench(path: str | Path) -> DiscordHarWorkbench:
    manifest = Path(path)
    if manifest.is_dir():
        manifest = manifest / HAR_WORKBENCH_MANIFEST
    data = json.loads(manifest.read_text(encoding="utf-8"))
    workbench_dir = manifest.parent
    summary_path = Path(str(data.get("summaryPath", "")))
    return DiscordHarWorkbench(
        created_at=str(data.get("createdAt", "unknown")),
        source_name=str(data.get("sourceName", "unknown")),
        summary_path=summary_path,
        workbench_dir=workbench_dir,
        groups=tuple(_group_from_payload(item) for item in data.get("groups", []) if isinstance(item, dict)),
        warnings=tuple(str(item) for item in data.get("warnings", []) if str(item).strip()),
        manifest_path=manifest,
        blueprint_path=workbench_dir / HAR_WORKBENCH_BLUEPRINT,
    )


def latest_discord_har_workbench(*, root: Path | None = None) -> DiscordHarWorkbench | None:
    root_dir = _workbench_root(root)
    candidates = sorted(path for path in root_dir.glob(f"{HAR_WORKBENCH_PREFIX}*") if path.is_dir())
    if not candidates:
        return None
    return load_discord_har_workbench(candidates[-1])


def get_har_workbench_group(group_id: str, *, root: Path | None = None) -> HarEvidenceGroup:
    workbench = latest_discord_har_workbench(root=root)
    if workbench is None:
        raise ValueError("HAR workbench отсутствует; сначала выполните --discord-har-workbench HAR_OR_ZIP")
    for item in workbench.groups:
        if item.group_id == group_id:
            return item
    raise ValueError(f"Группа HAR workbench не найдена: {group_id}")


def discord_har_workbench_to_text(path: str, *, root: Path | None = None) -> str:
    return build_discord_har_workbench(path, root=root).to_text()


def discord_har_workbench_report_to_text(*, root: Path | None = None) -> str:
    workbench = latest_discord_har_workbench(root=root)
    if workbench is None:
        return "\n".join(
            [
                "Discord HAR workbench",
                "status: no saved workbench",
                f"expected dir: {_workbench_root(root)}",
                "next: PYTHONPATH=gui python -m zap2_gui.app --discord-har-workbench /path/to/capture.har",
            ]
        )
    return workbench.to_text()


def discord_har_group_plan_to_text(group_id: str, *, root: Path | None = None) -> str:
    group = get_har_workbench_group(group_id, root=root)
    return "\n\n".join(
        [
            "\n".join(
                [
                    f"HAR group: {group.group_id}",
                    f"title: {group.title}",
                    f"protocol/L7: {group.protocol}/{group.l7}",
                    f"targets: {', '.join(group.hosts)}",
                    f"confidence: {group.confidence}",
                ]
            ),
            blockcheck_plan_to_text(root=root, options=group.blockcheck_options()),
        ]
    )
