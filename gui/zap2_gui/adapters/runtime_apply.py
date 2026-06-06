"""Owner-confirmed apply/revert системных правил runtime lifecycle.

Stage 12 отделяет системный apply/revert от session runner. Модуль умеет:

* построить plan для будущего применения или отката nftables-правил;
* сохранить этот plan в `.zap2/runtime` через hash/confirmation gate;
* исполнить только подтверждённый owner-ом plan и только локально;
* записать результат в runtime log и apply-state.

Автоматические проверки не вызывают реальный `nft`, не требуют root и не меняют
firewall. Тесты используют fake runner.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from .runtime_plan_generator import create_runtime_plan
from .runtime_state import (
    PreparedRuntimePlan,
    append_runtime_event,
    ensure_runtime_store,
    plan_payload_hash,
    runtime_store_paths,
)
from .workspace_profiles import load_workspace_catalog
from ..project_paths import discover_layout

APPLY_STAGE = "v0.3-alpha_stage_12"
APPLY_SCHEMA_VERSION = 1
APPLY_MARKER = "zap2-runtime-apply-v1"
SUPPORTED_RUNTIME_APPLY_ACTIONS = ("apply", "revert")
DEFAULT_NFT_TABLE_PREFIX = "zap2"
DEFAULT_NFT_CHAIN = "local_out"
DEFAULT_NFQUEUE_NUM = 200
DEFAULT_TCP_PORTS = (80, 443)
DEFAULT_UDP_PORTS = (443,)

RuntimeApplyAction = Literal["apply", "revert"]
CommandRunner = Callable[[tuple[str, ...]], "RuntimeCommandResult"]


@dataclass(frozen=True)
class RuntimeApplyCommand:
    """Одна owner-executed команда системного apply/revert."""

    label: str
    argv: tuple[str, ...]
    requires_sudo: bool
    mutates_system: bool
    description: str
    ignore_missing_on_revert: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "argv": list(self.argv),
            "requiresSudo": self.requires_sudo,
            "mutatesSystem": self.mutates_system,
            "description": self.description,
            "ignoreMissingOnRevert": self.ignore_missing_on_revert,
        }


@dataclass(frozen=True)
class RuntimeApplyPlan:
    """План системного apply/revert, построенный из workspace profile."""

    action: RuntimeApplyAction
    profile_id: str
    strategy_id: str
    plan_id: str
    nft_table: str
    nft_chain: str
    nfqueue_num: int
    commands: tuple[RuntimeApplyCommand, ...]
    rollback_notes: tuple[str, ...]
    binary_relative_path: str
    hostlists: tuple[str, ...]

    @property
    def requires_sudo(self) -> bool:
        return any(command.requires_sudo for command in self.commands)

    @property
    def mutates_firewall(self) -> bool:
        return any(command.mutates_system for command in self.commands)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": APPLY_SCHEMA_VERSION,
            "stage": APPLY_STAGE,
            "marker": APPLY_MARKER,
            "planId": self.plan_id,
            "action": self.action,
            "profileId": self.profile_id,
            "strategyId": self.strategy_id,
            "engine": "nftables",
            "nftTable": self.nft_table,
            "nftChain": self.nft_chain,
            "nfqueueNum": self.nfqueue_num,
            "binaryRelativePath": self.binary_relative_path,
            "hostlists": list(self.hostlists),
            "commands": [command.to_dict() for command in self.commands],
            "rollbackNotes": list(self.rollback_notes),
            "safety": {
                "requiresOwnerConfirmation": True,
                "requiresSudoWhenExecutedByOwner": self.requires_sudo,
                "mutatesFirewallWhenExecutedByOwner": self.mutates_firewall,
                "managesServiceWhenExecutedByOwner": False,
                "containsRemoteBootstrap": False,
                "containsUpstreamInstallerScript": False,
                "automaticChecksMayExecute": False,
                "bootstrapMixedIn": False,
            },
            "execution": {
                "executesNow": False,
                "mutatesServicesOrFirewallNow": False,
                "automaticChecksMayExecute": False,
            },
        }

    def to_text(self) -> str:
        command_lines = [
            f"  - {command.label}: {' '.join(command.argv)}; requires sudo: {'yes' if command.requires_sudo else 'no'}; mutates firewall: {'yes' if command.mutates_system else 'no'}"
            for command in self.commands
        ]
        rollback_lines = [f"  - {note}" for note in self.rollback_notes]
        return "\n".join(
            [
                f"Runtime {self.action} plan для profile: {self.profile_id}",
                f"plan id: {self.plan_id}",
                f"strategy: {self.strategy_id}",
                "engine: nftables",
                f"nft table: inet {self.nft_table}",
                f"nft chain: {self.nft_chain}",
                f"nfqueue: {self.nfqueue_num}",
                f"binary: {self.binary_relative_path}",
                "commands:",
                *(command_lines or ["  - нет"]),
                "rollback notes:",
                *(rollback_lines or ["  - нет"]),
                "requires owner confirmation: yes",
                f"requires sudo when executed by owner: {'yes' if self.requires_sudo else 'no'}",
                f"mutates firewall when executed by owner: {'yes' if self.mutates_firewall else 'no'}",
                "manages service: no",
                "contains remote bootstrap: no",
                "contains upstream installer script: no",
                "automatic checks may execute: no",
                "executes now: no",
            ]
        )


@dataclass(frozen=True)
class RuntimeCommandResult:
    """Результат одной команды runner-а."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class RuntimeApplyExecutionResult:
    """CLI-friendly результат owner-confirmed apply/revert."""

    action: RuntimeApplyAction
    state: str
    profile_id: str
    plan_id: str
    plan_hash: str
    executed_commands: tuple[RuntimeCommandResult, ...]
    state_path: Path
    log_path: Path
    message: str

    def to_text(self) -> str:
        lines = [
            f"Runtime {self.action}: {self.state}",
            f"profile: {self.profile_id}",
            f"plan id: {self.plan_id}",
            f"plan hash: {self.plan_hash}",
            f"message: {self.message}",
            f"apply state: {self.state_path}",
            f"runtime log: {self.log_path}",
            "executed commands:",
        ]
        for item in self.executed_commands:
            lines.append(f"  - rc={item.returncode}: {' '.join(item.argv)}")
            if item.stderr:
                lines.append(f"    stderr: {item.stderr.strip()}")
        lines.extend(
            [
                "owner confirmation verified: yes",
                "mutates firewall/services now: yes" if self.action in {"apply", "revert"} else "mutates firewall/services now: no",
                "manages service: no",
                "bootstrap mixed in: no",
            ]
        )
        return "\n".join(lines)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _nft_table_name(profile_id: str) -> str:
    safe_profile = "".join(ch if ch.isalnum() else "_" for ch in profile_id.lower()).strip("_") or "default"
    return f"{DEFAULT_NFT_TABLE_PREFIX}_{safe_profile}"


def _nft_apply_commands(table: str, chain: str, qnum: int) -> tuple[RuntimeApplyCommand, ...]:
    tcp_ports = ", ".join(str(port) for port in DEFAULT_TCP_PORTS)
    udp_ports = ", ".join(str(port) for port in DEFAULT_UDP_PORTS)
    return (
        RuntimeApplyCommand(
            label="nft-add-table",
            argv=("nft", "add", "table", "inet", table),
            requires_sudo=True,
            mutates_system=True,
            description="Создать отдельную nftables table, принадлежащую workspace profile.",
        ),
        RuntimeApplyCommand(
            label="nft-add-local-out-chain",
            argv=("nft", "add", "chain", "inet", table, chain, "{ type filter hook output priority filter; policy accept; }"),
            requires_sudo=True,
            mutates_system=True,
            description="Создать отдельную output chain для локального трафика владельца.",
        ),
        RuntimeApplyCommand(
            label="nft-queue-tcp-web",
            argv=("nft", "add", "rule", "inet", table, chain, f'tcp dport {{ {tcp_ports} }} queue num {qnum} bypass comment "zap2:{table}:tcp-out"'),
            requires_sudo=True,
            mutates_system=True,
            description="Отправить локальный TCP 80/443 в NFQUEUE с queue-bypass.",
        ),
        RuntimeApplyCommand(
            label="nft-queue-udp-quic",
            argv=("nft", "add", "rule", "inet", table, chain, f'udp dport {{ {udp_ports} }} queue num {qnum} bypass comment "zap2:{table}:udp-out"'),
            requires_sudo=True,
            mutates_system=True,
            description="Отправить локальный UDP/443 в NFQUEUE с queue-bypass.",
        ),
    )


def _nft_revert_commands(table: str) -> tuple[RuntimeApplyCommand, ...]:
    return (
        RuntimeApplyCommand(
            label="nft-delete-owned-table",
            argv=("nft", "delete", "table", "inet", table),
            requires_sudo=True,
            mutates_system=True,
            description="Удалить только нашу отдельную nftables table; чужие tables/chains не трогать.",
            ignore_missing_on_revert=True,
        ),
    )


def create_runtime_apply_plan(root: Path | None = None, action: RuntimeApplyAction = "apply", profile_id: str = "default") -> RuntimeApplyPlan:
    """Создаёт owner-confirmed apply/revert plan как данные."""

    if action not in SUPPORTED_RUNTIME_APPLY_ACTIONS:
        raise ValueError(f"Неизвестное apply action: {action}. Доступно: {', '.join(SUPPORTED_RUNTIME_APPLY_ACTIONS)}")
    layout = discover_layout(root)
    catalog = load_workspace_catalog(layout.root)
    profiles = catalog.profile_by_id()
    if profile_id not in profiles:
        raise ValueError(f"Неизвестный workspace-профиль: {profile_id}")
    profile = profiles[profile_id]
    strategies = catalog.strategy_by_id()
    if profile.strategy_id not in strategies:
        raise ValueError(f"Профиль {profile.profile_id} ссылается на неизвестную стратегию: {profile.strategy_id}")
    # Берём binary path из start plan, чтобы apply/revert не расходился с runtime plan generator.
    start_plan = create_runtime_plan(layout.root, action="start", profile_id=profile_id)
    table = _nft_table_name(profile.profile_id)
    plan_id = f"runtime-{profile.profile_id}-{profile.strategy_id}-{action}-owner-rules-plan"
    commands = _nft_apply_commands(table, DEFAULT_NFT_CHAIN, DEFAULT_NFQUEUE_NUM) if action == "apply" else _nft_revert_commands(table)
    if action == "apply":
        rollback_notes = (
            f"Откат выполняется командой revert plan для того же profile: {profile.profile_id}.",
            f"Revert обязан удалить только nftables table `inet {table}` и не трогать чужие правила.",
            "Если session start после apply не удался, сначала остановить session state, затем выполнить revert.",
        )
    else:
        rollback_notes = (
            f"Revert удаляет только nftables table `inet {table}`, созданную Stage 12 apply, и не затрагивает чужие таблицы/цепочки.",
            "Если таблица уже отсутствует, состояние считается безопасным для повторного stop workflow.",
            "После revert сохранить log/state; не удалять diagnostic logs автоматически.",
        )
    return RuntimeApplyPlan(
        action=action,
        profile_id=profile.profile_id,
        strategy_id=profile.strategy_id,
        plan_id=plan_id,
        nft_table=table,
        nft_chain=DEFAULT_NFT_CHAIN,
        nfqueue_num=DEFAULT_NFQUEUE_NUM,
        commands=commands,
        rollback_notes=rollback_notes,
        binary_relative_path=start_plan.binary_relative_path,
        hostlists=tuple(hostlist.path for hostlist in profile.hostlists),
    )


def runtime_apply_plan_to_text(action: RuntimeApplyAction = "apply", profile_id: str = "default", root: Path | None = None) -> str:
    """CLI-friendly текст owner-confirmed apply/revert plan."""

    return create_runtime_apply_plan(root=root, action=action, profile_id=profile_id).to_text()


def _rollback_text(plan: RuntimeApplyPlan, plan_hash: str) -> str:
    notes = "\n".join(f"- {note}" for note in plan.rollback_notes)
    commands = "\n".join(f"- `{' '.join(command.argv)}`" for command in plan.commands)
    return f"""# Rollback notes для {plan.plan_id}

- stage: `{APPLY_STAGE}`
- plan hash: `{plan_hash}`
- action: `{plan.action}`
- profile: `{plan.profile_id}`
- strategy: `{plan.strategy_id}`
- nft table: `inet {plan.nft_table}`
- service mode: нет
- bootstrap/install scripts: нет

## Команды плана

{commands}

## Заметки отката

{notes}
"""


def prepare_runtime_owner_rules_plan(root: Path | None = None, action: RuntimeApplyAction = "apply", profile_id: str = "default") -> PreparedRuntimePlan:
    """Сохраняет apply/revert plan в `.zap2/runtime`, но не исполняет его."""

    paths = ensure_runtime_store(root)
    plan = create_runtime_apply_plan(paths.root, action=action, profile_id=profile_id)
    payload = plan.to_payload()
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
        {
            "schemaVersion": APPLY_SCHEMA_VERSION,
            "stage": APPLY_STAGE,
            "eventId": f"owner-rules-{action}-planned-{plan.plan_id}-{plan_hash[:12]}",
            "eventType": f"owner-rules-{action}-planned",
            "level": "info",
            "planId": plan.plan_id,
            "planHash": plan_hash,
            "message": f"Prepared owner-confirmed runtime {action} rules plan for profile {profile_id}; execution disabled until explicit --runtime-{action}.",
            "createdAt": _utc_now(),
            "metadata": {"profileId": profile_id, "engine": "nftables", "nftTable": plan.nft_table},
            "executesNow": False,
            "mutatesFirewallOrServicesNow": False,
            "managesServiceNow": False,
        },
        profile_id=profile_id,
    )
    return PreparedRuntimePlan(
        plan_id=plan.plan_id,
        plan_hash=plan_hash,
        action=plan.action,
        profile_id=plan.profile_id,
        strategy_id=plan.strategy_id,
        plan_path=plan_path,
        rollback_path=rollback_path,
        log_path=log_path,
    )


def _default_runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return RuntimeCommandResult(argv=argv, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)


def _is_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    return True if geteuid is None else geteuid() == 0


def _load_confirmed_plan(root: Path, expected: RuntimeApplyPlan, confirm_plan_id: str) -> tuple[dict[str, Any], str]:
    paths = ensure_runtime_store(root)
    if not confirm_plan_id:
        raise ValueError("Для runtime apply/revert нужен --confirm <plan-id>")
    if confirm_plan_id != expected.plan_id:
        raise ValueError(f"Передан не тот plan id: {confirm_plan_id}; ожидается {expected.plan_id}")
    plan_path = paths.plans_dir / f"{expected.plan_id}.json"
    confirmation_path = paths.confirmations_dir / f"{expected.plan_id}.confirmation.json"
    if not plan_path.exists():
        raise ValueError(f"Prepared owner-rules plan не найден: {expected.plan_id}. Сначала выполните --runtime-{expected.action}-plan.")
    if not confirmation_path.exists():
        raise ValueError(f"Confirmation не найден для {expected.plan_id}. Сначала выполните --runtime-confirm {expected.plan_id}.")
    saved = _read_json(plan_path)
    confirmation = _read_json(confirmation_path)
    current_hash = plan_payload_hash(expected.to_payload())
    if saved.get("planHash") != current_hash:
        raise ValueError("Prepared owner-rules plan устарел: текущий planHash не совпадает с сохранённым")
    if saved.get("confirmed") is not True:
        raise ValueError("Prepared owner-rules plan ещё не подтверждён owner confirmation")
    if confirmation.get("planHash") != current_hash or confirmation.get("confirmedByOwner") is not True:
        raise ValueError("Confirmation не соответствует текущему owner-rules plan hash")
    return saved, current_hash


def _missing_table_is_ok(result: RuntimeCommandResult) -> bool:
    text = f"{result.stdout}\n{result.stderr}".lower()
    return result.returncode != 0 and ("no such file" in text or "no such table" in text or "not found" in text)


def execute_runtime_owner_rules(
    root: Path | None = None,
    action: RuntimeApplyAction = "apply",
    profile_id: str = "default",
    confirm_plan_id: str = "",
    *,
    runner: CommandRunner | None = None,
    allow_without_root: bool = False,
) -> RuntimeApplyExecutionResult:
    """Исполняет только подтверждённый owner-rules apply/revert plan."""

    if action not in SUPPORTED_RUNTIME_APPLY_ACTIONS:
        raise ValueError(f"Неизвестное apply action: {action}")
    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    plan = create_runtime_apply_plan(paths.root, action=action, profile_id=profile_id)
    _saved, plan_hash = _load_confirmed_plan(paths.root, plan, confirm_plan_id)
    if runner is None:
        if shutil.which("nft") is None:
            raise ValueError("Команда nft не найдена. Установите nftables или используйте другой будущий apply backend.")
        runner = _default_runner
    if not allow_without_root and not _is_root():
        raise ValueError("Runtime apply/revert требует root. Запустите owner-confirmed команду через sudo на своей машине.")

    results: list[RuntimeCommandResult] = []
    state = "applied" if action == "apply" else "reverted"
    message = f"owner-confirmed {action} completed"
    for command in plan.commands:
        result = runner(command.argv)
        results.append(result)
        if result.ok:
            continue
        if action == "revert" and command.ignore_missing_on_revert and _missing_table_is_ok(result):
            state = "reverted"
            message = "owned nft table was already missing; revert considered safe"
            continue
        state = "failed"
        message = f"command failed: {command.label}"
        break

    state_path = paths.sessions_dir / f"{profile_id}.owner-rules.json"
    state_record = {
        "schemaVersion": APPLY_SCHEMA_VERSION,
        "stage": APPLY_STAGE,
        "marker": APPLY_MARKER,
        "state": state,
        "action": action,
        "profileId": profile_id,
        "strategyId": plan.strategy_id,
        "planId": plan.plan_id,
        "planHash": plan_hash,
        "engine": "nftables",
        "nftTable": plan.nft_table,
        "nfqueueNum": plan.nfqueue_num,
        "updatedAt": _utc_now(),
        "commands": [
            {"argv": list(item.argv), "returncode": item.returncode, "stdout": item.stdout, "stderr": item.stderr}
            for item in results
        ],
        "managesServiceNow": False,
        "containsRemoteBootstrap": False,
        "containsUpstreamInstallerScript": False,
    }
    _write_json(state_path, state_record)
    log_path = append_runtime_event(
        paths,
        {
            "schemaVersion": APPLY_SCHEMA_VERSION,
            "stage": APPLY_STAGE,
            "eventId": f"owner-rules-{action}-{state}-{plan.plan_id}-{plan_hash[:12]}",
            "eventType": f"owner-rules-{action}-{state}",
            "level": "info" if state in {"applied", "reverted"} else "error",
            "planId": plan.plan_id,
            "planHash": plan_hash,
            "message": message,
            "createdAt": _utc_now(),
            "metadata": {"profileId": profile_id, "engine": "nftables", "nftTable": plan.nft_table, "statePath": str(state_path.relative_to(paths.root))},
            "executesNow": True,
            "mutatesFirewallOrServicesNow": True,
            "managesServiceNow": False,
        },
        profile_id=profile_id,
    )
    return RuntimeApplyExecutionResult(
        action=action,
        state=state,
        profile_id=profile_id,
        plan_id=plan.plan_id,
        plan_hash=plan_hash,
        executed_commands=tuple(results),
        state_path=state_path,
        log_path=log_path,
        message=message,
    )
