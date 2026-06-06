"""Модели высокоуровневых стратегий workspace."""

from __future__ import annotations

from dataclasses import dataclass


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

    @property
    def is_plan_only(self) -> bool:
        return (
            not self.capabilities.executes_automatically
            and not self.capabilities.requires_sudo_at_stage7
            and not self.capabilities.mutates_services_or_firewall_at_stage7
        )
