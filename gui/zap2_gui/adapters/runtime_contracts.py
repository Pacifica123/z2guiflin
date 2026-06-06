"""Read-only adapter для runtime lifecycle contracts Stage 8."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models.lifecycle import PLAN_SECTION_KINDS, default_lifecycle_boundary
from ..models.runtime_events import (
    ConfirmationContract,
    RuntimeEventContract,
    parse_confirmation_contract,
    parse_runtime_event_contract,
    validate_confirmation_contract,
    validate_runtime_event_contract,
)
from ..models.runtime_plan import (
    RuntimePlanContract,
    RuntimeValidationIssue,
    parse_runtime_plan_contract,
    validate_runtime_plan_contract,
)
from ..project_paths import discover_layout


@dataclass(frozen=True)
class RuntimeContractCatalog:
    """Сводка схем и примеров runtime contracts."""

    schemas: dict[str, Path]
    plan_contracts: tuple[RuntimePlanContract, ...]
    event_contracts: tuple[RuntimeEventContract, ...]
    confirmation_contracts: tuple[ConfirmationContract, ...]

    @property
    def plan_count(self) -> int:
        return len(self.plan_contracts)

    @property
    def event_count(self) -> int:
        return len(self.event_contracts)

    @property
    def confirmation_count(self) -> int:
        return len(self.confirmation_contracts)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_paths(root: Path | None = None) -> dict[str, Path]:
    layout = discover_layout(root)
    schemas_dir = layout.runtime_dir / "schemas"
    return {
        "runtime-plan": schemas_dir / "runtime-plan.schema.json",
        "runtime-event": schemas_dir / "runtime-event.schema.json",
        "confirmation": schemas_dir / "confirmation.schema.json",
    }


def _validate_schema_files(root: Path | None = None) -> tuple[RuntimeValidationIssue, ...]:
    issues: list[RuntimeValidationIssue] = []
    for name, path in _schema_paths(root).items():
        if not path.exists():
            issues.append(RuntimeValidationIssue("error", f"schema отсутствует: {name}"))
            continue
        data = _read_json(path)
        if data.get("type") != "object":
            issues.append(RuntimeValidationIssue("error", f"schema {name} должен описывать object"))
        if not data.get("required"):
            issues.append(RuntimeValidationIssue("error", f"schema {name} должен иметь required-поля"))
    return tuple(issues)


def load_runtime_contract_catalog(root: Path | None = None) -> RuntimeContractCatalog:
    """Загружает схемы и example-contracts без исполнения."""

    layout = discover_layout(root)
    examples_dir = layout.runtime_dir / "examples"
    plan_contracts = tuple(
        parse_runtime_plan_contract(_read_json(path), path)
        for path in sorted(examples_dir.glob("*.contract.json"))
    )
    event_contracts = tuple(
        parse_runtime_event_contract(_read_json(path), path)
        for path in sorted(examples_dir.glob("*.event.json"))
    )
    confirmation_contracts = tuple(
        parse_confirmation_contract(_read_json(path), path)
        for path in sorted(examples_dir.glob("*.confirmation.json"))
    )
    return RuntimeContractCatalog(
        schemas=_schema_paths(layout.root),
        plan_contracts=plan_contracts,
        event_contracts=event_contracts,
        confirmation_contracts=confirmation_contracts,
    )


def validate_runtime_contract_catalog(root: Path | None = None) -> tuple[RuntimeValidationIssue, ...]:
    """Проверяет runtime contracts и Stage 8 boundary."""

    layout = discover_layout(root)
    issues: list[RuntimeValidationIssue] = list(_validate_schema_files(layout.root))
    boundary = default_lifecycle_boundary()
    if not boundary.is_stage8_plan_only:
        issues.append(RuntimeValidationIssue("error", "LifecycleBoundary Stage 8 должен оставаться plan-only"))

    catalog = load_runtime_contract_catalog(layout.root)
    if not catalog.plan_contracts:
        issues.append(RuntimeValidationIssue("error", "runtime/examples должен иметь хотя бы один plan contract"))
    if not catalog.event_contracts:
        issues.append(RuntimeValidationIssue("error", "runtime/examples должен иметь хотя бы один runtime event"))
    if not catalog.confirmation_contracts:
        issues.append(RuntimeValidationIssue("error", "runtime/examples должен иметь хотя бы один confirmation contract"))

    plan_ids = {plan.plan_id for plan in catalog.plan_contracts}
    for plan in catalog.plan_contracts:
        issues.extend(validate_runtime_plan_contract(plan))
        if tuple(sorted(set(plan.section_kinds))) != tuple(sorted(PLAN_SECTION_KINDS)):
            issues.append(RuntimeValidationIssue("error", f"plan {plan.plan_id} должен покрывать run/apply/session/service"))
    for event in catalog.event_contracts:
        issues.extend(validate_runtime_event_contract(event))
        if event.plan_id not in plan_ids:
            issues.append(RuntimeValidationIssue("error", f"event {event.event_id} ссылается на неизвестный planId"))
    for confirmation in catalog.confirmation_contracts:
        issues.extend(validate_confirmation_contract(confirmation))
        if confirmation.plan_id not in plan_ids:
            issues.append(RuntimeValidationIssue("error", f"confirmation {confirmation.confirmation_id} ссылается на неизвестный planId"))
    return tuple(issues)


def runtime_contracts_to_text(root: Path | None = None) -> str:
    catalog = load_runtime_contract_catalog(root)
    lines = ["Runtime lifecycle contracts:"]
    lines.append(f"  schemas: {', '.join(sorted(catalog.schemas))}")
    lines.append(f"  plan contracts: {catalog.plan_count}")
    for plan in catalog.plan_contracts:
        lines.append(f"    {plan.plan_id}: {plan.action}; sections={', '.join(plan.section_kinds)}")
    lines.append(f"  runtime events: {catalog.event_count}")
    lines.append(f"  confirmations: {catalog.confirmation_count}")
    lines.append("  automatic checks may execute plans: no")
    lines.append("  bootstrap mixed in: no")
    return "\n".join(lines)


def validate_runtime_contracts_to_text(root: Path | None = None) -> str:
    issues = validate_runtime_contract_catalog(root)
    errors = [issue.message for issue in issues if issue.severity == "error"]
    warnings = [issue.message for issue in issues if issue.severity == "warning"]
    if errors:
        return "Runtime lifecycle contracts: FAILED\n" + "\n".join(f"  - {message}" for message in errors)
    lines = ["Runtime lifecycle contracts: OK"]
    for warning in warnings:
        lines.append(f"  warning: {warning}")
    lines.append("  validated schemas, plan contracts, runtime events and confirmation contracts")
    lines.append("  execution: disabled in Stage 8")
    return "\n".join(lines)
