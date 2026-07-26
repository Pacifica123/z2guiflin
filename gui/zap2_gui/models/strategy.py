"""Модели высокоуровневых стратегий workspace."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyCapabilities:
    """Read-only capabilities, которые стратегия объявляет для GUI."""

    reads_profiles: bool
    reads_hostlists: bool
    uses_local_build_plan: bool
    executes_automatically: bool
    requires_sudo_at_stage7: bool
    mutates_services_or_firewall_at_stage7: bool


@dataclass(frozen=True)
class WorkspaceStrategy:
    """Описание стратегии как данных, а не как исполняемой команды."""

    schema_version: int
    strategy_id: str
    title: str
    summary: str
    philosophy: str
    intended_for: tuple[str, ...]
    workflow: tuple[str, ...]
    capabilities: StrategyCapabilities
    notes: tuple[str, ...]
    runtime_args: tuple[str, ...] = ()
    preset_path: str = ""
    source_preset: dict[str, Any] | None = None
    service_target: dict[str, Any] | None = None
    capture_policy: dict[str, Any] | None = None
    diagnostic_hints: dict[str, Any] | None = None

    @property
    def capture_policy_label(self) -> str:
        if not self.capture_policy:
            return "capture policy: default runtime-derived"
        kind = str(self.capture_policy.get("kind") or "custom")
        tcp_ports = self.capture_policy.get("tcpOutPorts")
        edge_ips = self.capture_policy.get("edgeIps")
        tcp_count = len(tcp_ports) if isinstance(tcp_ports, list) else 0
        edge_count = len(edge_ips) if isinstance(edge_ips, list) else 0
        return f"capture policy: {kind}; tcp ports={tcp_count}; edge IPs={edge_count}"

    @property
    def service_target_label(self) -> str:
        if not self.service_target:
            return "not tagged"
        title = str(self.service_target.get("title") or "").strip()
        preset_id = str(self.service_target.get("presetId") or "").strip()
        if title and preset_id:
            return f"{title} ({preset_id})"
        return title or preset_id or "not tagged"


    @property
    def service_target_coverage_label(self) -> str:
        if not self.service_target:
            return "coverage: not tagged"
        coverage = self.service_target.get("coverage")
        if not isinstance(coverage, dict):
            return "coverage: unavailable"
        targets = coverage.get("targets")
        if not isinstance(targets, list):
            return "coverage: unavailable"
        counts: Counter[str] = Counter()
        for item in targets:
            if isinstance(item, dict):
                counts[str(item.get("status") or "unknown")] += 1
        if not counts:
            return "coverage: unavailable"
        summary = ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))
        scope = str(coverage.get("scope") or "per-target")
        return f"coverage: {summary}; scope: {scope}"

    @property
    def is_plan_only(self) -> bool:
        return (
            not self.capabilities.executes_automatically
            and not self.capabilities.requires_sudo_at_stage7
            and not self.capabilities.mutates_services_or_firewall_at_stage7
        )
