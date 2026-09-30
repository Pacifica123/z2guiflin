"""Модели runtime plan contracts.

Этот модуль не исполняет планы. Он только переводит JSON-контракты в typed
модели и проверяет safety-инварианты Stage 8.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .lifecycle import PLAN_SECTION_KINDS, RUNTIME_ACTIONS, RUNTIME_CONTRACT_STAGE


@dataclass(frozen=True)
class RuntimePlanSafety:
    """Safety-флаги runtime plan."""

    requires_owner_confirmation: bool
    may_require_sudo_when_executed_by_owner: bool
    may_mutate_firewall_when_executed_by_owner: bool
    may_manage_service_when_executed_by_owner: bool
    contains_remote_bootstrap: bool
    contains_upstream_installer_script: bool

    @property
    def blocks_hidden_execution(self) -> bool:
        return (
            self.requires_owner_confirmation
            and not self.contains_remote_bootstrap
            and not self.contains_upstream_installer_script
        )


@dataclass(frozen=True)
class RuntimePlanLifecycle:
    """Lifecycle metadata для контракта."""

    contract_stage: str
    bootstrap_mixed_in: bool
    automatic_checks_may_execute: bool

    @property
    def is_contract_only(self) -> bool:
        return (
            self.contract_stage == RUNTIME_CONTRACT_STAGE
            and not self.bootstrap_mixed_in
            and not self.automatic_checks_may_execute
        )


@dataclass(frozen=True)
class RuntimePlanCommandPreview:
    """Будущая команда как данные, а не как исполнение."""

    label: str
    cwd: str
    argv: tuple[str, ...]
    requires_sudo: bool
    mutates_system: bool
    description: str


@dataclass(frozen=True)
class RuntimePlanStep:
    """Один шаг внутри run/apply/session/service секции."""

    step_id: str
    title: str
    description: str
    requires_owner_confirmation: bool
    commands: tuple[RuntimePlanCommandPreview, ...]


@dataclass(frozen=True)
class RuntimePlanSection:
    """Секция runtime lifecycle: run/apply/session/service."""

    kind: str
    purpose: str
    steps: tuple[RuntimePlanStep, ...]


@dataclass(frozen=True)
class RuntimePlanContract:
    """Полный contract будущего runtime plan."""

    schema_version: int
    plan_id: str
    title: str
    profile_id: str
    strategy_id: str
    action: str
    lifecycle: RuntimePlanLifecycle
    safety: RuntimePlanSafety
    sections: tuple[RuntimePlanSection, ...]
    rollback_notes: tuple[str, ...]
    source_path: Path | None = None

    @property
    def runtime_context_id(self) -> str:
        return self.profile_id

    @property
    def preset_id(self) -> str:
        return self.strategy_id

    @property
    def section_kinds(self) -> tuple[str, ...]:
        return tuple(section.kind for section in self.sections)

    @property
    def is_stage8_contract_only(self) -> bool:
        return self.lifecycle.is_contract_only and self.safety.blocks_hidden_execution

    def to_summary_lines(self) -> tuple[str, ...]:
        section_summary = ", ".join(self.section_kinds)
        return (
            f"Runtime contract: {self.plan_id}",
            f"title: {self.title}",
            f"profile: {self.profile_id}; strategy: {self.strategy_id}; action: {self.action}",
            f"sections: {section_summary}",
            "automatic checks may execute: no",
            "bootstrap mixed in: no",
            "requires owner confirmation: yes",
            f"rollback notes: {len(self.rollback_notes)}",
        )

    def to_text(self) -> str:
        return "\n".join(self.to_summary_lines())


@dataclass(frozen=True)
class RuntimeValidationIssue:
    """Результат валидации runtime contract."""

    severity: str
    message: str


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} должен быть object")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} должен быть array")
    return value


def _parse_command(data: dict[str, Any]) -> RuntimePlanCommandPreview:
    return RuntimePlanCommandPreview(
        label=str(data.get("label", "")),
        cwd=str(data.get("cwd", "")),
        argv=tuple(str(item) for item in data.get("argv", [])),
        requires_sudo=bool(data.get("requiresSudo", False)),
        mutates_system=bool(data.get("mutatesSystem", False)),
        description=str(data.get("description", "")),
    )


def _parse_step(data: dict[str, Any]) -> RuntimePlanStep:
    commands = tuple(_parse_command(_require_mapping(item, "command")) for item in data.get("commands", []))
    return RuntimePlanStep(
        step_id=str(data["stepId"]),
        title=str(data["title"]),
        description=str(data["description"]),
        requires_owner_confirmation=bool(data["requiresOwnerConfirmation"]),
        commands=commands,
    )


def parse_runtime_plan_contract(data: dict[str, Any], source_path: Path | None = None) -> RuntimePlanContract:
    """Парсит runtime plan contract из JSON-like object."""

    lifecycle_data = _require_mapping(data["lifecycle"], "lifecycle")
    safety_data = _require_mapping(data["safety"], "safety")
    sections_data = _require_list(data["sections"], "sections")
    rollback_notes = tuple(str(item) for item in _require_list(data["rollbackNotes"], "rollbackNotes"))

    sections = tuple(
        RuntimePlanSection(
            kind=str(section["kind"]),
            purpose=str(section["purpose"]),
            steps=tuple(_parse_step(_require_mapping(item, "step")) for item in section.get("steps", [])),
        )
        for section in sections_data
    )
    return RuntimePlanContract(
        schema_version=int(data["schemaVersion"]),
        plan_id=str(data["planId"]),
        title=str(data["title"]),
        profile_id=str(data["profileId"]),
        strategy_id=str(data["strategyId"]),
        action=str(data["action"]),
        lifecycle=RuntimePlanLifecycle(
            contract_stage=str(lifecycle_data["contractStage"]),
            bootstrap_mixed_in=bool(lifecycle_data["bootstrapMixedIn"]),
            automatic_checks_may_execute=bool(lifecycle_data["automaticChecksMayExecute"]),
        ),
        safety=RuntimePlanSafety(
            requires_owner_confirmation=bool(safety_data["requiresOwnerConfirmation"]),
            may_require_sudo_when_executed_by_owner=bool(safety_data["mayRequireSudoWhenExecutedByOwner"]),
            may_mutate_firewall_when_executed_by_owner=bool(safety_data["mayMutateFirewallWhenExecutedByOwner"]),
            may_manage_service_when_executed_by_owner=bool(safety_data["mayManageServiceWhenExecutedByOwner"]),
            contains_remote_bootstrap=bool(safety_data["containsRemoteBootstrap"]),
            contains_upstream_installer_script=bool(safety_data["containsUpstreamInstallerScript"]),
        ),
        sections=sections,
        rollback_notes=rollback_notes,
        source_path=source_path,
    )


def validate_runtime_plan_contract(contract: RuntimePlanContract) -> tuple[RuntimeValidationIssue, ...]:
    """Проверяет инварианты Stage 8 для runtime plan contract."""

    issues: list[RuntimeValidationIssue] = []
    if contract.schema_version != 1:
        issues.append(RuntimeValidationIssue("error", "runtime plan должен иметь schemaVersion=1"))
    if contract.action not in RUNTIME_ACTIONS:
        issues.append(RuntimeValidationIssue("error", f"неизвестное runtime action: {contract.action}"))
    if not contract.lifecycle.is_contract_only:
        issues.append(RuntimeValidationIssue("error", "Stage 8 contract должен быть plan-only и не смешиваться с bootstrap"))
    if not contract.safety.blocks_hidden_execution:
        issues.append(RuntimeValidationIssue("error", "runtime plan требует owner confirmation и запрещает bootstrap/install scripts"))
    section_kinds = set(contract.section_kinds)
    missing = [kind for kind in PLAN_SECTION_KINDS if kind not in section_kinds]
    if missing:
        issues.append(RuntimeValidationIssue("error", f"runtime plan не содержит секции: {', '.join(missing)}"))
    for section in contract.sections:
        if section.kind not in PLAN_SECTION_KINDS:
            issues.append(RuntimeValidationIssue("error", f"неизвестная секция runtime plan: {section.kind}"))
        if not section.steps:
            issues.append(RuntimeValidationIssue("error", f"секция {section.kind} не содержит steps"))
        for step in section.steps:
            for command in step.commands:
                argv_text = " ".join(command.argv).lower()
                if "install_easy" in argv_text or "curl" in argv_text or "wget" in argv_text:
                    issues.append(RuntimeValidationIssue("error", f"шаг {step.step_id} содержит bootstrap-подобную команду"))
    if not contract.rollback_notes:
        issues.append(RuntimeValidationIssue("error", "runtime plan должен иметь rollbackNotes"))
    return tuple(issues)
