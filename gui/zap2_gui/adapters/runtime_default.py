"""Default strategy start/stop workflow для завершения v0.3-alpha.

Stage 14 собирает уже существующие кирпичи controlled runtime lifecycle в
понятную пару команд владельца:

* `--default-start-plan` / `--default-start --confirm <plan-id>`;
* `--default-stop-plan` / `--default-stop --confirm <plan-id>`.

Модуль не является bootstrap/install layer: он не скачивает код, не вызывает
upstream installer scripts, не управляет service mode и не прячет privileged
операции. Start/stop строятся как composite plans, сохраняются в `.zap2/runtime`,
получают `planHash` и исполняются только после owner confirmation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from .runtime_apply import (
    RuntimeApplyExecutionResult,
    RuntimeCommandResult,
    execute_runtime_owner_rules,
    prepare_runtime_owner_rules_plan,
)
from .runtime_session import (
    RuntimeSessionResult,
    RuntimeSessionStatus,
    build_runtime_session_config,
    runtime_session_status,
    start_runtime_session,
    stop_runtime_session,
)
from .runtime_state import (
    PreparedRuntimePlan,
    append_runtime_event,
    confirm_runtime_plan,
    ensure_runtime_store,
    plan_payload_hash,
    prepare_runtime_plan,
)
from .workspace_profiles import load_workspace_catalog
from ..project_paths import discover_layout

DEFAULT_WORKFLOW_STAGE = "v0.3-alpha_stage_14"
DEFAULT_WORKFLOW_SCHEMA_VERSION = 1
DEFAULT_WORKFLOW_MARKER = "zap2-default-workflow-v1"
SUPPORTED_DEFAULT_WORKFLOW_ACTIONS = ("start", "stop")

DefaultWorkflowAction = Literal["start", "stop"]


@dataclass(frozen=True)
class DefaultWorkflowChildPlan:
    """Дочерний plan, входящий в composite default workflow."""

    role: str
    plan_id: str
    plan_hash: str
    action: str
    plan_path: Path
    rollback_path: Path

    def to_dict(self, root: Path) -> dict[str, Any]:
        return {
            "role": self.role,
            "planId": self.plan_id,
            "planHash": self.plan_hash,
            "action": self.action,
            "planPath": str(self.plan_path.relative_to(root)),
            "rollbackPath": str(self.rollback_path.relative_to(root)),
        }


@dataclass(frozen=True)
class DefaultWorkflowPlan:
    """Composite plan для default start/stop."""

    action: DefaultWorkflowAction
    profile_id: str
    strategy_id: str
    plan_id: str
    plan_hash: str
    child_plans: tuple[DefaultWorkflowChildPlan, ...]
    plan_path: Path
    rollback_path: Path
    log_path: Path
    binary_path: Path
    hostlists: tuple[Path, ...]
    requires_sudo: bool

    def to_text(self) -> str:
        children = [f"  - {child.role}: {child.plan_id} ({child.plan_hash})" for child in self.child_plans]
        hostlists = [f"  - {path}" for path in self.hostlists]
        return "\n".join(
            [
                f"Default workflow plan для action: {self.action}",
                f"profile: {self.profile_id}",
                f"strategy: {self.strategy_id}",
                f"plan id: {self.plan_id}",
                f"plan hash: {self.plan_hash}",
                f"binary: {self.binary_path}",
                "hostlists:",
                *(hostlists or ["  - нет"]),
                "child plans:",
                *(children or ["  - нет"]),
                f"plan file: {self.plan_path}",
                f"rollback notes: {self.rollback_path}",
                f"runtime log: {self.log_path}",
                "requires owner confirmation: yes",
                f"requires sudo when executed by owner: {'yes' if self.requires_sudo else 'no'}",
                "uses service mode: no",
                "bootstrap mixed in: no",
                "contains remote bootstrap: no",
                "contains upstream installer script: no",
                "automatic checks may execute: no",
                "executes now: no",
            ]
        )


@dataclass(frozen=True)
class DefaultWorkflowResult:
    """CLI-friendly результат default-start/default-stop."""

    action: DefaultWorkflowAction
    state: str
    profile_id: str
    strategy_id: str
    plan_id: str
    plan_hash: str
    log_path: Path
    workflow_state_path: Path
    message: str
    apply_result: RuntimeApplyExecutionResult | None = None
    session_result: RuntimeSessionResult | None = None
    session_status: RuntimeSessionStatus | None = None

    def to_text(self) -> str:
        lines = [
            f"Default workflow {self.action}: {self.state}",
            f"profile: {self.profile_id}",
            f"strategy: {self.strategy_id}",
            f"plan id: {self.plan_id}",
            f"plan hash: {self.plan_hash}",
            f"workflow state: {self.workflow_state_path}",
            f"runtime log: {self.log_path}",
            f"message: {self.message}",
        ]
        if self.session_status is not None:
            lines.append(f"session status: {self.session_status.state}")
        if self.session_result is not None:
            lines.append(f"session result: {self.session_result.state}")
            if self.session_result.pid is not None:
                lines.append(f"session pid: {self.session_result.pid}")
        if self.apply_result is not None:
            lines.append(f"owner rules result: {self.apply_result.state}")
        lines.extend(
            [
                "owner confirmation verified: yes",
                "uses service mode: no",
                "bootstrap mixed in: no",
                "contains remote bootstrap: no",
                "contains upstream installer script: no",
            ]
        )
        return "\n".join(lines)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _default_plan_id(action: DefaultWorkflowAction, profile_id: str, strategy_id: str) -> str:
    return f"runtime-{profile_id}-{strategy_id}-default-{action}-workflow-plan"


def _load_strategy_id(root: Path, profile_id: str) -> str:
    catalog = load_workspace_catalog(root)
    try:
        return catalog.profile_by_id()[profile_id].strategy_id
    except KeyError as exc:
        raise ValueError(f"Workspace profile не найден: {profile_id}") from exc


def _prepared_to_child(role: str, prepared: PreparedRuntimePlan) -> DefaultWorkflowChildPlan:
    return DefaultWorkflowChildPlan(
        role=role,
        plan_id=prepared.plan_id,
        plan_hash=prepared.plan_hash,
        action=prepared.action,
        plan_path=prepared.plan_path,
        rollback_path=prepared.rollback_path,
    )


def _build_composite_payload(
    *,
    root: Path,
    action: DefaultWorkflowAction,
    profile_id: str,
    strategy_id: str,
    plan_id: str,
    child_plans: tuple[DefaultWorkflowChildPlan, ...],
    binary_path: Path,
    hostlists: tuple[Path, ...],
) -> dict[str, Any]:
    start_order = ["preflight", "apply-owner-rules", "session-start", "record-status"]
    stop_order = ["read-session-state", "session-stop", "revert-owner-rules", "record-status"]
    return {
        "schemaVersion": DEFAULT_WORKFLOW_SCHEMA_VERSION,
        "stage": DEFAULT_WORKFLOW_STAGE,
        "marker": DEFAULT_WORKFLOW_MARKER,
        "planId": plan_id,
        "action": action,
        "profileId": profile_id,
        "strategyId": strategy_id,
        "workflowKind": "default-strategy-start-stop",
        "executionOrder": start_order if action == "start" else stop_order,
        "binaryPath": str(binary_path),
        "hostlists": [str(path) for path in hostlists],
        "childPlans": [child.to_dict(root) for child in child_plans],
        "safety": {
            "requiresOwnerConfirmation": True,
            "requiresSudoWhenExecutedByOwner": True,
            "mayMutateFirewallWhenExecutedByOwner": True,
            "mayLaunchSessionProcessWhenExecutedByOwner": action == "start",
            "mayStopSessionProcessWhenExecutedByOwner": action == "stop",
            "mayManageServiceWhenExecutedByOwner": False,
            "usesServiceMode": False,
            "containsRemoteBootstrap": False,
            "containsUpstreamInstallerScript": False,
            "automaticChecksMayExecute": False,
            "bootstrapMixedIn": False,
        },
        "execution": {
            "executesNow": False,
            "requiresConfirmPlanId": plan_id,
            "guardedExecutionAvailable": True,
            "automaticChecksMayExecute": False,
        },
    }


def _rollback_text(payload: dict[str, Any], plan_hash: str) -> str:
    action = payload["action"]
    if action == "start":
        notes = [
            "Если default-start прервался после apply, выполните default-stop-plan/default-stop для остановки session и revert owner-rules.",
            "Revert удаляет только owned nftables table проекта и не делает глобальный firewall reset.",
            "Session runner останавливает только PID, записанный нашим marker в `.zap2/runtime/sessions/`.",
        ]
    else:
        notes = [
            "Если default-stop не нашёл session, revert owner-rules всё равно можно выполнить для удаления owned nftables table.",
            "Если PID из session state не совпал с recorded binary, stop отклоняется, чтобы не остановить чужой процесс.",
            "Повторный revert безопасен для уже отсутствующей owned table.",
        ]
    bullet_notes = "\n".join(f"- {note}" for note in notes)
    child_notes = "\n".join(f"- {child['role']}: `{child['planId']}` / `{child['planHash']}`" for child in payload["childPlans"])
    return f"""# Rollback notes для {payload['planId']}

- stage: `{DEFAULT_WORKFLOW_STAGE}`
- plan hash: `{plan_hash}`
- action: `{action}`
- profile: `{payload['profileId']}`
- strategy: `{payload['strategyId']}`
- service mode: нет
- bootstrap/install scripts: нет

## Дочерние планы

{child_notes}

## Заметки отката

{bullet_notes}
"""


def prepare_default_workflow_plan(root: Path | None = None, action: DefaultWorkflowAction = "start", profile_id: str = "default") -> DefaultWorkflowPlan:
    """Готовит composite default workflow plan, но ничего не исполняет."""

    if action not in SUPPORTED_DEFAULT_WORKFLOW_ACTIONS:
        raise ValueError(f"Неизвестное default workflow action: {action}")
    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    strategy_id = _load_strategy_id(paths.root, profile_id)

    if action == "start":
        runtime_prepared = prepare_runtime_plan(paths.root, action="start", profile_id=profile_id)
        rules_prepared = prepare_runtime_owner_rules_plan(paths.root, action="apply", profile_id=profile_id)
        child_plans = (
            _prepared_to_child("runtime-start", runtime_prepared),
            _prepared_to_child("owner-rules-apply", rules_prepared),
        )
    else:
        runtime_prepared = prepare_runtime_plan(paths.root, action="stop", profile_id=profile_id)
        rules_prepared = prepare_runtime_owner_rules_plan(paths.root, action="revert", profile_id=profile_id)
        child_plans = (
            _prepared_to_child("runtime-stop", runtime_prepared),
            _prepared_to_child("owner-rules-revert", rules_prepared),
        )

    catalog = load_workspace_catalog(paths.root)
    profile = catalog.profile_by_id()[profile_id]
    binary_path = paths.root / "core" / "zapret2" / "nfq2" / "nfqws2"
    hostlists = tuple((paths.root / item.path).resolve() for item in profile.hostlists)
    plan_id = _default_plan_id(action, profile_id, strategy_id)
    payload = _build_composite_payload(
        root=paths.root,
        action=action,
        profile_id=profile_id,
        strategy_id=strategy_id,
        plan_id=plan_id,
        child_plans=child_plans,
        binary_path=binary_path,
        hostlists=hostlists,
    )
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
    plan_path = paths.plans_dir / f"{plan_id}.json"
    rollback_path = paths.rollback_dir / f"{plan_id}.md"
    _write_json(plan_path, record)
    rollback_path.write_text(_rollback_text(payload, plan_hash), encoding="utf-8")
    log_path = append_runtime_event(
        paths,
        {
            "schemaVersion": DEFAULT_WORKFLOW_SCHEMA_VERSION,
            "stage": DEFAULT_WORKFLOW_STAGE,
            "eventId": f"default-{action}-planned-{plan_id}-{plan_hash[:12]}",
            "eventType": f"default-{action}-planned",
            "level": "info",
            "planId": plan_id,
            "planHash": plan_hash,
            "message": f"Prepared default {action} workflow plan for profile {profile_id}; execution disabled until owner confirmation.",
            "createdAt": _utc_now(),
            "metadata": {"profileId": profile_id, "strategyId": strategy_id, "childPlans": [child.plan_id for child in child_plans]},
            "executesNow": False,
            "mutatesFirewallOrServicesNow": False,
            "managesServiceNow": False,
        },
        profile_id=profile_id,
    )
    return DefaultWorkflowPlan(
        action=action,
        profile_id=profile_id,
        strategy_id=strategy_id,
        plan_id=plan_id,
        plan_hash=plan_hash,
        child_plans=child_plans,
        plan_path=plan_path,
        rollback_path=rollback_path,
        log_path=log_path,
        binary_path=binary_path,
        hostlists=hostlists,
        requires_sudo=True,
    )


def _payload_without_runtime_fields(saved: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in saved.items()
        if key
        not in {
            "planHash",
            "preparedAt",
            "confirmationRequired",
            "confirmed",
            "expiresWhenPlanChanges",
            "allowsAutomaticReuse",
            "confirmationId",
            "confirmedAt",
        }
    }


def _load_confirmed_default_plan(root: Path, action: DefaultWorkflowAction, profile_id: str, confirm_plan_id: str) -> tuple[dict[str, Any], str]:
    paths = ensure_runtime_store(root)
    strategy_id = _load_strategy_id(paths.root, profile_id)
    expected_plan_id = _default_plan_id(action, profile_id, strategy_id)
    if not confirm_plan_id:
        raise ValueError("Для default workflow нужен --confirm <plan-id>")
    if confirm_plan_id != expected_plan_id:
        raise ValueError(f"Передан не тот plan id: {confirm_plan_id}; ожидается {expected_plan_id}")
    plan_path = paths.plans_dir / f"{expected_plan_id}.json"
    confirmation_path = paths.confirmations_dir / f"{expected_plan_id}.confirmation.json"
    if not plan_path.exists():
        raise ValueError(f"Prepared default workflow plan не найден: {expected_plan_id}. Сначала выполните --default-{action}-plan.")
    if not confirmation_path.exists():
        raise ValueError(f"Confirmation не найден для {expected_plan_id}. Сначала выполните --runtime-confirm {expected_plan_id}.")
    saved = _read_json(plan_path)
    confirmation = _read_json(confirmation_path)
    current_hash = plan_payload_hash(_payload_without_runtime_fields(saved))
    if saved.get("planHash") != current_hash:
        raise ValueError("Prepared default workflow plan устарел: текущий planHash не совпадает с сохранённым")
    if saved.get("confirmed") is not True:
        raise ValueError("Prepared default workflow plan ещё не подтверждён owner confirmation")
    if confirmation.get("planHash") != current_hash or confirmation.get("confirmedByOwner") is not True:
        raise ValueError("Confirmation не соответствует текущему default workflow plan hash")
    return saved, current_hash


def _confirm_child_plans(root: Path, saved_composite: dict[str, Any]) -> None:
    """Создаёт derived confirmations для дочерних plans после composite confirmation."""

    paths = ensure_runtime_store(root)
    for child in saved_composite.get("childPlans", []):
        child_plan_id = str(child["planId"])
        child_plan_path = paths.plans_dir / f"{child_plan_id}.json"
        if not child_plan_path.exists():
            raise ValueError(f"Child plan не найден для default workflow: {child_plan_id}")
        child_saved = _read_json(child_plan_path)
        if child_saved.get("planHash") != child.get("planHash"):
            raise ValueError(f"Child plan hash не совпадает с composite plan: {child_plan_id}")
        confirm_runtime_plan(root, plan_id=child_plan_id)


def _write_workflow_state(paths_root: Path, record: dict[str, Any], profile_id: str) -> Path:
    paths = ensure_runtime_store(paths_root)
    state_path = paths.sessions_dir / f"{profile_id}.default-workflow.json"
    _write_json(state_path, record)
    return state_path


def execute_default_workflow(
    root: Path | None = None,
    action: DefaultWorkflowAction = "start",
    profile_id: str = "default",
    confirm_plan_id: str = "",
    *,
    apply_runner: Callable[[tuple[str, ...]], RuntimeCommandResult] | None = None,
    allow_without_root: bool = False,
) -> DefaultWorkflowResult:
    """Исполняет owner-confirmed default start/stop workflow."""

    if action not in SUPPORTED_DEFAULT_WORKFLOW_ACTIONS:
        raise ValueError(f"Неизвестное default workflow action: {action}")
    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    saved, plan_hash = _load_confirmed_default_plan(paths.root, action, profile_id, confirm_plan_id)
    _confirm_child_plans(paths.root, saved)
    strategy_id = str(saved["strategyId"])
    state = "started" if action == "start" else "stopped"
    message = f"default {action} completed"
    apply_result: RuntimeApplyExecutionResult | None = None
    session_result: RuntimeSessionResult | None = None
    session_status: RuntimeSessionStatus | None = None

    if action == "start":
        # Preflight до firewall apply: бинарник должен существовать и быть executable.
        build_runtime_session_config(paths.root, profile_id)
        apply_plan_id = next(str(child["planId"]) for child in saved["childPlans"] if child["role"] == "owner-rules-apply")
        session_plan_id = next(str(child["planId"]) for child in saved["childPlans"] if child["role"] == "runtime-start")
        apply_result = execute_runtime_owner_rules(
            paths.root,
            action="apply",
            profile_id=profile_id,
            confirm_plan_id=apply_plan_id,
            runner=apply_runner,
            allow_without_root=allow_without_root,
        )
        if apply_result.state != "applied":
            state = "failed"
            message = "owner-rules apply failed; session start skipped"
        else:
            # session_plan_id используется как явная self-check: start_runtime_session сам
            # сверит подтверждение текущего runtime start plan.
            if session_plan_id:
                session_result = start_runtime_session(paths.root, profile_id=profile_id)
                session_status = runtime_session_status(paths.root, profile_id=profile_id)
                state = "started" if session_result.state == "running" else session_result.state
                message = "default start workflow applied owner-rules and started session"
    else:
        # Stop сначала пытается остановить нашу session, но revert должен быть доступен и
        # когда session state отсутствует: цель stop — отключить default strategy.
        session_result = stop_runtime_session(paths.root, profile_id=profile_id)
        revert_plan_id = next(str(child["planId"]) for child in saved["childPlans"] if child["role"] == "owner-rules-revert")
        apply_result = execute_runtime_owner_rules(
            paths.root,
            action="revert",
            profile_id=profile_id,
            confirm_plan_id=revert_plan_id,
            runner=apply_runner,
            allow_without_root=allow_without_root,
        )
        session_status = runtime_session_status(paths.root, profile_id=profile_id)
        if apply_result.state != "reverted":
            state = "failed"
            message = "session stop attempted, but owner-rules revert failed"
        else:
            state = "stopped"
            message = "default stop workflow stopped session if present and reverted owner-rules"

    state_record = {
        "schemaVersion": DEFAULT_WORKFLOW_SCHEMA_VERSION,
        "stage": DEFAULT_WORKFLOW_STAGE,
        "marker": DEFAULT_WORKFLOW_MARKER,
        "state": state,
        "action": action,
        "profileId": profile_id,
        "strategyId": strategy_id,
        "planId": confirm_plan_id,
        "planHash": plan_hash,
        "updatedAt": _utc_now(),
        "childPlans": saved.get("childPlans", []),
        "sessionResult": None if session_result is None else {"state": session_result.state, "pid": session_result.pid, "message": session_result.message},
        "ownerRulesResult": None if apply_result is None else {"state": apply_result.state, "message": apply_result.message},
        "usesServiceMode": False,
        "bootstrapMixedIn": False,
        "containsRemoteBootstrap": False,
        "containsUpstreamInstallerScript": False,
    }
    workflow_state_path = _write_workflow_state(paths.root, state_record, profile_id)
    log_path = append_runtime_event(
        paths,
        {
            "schemaVersion": DEFAULT_WORKFLOW_SCHEMA_VERSION,
            "stage": DEFAULT_WORKFLOW_STAGE,
            "eventId": f"default-{action}-{state}-{confirm_plan_id}-{plan_hash[:12]}",
            "eventType": f"default-{action}-{state}",
            "level": "info" if state in {"started", "stopped"} else "error",
            "planId": confirm_plan_id,
            "planHash": plan_hash,
            "message": message,
            "createdAt": _utc_now(),
            "metadata": {"profileId": profile_id, "strategyId": strategy_id, "statePath": str(workflow_state_path.relative_to(paths.root))},
            "executesNow": True,
            "mutatesFirewallOrServicesNow": True,
            "managesServiceNow": False,
        },
        profile_id=profile_id,
    )
    return DefaultWorkflowResult(
        action=action,
        state=state,
        profile_id=profile_id,
        strategy_id=strategy_id,
        plan_id=confirm_plan_id,
        plan_hash=plan_hash,
        log_path=log_path,
        workflow_state_path=workflow_state_path,
        message=message,
        apply_result=apply_result,
        session_result=session_result,
        session_status=session_status,
    )
