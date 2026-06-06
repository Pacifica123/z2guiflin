"""Read-only adapter для workspace-профилей и стратегий.

Stage 7 делает стратегии и профили видимыми данными проекта. Adapter ничего не
применяет к системе: он только читает JSON, валидирует связи и готовит текстовое
представление для CLI/GUI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .local_build import supported_build_targets
from ..models.strategy import StrategyCapabilities, WorkspaceStrategy
from ..models.workspace_profile import HostlistRef, WorkspaceProfile, WorkspaceSafety
from ..project_paths import discover_layout


@dataclass(frozen=True)
class StrategyCatalog:
    schema_version: int
    default_strategy_id: str
    strategies: tuple[WorkspaceStrategy, ...]
    automatic_checks_may_execute_strategies: bool
    strategies_are_plans_only: bool

    def by_id(self) -> dict[str, WorkspaceStrategy]:
        return {strategy.strategy_id: strategy for strategy in self.strategies}


@dataclass(frozen=True)
class WorkspaceCatalog:
    profiles: tuple[WorkspaceProfile, ...]
    strategies: tuple[WorkspaceStrategy, ...]
    default_profile_id: str
    default_strategy_id: str

    def profile_by_id(self) -> dict[str, WorkspaceProfile]:
        return {profile.profile_id: profile for profile in self.profiles}

    def strategy_by_id(self) -> dict[str, WorkspaceStrategy]:
        return {strategy.strategy_id: strategy for strategy in self.strategies}


@dataclass(frozen=True)
class ProfileValidationIssue:
    severity: str
    message: str


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_schema(data: dict[str, Any], path: Path) -> None:
    if int(data.get("schemaVersion", 0)) != 1:
        raise ValueError(f"Неподдерживаемая schemaVersion в {path}")


def _parse_strategy(path: Path) -> WorkspaceStrategy:
    data = _read_json(path)
    _require_schema(data, path)
    raw_capabilities = data["capabilities"]
    capabilities = StrategyCapabilities(
        reads_profiles=bool(raw_capabilities["readsProfiles"]),
        reads_hostlists=bool(raw_capabilities["readsHostlists"]),
        uses_local_build_plan=bool(raw_capabilities["usesLocalBuildPlan"]),
        executes_automatically=bool(raw_capabilities["executesAutomatically"]),
        requires_sudo_at_stage7=bool(raw_capabilities["requiresSudoAtStage7"]),
        mutates_services_or_firewall_at_stage7=bool(raw_capabilities["mutatesServicesOrFirewallAtStage7"]),
    )
    return WorkspaceStrategy(
        schema_version=int(data["schemaVersion"]),
        strategy_id=str(data["id"]),
        title=str(data["title"]),
        summary=str(data["summary"]),
        philosophy=str(data["philosophy"]),
        intended_for=tuple(str(item) for item in data.get("intendedFor", [])),
        workflow=tuple(str(item) for item in data.get("workflow", [])),
        capabilities=capabilities,
        notes=tuple(str(item) for item in data.get("notes", [])),
        runtime_args=tuple(str(item) for item in data.get("runtimeArgs", [])),
        source_preset=dict(data["sourcePreset"]) if isinstance(data.get("sourcePreset"), dict) else None,
    )


def _parse_profile(path: Path) -> WorkspaceProfile:
    data = _read_json(path)
    _require_schema(data, path)
    raw_safety = data["safety"]
    safety = WorkspaceSafety(
        read_only_in_checks=bool(raw_safety["readOnlyInChecks"]),
        requires_owner_confirmation_before_apply=bool(raw_safety["requiresOwnerConfirmationBeforeApply"]),
        may_use_sudo=bool(raw_safety["mayUseSudo"]),
        may_mutate_services_or_firewall=bool(raw_safety["mayMutateServicesOrFirewall"]),
    )
    hostlists = tuple(
        HostlistRef(
            hostlist_id=str(item["id"]),
            path=str(item["path"]),
            purpose=str(item["purpose"]),
        )
        for item in data.get("hostlists", [])
    )
    return WorkspaceProfile(
        schema_version=int(data["schemaVersion"]),
        profile_id=str(data["id"]),
        title=str(data["title"]),
        description=str(data["description"]),
        strategy_id=str(data["strategyId"]),
        build_target=str(data["buildTarget"]),
        hostlists=hostlists,
        safety=safety,
        notes=tuple(str(item) for item in data.get("notes", [])),
    )


def load_strategy_catalog(root: Path | None = None) -> StrategyCatalog:
    layout = discover_layout(root)
    catalog_path = layout.root / "strategies" / "catalog.json"
    catalog_data = _read_json(catalog_path)
    _require_schema(catalog_data, catalog_path)
    strategies = tuple(_parse_strategy(layout.root / rel_path) for rel_path in catalog_data["strategyFiles"])
    strategy_ids = [strategy.strategy_id for strategy in strategies]
    if len(strategy_ids) != len(set(strategy_ids)):
        raise ValueError("В strategy catalog есть повторяющиеся id")
    default_strategy_id = str(catalog_data["defaultStrategyId"])
    if default_strategy_id not in set(strategy_ids):
        raise ValueError("defaultStrategyId отсутствует среди strategyFiles")
    safety = catalog_data["safety"]
    return StrategyCatalog(
        schema_version=int(catalog_data["schemaVersion"]),
        default_strategy_id=default_strategy_id,
        strategies=strategies,
        automatic_checks_may_execute_strategies=bool(safety["automaticChecksMayExecuteStrategies"]),
        strategies_are_plans_only=bool(safety["strategiesArePlansOnly"]),
    )


def list_workspace_profile_paths(root: Path | None = None) -> tuple[Path, ...]:
    layout = discover_layout(root)
    profile_dir = layout.root / "profiles"
    return tuple(sorted(path for path in profile_dir.glob("*.json") if path.is_file()))


def load_workspace_profiles(root: Path | None = None) -> tuple[WorkspaceProfile, ...]:
    return tuple(_parse_profile(path) for path in list_workspace_profile_paths(root))


def load_workspace_profile(root: Path | None = None, profile_id: str = "default") -> WorkspaceProfile:
    profiles = {profile.profile_id: profile for profile in load_workspace_profiles(root)}
    if profile_id not in profiles:
        raise ValueError(f"Неизвестный workspace-профиль: {profile_id}. Доступно: {', '.join(sorted(profiles))}")
    return profiles[profile_id]


def validate_workspace_catalog(root: Path | None = None) -> tuple[ProfileValidationIssue, ...]:
    layout = discover_layout(root)
    catalog = load_strategy_catalog(layout.root)
    strategies = catalog.by_id()
    build_targets = set(supported_build_targets())
    issues: list[ProfileValidationIssue] = []

    if catalog.automatic_checks_may_execute_strategies:
        issues.append(ProfileValidationIssue("error", "Strategy catalog разрешает выполнение стратегий в проверках"))
    if not catalog.strategies_are_plans_only:
        issues.append(ProfileValidationIssue("error", "Strategy catalog должен оставаться plan-only"))
    for strategy in catalog.strategies:
        if not strategy.is_plan_only:
            issues.append(ProfileValidationIssue("error", f"Стратегия {strategy.strategy_id} не является plan-only"))

    for profile in load_workspace_profiles(layout.root):
        if profile.strategy_id not in strategies:
            issues.append(ProfileValidationIssue("error", f"Профиль {profile.profile_id} ссылается на неизвестную стратегию"))
        if profile.build_target not in build_targets:
            issues.append(ProfileValidationIssue("error", f"Профиль {profile.profile_id} использует неизвестный build target"))
        if not profile.is_read_only_stage7:
            issues.append(ProfileValidationIssue("error", f"Профиль {profile.profile_id} нарушает read-only boundary Stage 7"))
        for hostlist in profile.hostlists:
            hostlist_path = layout.root / hostlist.path
            try:
                hostlist_path.relative_to(layout.root)
            except ValueError:
                issues.append(ProfileValidationIssue("error", f"Hostlist {hostlist.hostlist_id} выходит за пределы workspace"))
            if not hostlist_path.exists():
                issues.append(ProfileValidationIssue("error", f"Hostlist {hostlist.hostlist_id} не найден: {hostlist.path}"))
    return tuple(issues)


def load_workspace_catalog(root: Path | None = None) -> WorkspaceCatalog:
    layout = discover_layout(root)
    strategy_catalog = load_strategy_catalog(layout.root)
    profiles = load_workspace_profiles(layout.root)
    if not profiles:
        raise ValueError("Нет workspace-профилей")
    profile_ids = [profile.profile_id for profile in profiles]
    if len(profile_ids) != len(set(profile_ids)):
        raise ValueError("В profiles/ есть повторяющиеся id")
    issues = validate_workspace_catalog(layout.root)
    errors = [issue.message for issue in issues if issue.severity == "error"]
    if errors:
        raise ValueError("; ".join(errors))
    default_profile_id = "default" if "default" in set(profile_ids) else profiles[0].profile_id
    return WorkspaceCatalog(
        profiles=profiles,
        strategies=strategy_catalog.strategies,
        default_profile_id=default_profile_id,
        default_strategy_id=strategy_catalog.default_strategy_id,
    )


def workspace_profiles_to_text(root: Path | None = None) -> str:
    catalog = load_workspace_catalog(root)
    lines = ["Workspace profiles:"]
    for profile in catalog.profiles:
        default_marker = " (default)" if profile.profile_id == catalog.default_profile_id else ""
        lines.append(f"  {profile.profile_id}{default_marker}: {profile.title}")
        lines.append(f"    strategy: {profile.strategy_id}; build target: {profile.build_target}")
        lines.append(f"    hostlists: {len(profile.hostlists)}; read-only checks: yes")
    return "\n".join(lines)


def workspace_profile_to_text(profile_id: str = "default", root: Path | None = None) -> str:
    profile = load_workspace_profile(root, profile_id)
    hostlists = ", ".join(item.path for item in profile.hostlists) or "нет"
    notes = "\n".join(f"  - {note}" for note in profile.notes) or "  - нет"
    return "\n".join(
        [
            f"Workspace profile: {profile.profile_id}",
            f"title: {profile.title}",
            f"strategy: {profile.strategy_id}",
            f"build target: {profile.build_target}",
            f"hostlists: {hostlists}",
            "read-only checks: yes",
            "requires owner confirmation before apply: yes",
            "notes:",
            notes,
        ]
    )


def workspace_strategies_to_text(root: Path | None = None) -> str:
    catalog = load_workspace_catalog(root)
    lines = ["Workspace strategies:"]
    for strategy in catalog.strategies:
        default_marker = " (default)" if strategy.strategy_id == catalog.default_strategy_id else ""
        lines.append(f"  {strategy.strategy_id}{default_marker}: {strategy.title}")
        lines.append(f"    philosophy: {strategy.philosophy}; plan-only: yes")
    return "\n".join(lines)


def workspace_strategy_to_text(strategy_id: str, root: Path | None = None) -> str:
    catalog = load_workspace_catalog(root)
    strategies = catalog.strategy_by_id()
    if strategy_id not in strategies:
        raise ValueError(f"Неизвестная стратегия: {strategy_id}. Доступно: {', '.join(sorted(strategies))}")
    strategy = strategies[strategy_id]
    intended = ", ".join(strategy.intended_for) or "не указано"
    workflow = " -> ".join(strategy.workflow) or "не указан"
    notes = "\n".join(f"  - {note}" for note in strategy.notes) or "  - нет"
    source = strategy.source_preset or {}
    source_name = str(source.get("name", "не указан"))
    source_level = str(source.get("portingLevel", "не указан"))
    runtime_args = "\n".join(f"  - {arg}" for arg in strategy.runtime_args) or "  - нет"
    return "\n".join(
        [
            f"Workspace strategy: {strategy.strategy_id}",
            f"title: {strategy.title}",
            f"summary: {strategy.summary}",
            f"philosophy: {strategy.philosophy}",
            f"intended for: {intended}",
            f"workflow: {workflow}",
            f"source preset: {source_name} ({source_level})",
            "runtime args:",
            runtime_args,
            "executes automatically: no",
            "requires sudo at Stage 7: no",
            "mutates services/firewall at Stage 7: no",
            "notes:",
            notes,
        ]
    )
