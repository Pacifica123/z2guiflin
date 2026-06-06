"""Runtime state, logs и confirmation gate для Stage 10.

Этот adapter создаёт и ведёт только локальное состояние workspace в `.zap2/runtime`.
Он не запускает процессы, не вызывает sudo, не меняет firewall/service state и не
исполняет runtime plans. Его задача — подготовить проверяемый след: saved plan,
plan hash, confirmation record, rollback notes и append-only log.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runtime_plan_generator import GeneratedRuntimePlan, create_runtime_plan
from ..models.runtime_plan import (
    RuntimePlanCommandPreview,
    RuntimePlanContract,
    RuntimePlanLifecycle,
    RuntimePlanSafety,
    RuntimePlanSection,
    RuntimePlanStep,
)
from ..project_paths import discover_layout

RUNTIME_STATE_SCHEMA_VERSION = 1
RUNTIME_STATE_STAGE = "v0.3-alpha_stage_10"
RUNTIME_STATE_DIRNAME = ".zap2"
RUNTIME_SUBDIRS = ("plans", "confirmations", "sessions", "logs", "rollback", "session-inputs")


@dataclass(frozen=True)
class RuntimeStorePaths:
    """Пути локального runtime state внутри workspace."""

    root: Path
    store_root: Path
    runtime_root: Path
    plans_dir: Path
    confirmations_dir: Path
    sessions_dir: Path
    logs_dir: Path
    rollback_dir: Path
    session_inputs_dir: Path

    @property
    def required_dirs(self) -> tuple[Path, ...]:
        return (
            self.store_root,
            self.runtime_root,
            self.plans_dir,
            self.confirmations_dir,
            self.sessions_dir,
            self.logs_dir,
            self.rollback_dir,
            self.session_inputs_dir,
        )

    def as_text_lines(self) -> tuple[str, ...]:
        return (
            f"workspace runtime root: {self.runtime_root}",
            f"plans: {self.plans_dir}",
            f"confirmations: {self.confirmations_dir}",
            f"sessions: {self.sessions_dir}",
            f"logs: {self.logs_dir}",
            f"rollback: {self.rollback_dir}",
            f"session inputs: {self.session_inputs_dir}",
        )


@dataclass(frozen=True)
class PreparedRuntimePlan:
    """Сохранённый plan-only runtime plan."""

    plan_id: str
    plan_hash: str
    action: str
    profile_id: str
    strategy_id: str
    plan_path: Path
    rollback_path: Path
    log_path: Path

    def to_text(self) -> str:
        return "\n".join(
            [
                f"Prepared runtime plan: {self.plan_id}",
                f"plan hash: {self.plan_hash}",
                f"action: {self.action}",
                f"profile: {self.profile_id}",
                f"strategy: {self.strategy_id}",
                f"plan file: {self.plan_path}",
                f"rollback notes: {self.rollback_path}",
                f"runtime log: {self.log_path}",
                "confirmation required: yes",
                "executes now: no",
                "mutates services/firewall now: no",
            ]
        )


@dataclass(frozen=True)
class RuntimeConfirmationRecord:
    """Owner confirmation, привязанный к конкретному plan hash."""

    confirmation_id: str
    plan_id: str
    plan_hash: str
    confirmation_path: Path
    log_path: Path

    def to_text(self) -> str:
        return "\n".join(
            [
                f"Runtime confirmation: {self.confirmation_id}",
                f"plan id: {self.plan_id}",
                f"plan hash: {self.plan_hash}",
                f"confirmation file: {self.confirmation_path}",
                f"runtime log: {self.log_path}",
                "expires when plan changes: yes",
                "allows automatic reuse: no",
                "executes now: no",
            ]
        )


def runtime_store_paths(root: Path | None = None) -> RuntimeStorePaths:
    """Возвращает пути `.zap2/runtime` для текущего workspace."""

    layout = discover_layout(root)
    store_root = layout.root / RUNTIME_STATE_DIRNAME
    runtime_root = store_root / "runtime"
    return RuntimeStorePaths(
        root=layout.root,
        store_root=store_root,
        runtime_root=runtime_root,
        plans_dir=runtime_root / "plans",
        confirmations_dir=runtime_root / "confirmations",
        sessions_dir=runtime_root / "sessions",
        logs_dir=runtime_root / "logs",
        rollback_dir=runtime_root / "rollback",
        session_inputs_dir=runtime_root / "session-inputs",
    )


def ensure_runtime_store(root: Path | None = None) -> RuntimeStorePaths:
    """Создаёт только локальные workspace-директории runtime state."""

    paths = runtime_store_paths(root)
    for directory in paths.required_dirs:
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _command_to_dict(command: RuntimePlanCommandPreview) -> dict[str, Any]:
    return {
        "label": command.label,
        "cwd": command.cwd,
        "argv": list(command.argv),
        "requiresSudo": command.requires_sudo,
        "mutatesSystem": command.mutates_system,
        "description": command.description,
    }


def _step_to_dict(step: RuntimePlanStep) -> dict[str, Any]:
    return {
        "stepId": step.step_id,
        "title": step.title,
        "description": step.description,
        "requiresOwnerConfirmation": step.requires_owner_confirmation,
        "commands": [_command_to_dict(command) for command in step.commands],
    }


def _section_to_dict(section: RuntimePlanSection) -> dict[str, Any]:
    return {
        "kind": section.kind,
        "purpose": section.purpose,
        "steps": [_step_to_dict(step) for step in section.steps],
    }


def _lifecycle_to_dict(lifecycle: RuntimePlanLifecycle) -> dict[str, Any]:
    return {
        "contractStage": lifecycle.contract_stage,
        "bootstrapMixedIn": lifecycle.bootstrap_mixed_in,
        "automaticChecksMayExecute": lifecycle.automatic_checks_may_execute,
    }


def _safety_to_dict(safety: RuntimePlanSafety) -> dict[str, Any]:
    return {
        "requiresOwnerConfirmation": safety.requires_owner_confirmation,
        "mayRequireSudoWhenExecutedByOwner": safety.may_require_sudo_when_executed_by_owner,
        "mayMutateFirewallWhenExecutedByOwner": safety.may_mutate_firewall_when_executed_by_owner,
        "mayManageServiceWhenExecutedByOwner": safety.may_manage_service_when_executed_by_owner,
        "containsRemoteBootstrap": safety.contains_remote_bootstrap,
        "containsUpstreamInstallerScript": safety.contains_upstream_installer_script,
    }


def runtime_plan_contract_to_dict(contract: RuntimePlanContract) -> dict[str, Any]:
    """Сериализует RuntimePlanContract в стабильный JSON-compatible object."""

    return {
        "schemaVersion": contract.schema_version,
        "planId": contract.plan_id,
        "title": contract.title,
        "profileId": contract.profile_id,
        "strategyId": contract.strategy_id,
        "action": contract.action,
        "lifecycle": _lifecycle_to_dict(contract.lifecycle),
        "safety": _safety_to_dict(contract.safety),
        "sections": [_section_to_dict(section) for section in contract.sections],
        "rollbackNotes": list(contract.rollback_notes),
    }


def generated_runtime_plan_to_payload(plan: GeneratedRuntimePlan) -> dict[str, Any]:
    """Создаёт hashable payload сгенерированного plan-only плана."""

    return {
        "schemaVersion": RUNTIME_STATE_SCHEMA_VERSION,
        "stage": RUNTIME_STATE_STAGE,
        "planId": plan.plan_id,
        "action": plan.action,
        "profileId": plan.profile.profile_id,
        "strategyId": plan.strategy.strategy_id,
        "buildTarget": plan.profile.build_target,
        "binaryRelativePath": plan.binary_relative_path,
        "hostlists": [
            {
                "id": hostlist.hostlist_id,
                "path": hostlist.path,
                "purpose": hostlist.purpose,
            }
            for hostlist in plan.hostlists
        ],
        "strategyRuntimeArgs": list(plan.strategy.runtime_args),
        "strategySourcePreset": plan.strategy.source_preset or {},
        "requiredArtifacts": [
            {
                "unitName": artifact.unit_name,
                "relativePath": artifact.relative_path,
                "exists": exists,
            }
            for artifact, exists in zip(plan.required_artifacts, plan.required_artifacts_exist)
        ],
        "sessionFiles": [
            {"label": item.label, "relativePath": item.relative_path, "purpose": item.purpose}
            for item in plan.session_files
        ],
        "logFiles": [
            {"label": item.label, "relativePath": item.relative_path, "purpose": item.purpose}
            for item in plan.log_files
        ],
        "contract": runtime_plan_contract_to_dict(plan.contract),
        "execution": {
            "executesNow": False,
            "mutatesServicesOrFirewallNow": False,
            "automaticChecksMayExecute": False,
        },
    }


def plan_payload_hash(payload: dict[str, Any]) -> str:
    """Возвращает стабильный sha256 для plan payload."""

    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _event_record(event_type: str, level: str, plan_id: str, plan_hash: str, message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": RUNTIME_STATE_SCHEMA_VERSION,
        "stage": RUNTIME_STATE_STAGE,
        "eventId": f"{event_type}-{plan_id}-{plan_hash[:12]}",
        "eventType": event_type,
        "level": level,
        "planId": plan_id,
        "planHash": plan_hash,
        "message": message,
        "createdAt": _utc_now(),
        "metadata": metadata or {},
        "executesNow": False,
    }


def append_runtime_event(paths: RuntimeStorePaths, event: dict[str, Any], profile_id: str = "default") -> Path:
    """Добавляет JSONL-запись в workspace runtime log."""

    ensure_runtime_store(paths.root)
    log_path = paths.logs_dir / f"{profile_id}.runtime.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return log_path


def _rollback_text(plan: GeneratedRuntimePlan, plan_hash: str) -> str:
    notes = "\n".join(f"- {note}" for note in plan.contract.rollback_notes)
    return f"""# Rollback notes для {plan.plan_id}

- plan hash: `{plan_hash}`
- action: `{plan.action}`
- profile: `{plan.profile.profile_id}`
- strategy: `{plan.strategy.strategy_id}`
- Stage 10 не исполняет этот план и не меняет систему.
- Будущий executor обязан использовать эти заметки до apply/session actions.

## Заметки

{notes}
"""


def prepare_runtime_plan(root: Path | None = None, action: str = "start", profile_id: str = "default") -> PreparedRuntimePlan:
    """Готовит plan state, rollback notes и log, но ничего не исполняет."""

    paths = ensure_runtime_store(root)
    plan = create_runtime_plan(paths.root, action=action, profile_id=profile_id)
    payload = generated_runtime_plan_to_payload(plan)
    plan_hash = plan_payload_hash(payload)
    record = {
        **payload,
        "planHash": plan_hash,
        "preparedAt": _utc_now(),
        "confirmationRequired": True,
        "confirmed": False,
        "expiresWhenPlanChanges": True,
        "allowsAutomaticReuse": False,
    }
    plan_path = paths.plans_dir / f"{plan.plan_id}.json"
    rollback_path = paths.rollback_dir / f"{plan.plan_id}.md"
    _write_json(plan_path, record)
    rollback_path.write_text(_rollback_text(plan, plan_hash), encoding="utf-8")
    log_path = append_runtime_event(
        paths,
        _event_record(
            "planned",
            "info",
            plan.plan_id,
            plan_hash,
            f"Prepared runtime {action} plan for profile {profile_id}; execution disabled in Stage 10.",
            {"action": action, "profileId": profile_id, "planPath": str(plan_path.relative_to(paths.root))},
        ),
        profile_id=profile_id,
    )
    return PreparedRuntimePlan(
        plan_id=plan.plan_id,
        plan_hash=plan_hash,
        action=plan.action,
        profile_id=plan.profile.profile_id,
        strategy_id=plan.strategy.strategy_id,
        plan_path=plan_path,
        rollback_path=rollback_path,
        log_path=log_path,
    )


def _read_prepared_plan(paths: RuntimeStorePaths, plan_id: str) -> dict[str, Any]:
    plan_path = paths.plans_dir / f"{plan_id}.json"
    if not plan_path.exists():
        raise ValueError(f"Prepared runtime plan не найден: {plan_id}. Сначала выполните --runtime-prepare.")
    return json.loads(plan_path.read_text(encoding="utf-8"))


def confirm_runtime_plan(root: Path | None = None, plan_id: str = "") -> RuntimeConfirmationRecord:
    """Создаёт owner confirmation, привязанный к сохранённому planHash."""

    if not plan_id:
        raise ValueError("Для подтверждения нужен plan id")
    paths = ensure_runtime_store(root)
    prepared = _read_prepared_plan(paths, plan_id)
    stored_hash = str(prepared["planHash"])
    payload_for_hash = {key: value for key, value in prepared.items() if key not in {"planHash", "preparedAt", "confirmationRequired", "confirmed", "expiresWhenPlanChanges", "allowsAutomaticReuse", "confirmationId", "confirmedAt"}}
    current_hash = plan_payload_hash(payload_for_hash)
    if current_hash != stored_hash:
        raise ValueError("Saved runtime plan hash не совпадает с содержимым плана; подтверждение отклонено")

    confirmation_id = f"confirm-{plan_id}-{stored_hash[:12]}"
    confirmation = {
        "schemaVersion": RUNTIME_STATE_SCHEMA_VERSION,
        "stage": RUNTIME_STATE_STAGE,
        "confirmationId": confirmation_id,
        "planId": plan_id,
        "planHash": stored_hash,
        "confirmedByOwner": True,
        "expiresWhenPlanChanges": True,
        "allowsAutomaticReuse": False,
        "createdAt": _utc_now(),
        "notes": [
            "Подтверждение относится только к сохранённому planHash.",
            "Stage 10 не исполняет подтверждённый план.",
            "Будущий executor должен заново сверить planHash перед действиями.",
        ],
    }
    confirmation_path = paths.confirmations_dir / f"{plan_id}.confirmation.json"
    _write_json(confirmation_path, confirmation)

    updated_plan = dict(prepared)
    updated_plan["confirmed"] = True
    updated_plan["confirmationId"] = confirmation_id
    updated_plan["confirmedAt"] = confirmation["createdAt"]
    _write_json(paths.plans_dir / f"{plan_id}.json", updated_plan)

    profile_id = str(prepared.get("profileId", "default"))
    log_path = append_runtime_event(
        paths,
        _event_record(
            "confirmed",
            "info",
            plan_id,
            stored_hash,
            f"Owner confirmed runtime plan {plan_id}; execution disabled in Stage 10.",
            {"confirmationId": confirmation_id, "confirmationPath": str(confirmation_path.relative_to(paths.root))},
        ),
        profile_id=profile_id,
    )
    return RuntimeConfirmationRecord(
        confirmation_id=confirmation_id,
        plan_id=plan_id,
        plan_hash=stored_hash,
        confirmation_path=confirmation_path,
        log_path=log_path,
    )


def runtime_log_to_text(root: Path | None = None, profile_id: str = "default", limit: int = 40) -> str:
    """Читает workspace runtime log без исправлений и исполнения."""

    paths = runtime_store_paths(root)
    log_path = paths.logs_dir / f"{profile_id}.runtime.jsonl"
    lines = [f"Runtime log для profile: {profile_id}", f"log file: {log_path}"]
    if not log_path.exists():
        lines.append("entries: 0")
        lines.append("state: log file отсутствует; выполните --runtime-prepare")
        return "\n".join(lines)

    raw_entries = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    entries = raw_entries[-limit:]
    lines.append(f"entries: {len(raw_entries)}")
    for raw in entries:
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            lines.append(f"  - invalid-json: {raw}")
            continue
        lines.append(
            "  - "
            + f"{event.get('createdAt', '?')} "
            + f"{event.get('eventType', '?')} "
            + f"{event.get('level', '?')}: "
            + f"{event.get('message', '')}"
        )
    lines.append("executes now: no")
    return "\n".join(lines)


def runtime_state_to_text(root: Path | None = None) -> str:
    """CLI-сводка по локальному runtime store."""

    paths = runtime_store_paths(root)
    existing = [path for path in paths.required_dirs if path.exists()]
    lines = ["Runtime state store:"]
    lines.extend(f"  {line}" for line in paths.as_text_lines())
    lines.append(f"existing dirs: {len(existing)}/{len(paths.required_dirs)}")
    lines.append("workspace-only mutation: yes")
    lines.append("system mutation: no")
    return "\n".join(lines)
