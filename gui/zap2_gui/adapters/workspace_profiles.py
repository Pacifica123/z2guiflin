"""Read-only adapter для workspace-профилей и стратегий.

Stage 7 делает стратегии и профили видимыми данными проекта. Adapter ничего не
применяет к системе: он только читает JSON, валидирует связи и готовит текстовое
представление для CLI/GUI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .local_build import supported_build_targets
from ..models.strategy import StrategyCapabilities, WorkspaceStrategy
from ..models.preset import parse_preset_args
from ..models.workspace_profile import HostlistRef, WorkspaceProfile, WorkspaceRuntimeContext, WorkspaceSafety
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
    active_selection: "ActiveStrategySelection | None" = None

    def profile_by_id(self) -> dict[str, WorkspaceProfile]:
        return {profile.profile_id: profile for profile in self.profiles}

    def strategy_by_id(self) -> dict[str, WorkspaceStrategy]:
        return {strategy.strategy_id: strategy for strategy in self.strategies}

    def runtime_context_by_id(self) -> dict[str, WorkspaceProfile]:
        return self.profile_by_id()

    def preset_by_id(self) -> dict[str, WorkspaceStrategy]:
        return self.strategy_by_id()


ACTIVE_STRATEGY_SELECTION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ActiveStrategySelection:
    """Owner-selected strategy override stored in .zap2 state."""

    schema_version: int
    profile_id: str
    strategy_id: str
    selected_at: str
    reason: str
    path: Path
    previous_strategy_id: str | None = None

    @property
    def runtime_context_id(self) -> str:
        return self.profile_id

    @property
    def preset_id(self) -> str:
        return self.strategy_id

    @property
    def previous_preset_id(self) -> str | None:
        return self.previous_strategy_id

    def to_text(self) -> str:
        previous = self.previous_strategy_id or "не указан"
        return "\n".join(
            [
                "Active strategy selection",
                f"profile: {self.profile_id}",
                f"strategy: {self.strategy_id}",
                f"previous strategy: {previous}",
                f"selected at: {self.selected_at}",
                f"reason: {self.reason}",
                f"selection file: {self.path}",
                "read-only in checks: yes",
            ]
        )


@dataclass(frozen=True)
class StrategySelectionResult:
    """Result of an explicit owner strategy selection."""

    profile_id: str
    strategy_id: str
    previous_strategy_id: str
    path: Path
    selected_at: str

    @property
    def runtime_context_id(self) -> str:
        return self.profile_id

    @property
    def preset_id(self) -> str:
        return self.strategy_id

    @property
    def previous_preset_id(self) -> str:
        return self.previous_strategy_id

    def to_text(self) -> str:
        return "\n".join(
            [
                "Strategy selection: saved",
                f"profile: {self.profile_id}",
                f"strategy: {self.strategy_id}",
                f"previous strategy: {self.previous_strategy_id}",
                f"selection file: {self.path}",
                f"selected at: {self.selected_at}",
                "effect: next default build/start/stop/status plans use selected strategy",
                "executes now: no",
                "mutates services/firewall now: no",
            ]
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _compat_value(data: dict[str, Any], canonical: str, legacy: str, *, required: bool = True) -> str:
    canonical_value = str(data.get(canonical) or "").strip()
    legacy_value = str(data.get(legacy) or "").strip()
    if canonical_value and legacy_value and canonical_value != legacy_value:
        raise ValueError(f"Conflicting compatibility fields: {canonical}={canonical_value!r} != {legacy}={legacy_value!r}")
    value = canonical_value or legacy_value
    if required and not value:
        raise ValueError(f"Missing required field: {canonical} (legacy alias: {legacy})")
    return value


def active_strategy_selection_path(root: Path | None = None, profile_id: str = "default") -> Path:
    layout = discover_layout(root)
    safe_profile = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in profile_id)
    return layout.root / ".zap2" / "strategies" / f"{safe_profile}.active-strategy.json"


def load_active_strategy_selection(root: Path | None = None, profile_id: str = "default") -> ActiveStrategySelection | None:
    path = active_strategy_selection_path(root, profile_id)
    if not path.is_file():
        return None
    data = _read_json(path)
    if int(data.get("schemaVersion", 0)) != ACTIVE_STRATEGY_SELECTION_SCHEMA_VERSION:
        return None
    stored_context_id = _compat_value(data, "runtimeContextId", "profileId")
    if stored_context_id != profile_id:
        return None
    previous_preset_id = _compat_value(data, "previousPresetId", "previousStrategyId", required=False) or None
    return ActiveStrategySelection(
        schema_version=int(data["schemaVersion"]),
        profile_id=stored_context_id,
        strategy_id=_compat_value(data, "presetId", "strategyId"),
        selected_at=str(data.get("selectedAt", "")),
        reason=str(data.get("reason", "owner-selected")),
        previous_strategy_id=previous_preset_id,
        path=path,
    )


def select_workspace_strategy(
    root: Path | None = None,
    strategy_id: str = "",
    profile_id: str = "default",
    reason: str = "owner-selected",
) -> StrategySelectionResult:
    """Persist owner-selected strategy for a profile without starting anything."""

    if not strategy_id:
        raise ValueError("strategy_id обязателен для выбора стратегии")
    layout = discover_layout(root)
    profiles = {profile.profile_id: profile for profile in load_workspace_profiles(layout.root)}
    if profile_id not in profiles:
        raise ValueError(f"Неизвестный workspace-профиль: {profile_id}")
    strategies = load_strategy_catalog(layout.root).by_id()
    if strategy_id not in strategies:
        raise ValueError(f"Неизвестная стратегия: {strategy_id}. Доступно: {', '.join(sorted(strategies))}")
    previous = load_active_strategy_selection(layout.root, profile_id)
    previous_strategy_id = previous.strategy_id if previous is not None else profiles[profile_id].strategy_id
    path = active_strategy_selection_path(layout.root, profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    selected_at = _utc_now()
    payload = {
        "schemaVersion": ACTIVE_STRATEGY_SELECTION_SCHEMA_VERSION,
        "runtimeContextId": profile_id,
        "presetId": strategy_id,
        "previousPresetId": previous_strategy_id,
        "profileId": profile_id,
        "strategyId": strategy_id,
        "previousStrategyId": previous_strategy_id,
        "selectedAt": selected_at,
        "reason": reason,
        "safety": {
            "executesNow": False,
            "mutatesServicesOrFirewallNow": False,
            "automaticChecksMayExecute": False,
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return StrategySelectionResult(
        profile_id=profile_id,
        strategy_id=strategy_id,
        previous_strategy_id=previous_strategy_id,
        path=path,
        selected_at=selected_at,
    )


def _apply_active_selection(
    root: Path,
    profiles: tuple[WorkspaceProfile, ...],
    strategies: dict[str, WorkspaceStrategy],
    default_profile_id: str,
) -> tuple[tuple[WorkspaceProfile, ...], ActiveStrategySelection | None, str]:
    selection = load_active_strategy_selection(root, default_profile_id)
    if selection is None:
        return profiles, None, ""
    if selection.strategy_id not in strategies:
        return profiles, None, ""
    updated = tuple(
        replace(profile, strategy_id=selection.strategy_id)
        if profile.profile_id == selection.profile_id
        else profile
        for profile in profiles
    )
    return updated, selection, selection.strategy_id


@dataclass(frozen=True)
class ProfileValidationIssue:
    severity: str
    message: str


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_schema(data: dict[str, Any], path: Path) -> None:
    if int(data.get("schemaVersion", 0)) != 1:
        raise ValueError(f"Неподдерживаемая schemaVersion в {path}")


def _parse_strategy(path: Path, root: Path) -> WorkspaceStrategy:
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
    legacy_runtime_args = tuple(str(item) for item in data.get("runtimeArgs", []))
    preset_path = str(data.get("presetPath") or "").strip()
    runtime_args = legacy_runtime_args
    compatibility_warnings: list[str] = []
    if preset_path:
        resolved = (root / preset_path).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"presetPath выходит за пределы workspace: {preset_path}") from exc
        if not resolved.is_file():
            raise ValueError(f"Файл пресета не найден: {preset_path}")
        preset_args = tuple(
            line.strip()
            for line in resolved.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        parsed = parse_preset_args(
            preset_args,
            preset_id=str(data["id"]),
            title=str(data["title"]),
            source_path=preset_path,
        )
        runtime_args = parsed.to_runtime_args()
        if legacy_runtime_args and runtime_args != legacy_runtime_args:
            compatibility_warnings.append(
                f"legacy runtimeArgs drift ignored for {data['id']}; presetPath is execution authority"
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
        runtime_args=runtime_args,
        preset_path=preset_path,
        source_preset=dict(data["sourcePreset"]) if isinstance(data.get("sourcePreset"), dict) else None,
        service_target=dict(data["serviceTarget"]) if isinstance(data.get("serviceTarget"), dict) else None,
        capture_policy=dict(data["capturePolicy"]) if isinstance(data.get("capturePolicy"), dict) else None,
        diagnostic_hints=dict(data["diagnosticHints"]) if isinstance(data.get("diagnosticHints"), dict) else None,
        compatibility_warnings=tuple(compatibility_warnings),
    )


def _strategy_diagnostic_hints_to_lines(strategy: WorkspaceStrategy) -> list[str]:
    hints = strategy.diagnostic_hints
    if not hints:
        return []
    lines = ["diagnostic hints:"]
    observed_url = str(hints.get("observedDiscordUrl") or "").strip()
    observed_host = str(hints.get("observedDiscordHost") or "").strip()
    hostlist_required = [str(item) for item in hints.get("hostlistMustInclude", []) if str(item).strip()]
    phase_ladder = [str(item) for item in hints.get("phaseLadder", []) if str(item).strip()]
    owner_result = [str(item) for item in hints.get("ownerObservedV2Result", []) if str(item).strip()]
    owner_result_v2b = [str(item) for item in hints.get("ownerObservedV2bResult", []) if str(item).strip()]
    matrix_variant = str(hints.get("matrixVariant") or "").strip()
    manual_checks = [str(item) for item in hints.get("recommendedManualChecks", []) if str(item).strip()]
    args_text = "\n".join(strategy.runtime_args)
    hostlist_ok = all(host in args_text for host in hostlist_required) if hostlist_required else False
    if observed_url:
        lines.append(f"  observed Discord URL: {observed_url}")
    if observed_host:
        lines.append(f"  observed Discord host: {observed_host}")
    if hostlist_required:
        lines.append(f"  required hostlist hosts: {', '.join(hostlist_required)}")
        lines.append(f"  required hosts present in runtime args: {'yes' if hostlist_ok else 'no'}")
    if phase_ladder:
        lines.append(f"  phase ladder: {' -> '.join(phase_ladder)}")
    if matrix_variant:
        lines.append(f"  matrix variant: {matrix_variant}")
    for item in owner_result:
        lines.append(f"  owner observed v2 result: {item}")
    for item in owner_result_v2b:
        lines.append(f"  owner observed v2b result: {item}")
    for item in manual_checks:
        lines.append(f"  manual check: {item}")
    return lines


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
        profile_id=_compat_value(data, "runtimeContextId", "id"),
        title=str(data["title"]),
        description=str(data["description"]),
        strategy_id=_compat_value(data, "presetId", "strategyId"),
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
    strategies = tuple(_parse_strategy(layout.root / rel_path, layout.root) for rel_path in catalog_data["strategyFiles"])
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


def load_runtime_context(root: Path | None = None, runtime_context_id: str = "default") -> WorkspaceProfile:
    """Canonical P04 alias for ``load_workspace_profile``."""

    return load_workspace_profile(root, runtime_context_id)


def select_workspace_preset(
    root: Path | None = None,
    preset_id: str = "",
    runtime_context_id: str = "default",
    reason: str = "owner-selected",
) -> StrategySelectionResult:
    """Canonical P04 alias; storage keeps legacy fields for compatibility."""

    return select_workspace_strategy(root, preset_id, runtime_context_id, reason)


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
        for warning in strategy.compatibility_warnings:
            issues.append(ProfileValidationIssue("warning", warning))

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
    active_profiles, active_selection, active_default_strategy_id = _apply_active_selection(
        layout.root,
        profiles,
        strategy_catalog.by_id(),
        default_profile_id,
    )
    return WorkspaceCatalog(
        profiles=active_profiles,
        strategies=strategy_catalog.strategies,
        default_profile_id=default_profile_id,
        default_strategy_id=active_default_strategy_id or strategy_catalog.default_strategy_id,
        active_selection=active_selection,
    )


def workspace_profiles_to_text(root: Path | None = None) -> str:
    catalog = load_workspace_catalog(root)
    lines = ["Workspace profiles:"]
    for profile in catalog.profiles:
        default_marker = " (default)" if profile.profile_id == catalog.default_profile_id else ""
        active_marker = " [active selected]" if catalog.active_selection and catalog.active_selection.profile_id == profile.profile_id else ""
        lines.append(f"  {profile.profile_id}{default_marker}: {profile.title}{active_marker}")
        lines.append(f"    strategy: {profile.strategy_id}; build target: {profile.build_target}")
        lines.append(f"    hostlists: {len(profile.hostlists)}; read-only checks: yes")
    return "\n".join(lines)


def workspace_profile_to_text(profile_id: str = "default", root: Path | None = None) -> str:
    catalog = load_workspace_catalog(root)
    profiles = catalog.profile_by_id()
    if profile_id not in profiles:
        raise ValueError(f"Неизвестный workspace-профиль: {profile_id}. Доступно: {', '.join(sorted(profiles))}")
    profile = profiles[profile_id]
    hostlists = ", ".join(item.path for item in profile.hostlists) or "нет"
    notes = "\n".join(f"  - {note}" for note in profile.notes) or "  - нет"
    active_line = (
        f"active selection file: {catalog.active_selection.path}"
        if catalog.active_selection and catalog.active_selection.profile_id == profile.profile_id
        else "active selection file: нет"
    )
    return "\n".join(
        [
            f"Workspace profile: {profile.profile_id}",
            f"title: {profile.title}",
            f"strategy: {profile.strategy_id}",
            active_line,
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
    active_id = catalog.active_selection.strategy_id if catalog.active_selection else ""
    lines = ["Workspace strategies:"]
    for strategy in catalog.strategies:
        default_marker = " (default)" if strategy.strategy_id == catalog.default_strategy_id else ""
        active_marker = " [selected for Default]" if strategy.strategy_id == active_id else ""
        lines.append(f"  {strategy.strategy_id}{default_marker}{active_marker}: {strategy.title}")
        lines.append(f"    service target: {strategy.service_target_label}")
        if strategy.service_target and isinstance(strategy.service_target.get("coverage"), dict):
            lines.append(f"    {strategy.service_target_coverage_label}")
        lines.append(f"    {strategy.capture_policy_label}")
        lines.append(f"    philosophy: {strategy.philosophy}; plan-only: yes; runtime args: {len(strategy.runtime_args)}")
    if catalog.active_selection:
        lines.append(f"active selection file: {catalog.active_selection.path}")
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
    lines = [
            f"Workspace strategy: {strategy.strategy_id}",
            f"title: {strategy.title}",
            f"summary: {strategy.summary}",
            f"service target: {strategy.service_target_label}",
            strategy.service_target_coverage_label,
            strategy.capture_policy_label,
            f"philosophy: {strategy.philosophy}",
            f"intended for: {intended}",
            f"workflow: {workflow}",
            f"source preset: {source_name} ({source_level})",
            "runtime args:",
            runtime_args,
        ]
    diagnostic_lines = _strategy_diagnostic_hints_to_lines(strategy)
    if diagnostic_lines:
        lines.extend(diagnostic_lines)
    lines.extend(
        [
            "executes automatically: no",
            "requires sudo at Stage 7: no",
            "mutates services/firewall at Stage 7: no",
            "notes:",
            notes,
        ]
    )
    return "\n".join(lines)
