"""Модели runtime events и owner confirmations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .lifecycle import RUNTIME_EVENT_LEVELS, RUNTIME_EVENT_TYPES
from .runtime_plan import RuntimeValidationIssue


@dataclass(frozen=True)
class RuntimeEventContract:
    """Контракт будущей записи runtime-журнала."""

    schema_version: int
    event_id: str
    plan_id: str
    event_type: str
    level: str
    message: str
    created_at: str
    metadata: dict[str, Any]
    source_path: Path | None = None


@dataclass(frozen=True)
class ConfirmationContract:
    """Контракт будущего owner confirmation."""

    schema_version: int
    confirmation_id: str
    plan_id: str
    plan_hash: str
    confirmed_by_owner: bool
    expires_when_plan_changes: bool
    allows_automatic_reuse: bool
    notes: tuple[str, ...]
    source_path: Path | None = None

    @property
    def is_safe_example_or_single_use_confirmation(self) -> bool:
        return self.expires_when_plan_changes and not self.allows_automatic_reuse


def parse_runtime_event_contract(data: dict[str, Any], source_path: Path | None = None) -> RuntimeEventContract:
    return RuntimeEventContract(
        schema_version=int(data["schemaVersion"]),
        event_id=str(data["eventId"]),
        plan_id=str(data["planId"]),
        event_type=str(data["eventType"]),
        level=str(data["level"]),
        message=str(data["message"]),
        created_at=str(data["createdAt"]),
        metadata=dict(data.get("metadata", {})),
        source_path=source_path,
    )


def parse_confirmation_contract(data: dict[str, Any], source_path: Path | None = None) -> ConfirmationContract:
    return ConfirmationContract(
        schema_version=int(data["schemaVersion"]),
        confirmation_id=str(data["confirmationId"]),
        plan_id=str(data["planId"]),
        plan_hash=str(data["planHash"]),
        confirmed_by_owner=bool(data["confirmedByOwner"]),
        expires_when_plan_changes=bool(data["expiresWhenPlanChanges"]),
        allows_automatic_reuse=bool(data["allowsAutomaticReuse"]),
        notes=tuple(str(item) for item in data.get("notes", [])),
        source_path=source_path,
    )


def validate_runtime_event_contract(event: RuntimeEventContract) -> tuple[RuntimeValidationIssue, ...]:
    issues: list[RuntimeValidationIssue] = []
    if event.schema_version != 1:
        issues.append(RuntimeValidationIssue("error", "runtime event должен иметь schemaVersion=1"))
    if event.event_type not in RUNTIME_EVENT_TYPES:
        issues.append(RuntimeValidationIssue("error", f"неизвестный eventType: {event.event_type}"))
    if event.level not in RUNTIME_EVENT_LEVELS:
        issues.append(RuntimeValidationIssue("error", f"неизвестный level: {event.level}"))
    if not event.message:
        issues.append(RuntimeValidationIssue("error", "runtime event должен иметь message"))
    return tuple(issues)


def validate_confirmation_contract(confirmation: ConfirmationContract) -> tuple[RuntimeValidationIssue, ...]:
    issues: list[RuntimeValidationIssue] = []
    if confirmation.schema_version != 1:
        issues.append(RuntimeValidationIssue("error", "confirmation должен иметь schemaVersion=1"))
    if not confirmation.is_safe_example_or_single_use_confirmation:
        issues.append(RuntimeValidationIssue("error", "confirmation не должен переиспользоваться автоматически"))
    if confirmation.confirmed_by_owner:
        issues.append(RuntimeValidationIssue("warning", "пример Stage 8 не должен быть настоящим подтверждением"))
    if len(confirmation.plan_hash) < 12:
        issues.append(RuntimeValidationIssue("error", "confirmation должен быть связан с plan hash"))
    return tuple(issues)
