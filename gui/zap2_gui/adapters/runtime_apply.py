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

import fcntl
import ipaddress
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from .runtime_plan_generator import create_runtime_plan
from .runtime_queue import resolve_runtime_queue
from .runtime_state import (
    PreparedRuntimePlan,
    append_runtime_event,
    ensure_runtime_store,
    plan_payload_hash,
    runtime_store_paths,
    atomic_write_json,
)
from .workspace_profiles import load_workspace_catalog
from .runtime_owner import owned_nft_table_name, runtime_owner_identity, runtime_owner_uid
from ..project_paths import discover_layout

APPLY_STAGE = "v0.3-alpha_stage_12"
APPLY_SCHEMA_VERSION = 1
APPLY_MARKER = "zap2-runtime-apply-v1"
SUPPORTED_RUNTIME_APPLY_ACTIONS = ("apply", "revert")
DEFAULT_NFT_TABLE_PREFIX = "zap2"
DEFAULT_NFT_CHAIN = "local_out"
DEFAULT_NFT_INPUT_CHAIN = "local_in"
DEFAULT_TCP_PORTS = ("80", "443")
DEFAULT_DESYNC_MARK = "0x40000000"
DEFAULT_TCP_ORIGINAL_PACKET_RANGE = "1-8"
DEFAULT_UDP_ORIGINAL_PACKET_RANGE = "1-4"

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
    queued_tcp_ports: tuple[str, ...]
    queued_udp_ports: tuple[str, ...]
    queued_edge_ips: tuple[str, ...]
    capture_policy: dict[str, Any] | None
    queue_input_syn_ack: bool
    queue_input_fin_rst: bool
    owner_uid: int
    owner_uid_source: str
    owner_key: str
    owner_marker: str
    desync_mark: str
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
            "queuedTcpPorts": list(self.queued_tcp_ports),
            "queuedUdpPorts": list(self.queued_udp_ports),
            "queuedEdgeIps": list(self.queued_edge_ips),
            "capturePolicy": self.capture_policy or {},
            "queueInputSynAck": self.queue_input_syn_ack,
            "queueInputFinRst": self.queue_input_fin_rst,
            "nftCountersEnabled": True,
            "ownerUid": self.owner_uid,
            "ownerUidSource": self.owner_uid_source,
            "ownerKey": self.owner_key,
            "ownerMarker": self.owner_marker,
            "desyncMark": self.desync_mark,
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
                f"queued TCP ports: {', '.join(self.queued_tcp_ports) if self.queued_tcp_ports else 'нет'}",
                f"queued UDP ports: {', '.join(self.queued_udp_ports) if self.queued_udp_ports else 'нет'}",
                f"queued edge IPs: {', '.join(self.queued_edge_ips) if self.queued_edge_ips else 'нет / runtime-derived hostlist'}",
                f"capture policy: {str((self.capture_policy or {}).get('kind') or 'runtime-derived')}",
                f"input SYN+ACK queue: {'yes' if self.queue_input_syn_ack else 'no'}",
                f"input FIN/RST queue: {'yes' if self.queue_input_fin_rst else 'no'}",
                "nft counters: yes",
                f"owner uid scope: {self.owner_uid} ({self.owner_uid_source})",
                f"owner key: {self.owner_key}",
                f"owner marker: {self.owner_marker}",
                f"desync mark loop guard: {self.desync_mark}",
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
    atomic_write_json(path, data)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _nft_table_name(root: Path, profile_id: str) -> str:
    return owned_nft_table_name(root, profile_id, prefix=DEFAULT_NFT_TABLE_PREFIX)


def _legacy_nft_table_name(profile_id: str) -> str:
    """Table name used by the pre-runtime-security workspace-sync build."""

    safe_profile = "".join(ch if ch.isalnum() else "_" for ch in profile_id.lower()).strip("_") or "default"
    return f"{DEFAULT_NFT_TABLE_PREFIX}_{safe_profile}"


def _valid_port_token(value: str) -> bool:
    """Return whether a strategy port token is safe to embed in an nft set.

    Strategy files are project data, but keeping this parser narrow prevents a
    malformed ``--filter-*`` value from becoming raw nft syntax. Supported forms
    match the subset used by nfqws2 profiles: ``443`` and ``443-65535``.
    """

    token = value.strip()
    if not token:
        return False
    if "-" in token:
        left, right = token.split("-", 1)
        if not left.isdigit() or not right.isdigit():
            return False
        low, high = int(left, 10), int(right, 10)
        return 1 <= low <= high <= 65535
    if not token.isdigit():
        return False
    port = int(token, 10)
    return 1 <= port <= 65535


def _ports_from_strategy_args(runtime_args: tuple[str, ...], option: str) -> tuple[str, ...]:
    """Extract unique port/range tokens from strategy ``--filter-*`` args."""

    prefix = f"{option}="
    ports: list[str] = []
    seen: set[str] = set()
    for arg in runtime_args:
        if not arg.startswith(prefix):
            continue
        for raw_token in arg[len(prefix) :].split(","):
            token = raw_token.strip()
            if not _valid_port_token(token) or token in seen:
                continue
            seen.add(token)
            ports.append(token)
    return tuple(ports)



def _valid_ip_token(value: str) -> bool:
    """Return whether a capture-policy edge token is safe for nft IP sets."""

    token = value.strip()
    if not token:
        return False
    try:
        ipaddress.ip_network(token, strict=False)
    except ValueError:
        return False
    return True


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        token = str(item).strip()
        if not token or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return tuple(result)


def _capture_policy_ports(policy: dict[str, Any] | None, key: str) -> tuple[str, ...]:
    ports: list[str] = []
    seen: set[str] = set()
    for token in _string_list((policy or {}).get(key)):
        if not _valid_port_token(token) or token in seen:
            continue
        seen.add(token)
        ports.append(token)
    return tuple(ports)


def _capture_policy_edge_ips(policy: dict[str, Any] | None) -> tuple[str, ...]:
    edge_ips: list[str] = []
    seen: set[str] = set()
    for token in _string_list((policy or {}).get("edgeIps")):
        if not _valid_ip_token(token) or token in seen:
            continue
        seen.add(token)
        edge_ips.append(token)
    return tuple(edge_ips)


def _nft_ip_set(values: tuple[str, ...]) -> str:
    return ", ".join(values)

def _nft_port_set(ports: tuple[str, ...]) -> str:
    return ", ".join(ports)


def _parse_non_negative_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value, 10)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _runtime_owner_uid(root: Path) -> tuple[int, str]:
    return runtime_owner_uid(root)


def _nft_common_filter(owner_uid: int) -> str:
    return f"meta skuid {owner_uid} meta mark & {DEFAULT_DESYNC_MARK} == 0"


def _nft_apply_commands(
    table: str,
    chain: str,
    qnum: int,
    tcp_ports: tuple[str, ...],
    udp_ports: tuple[str, ...],
    owner_uid: int,
    owner_marker: str,
    *,
    edge_ips: tuple[str, ...] = (),
    queue_input_syn_ack: bool = False,
    queue_input_fin_rst: bool = False,
) -> tuple[RuntimeApplyCommand, ...]:
    common_filter = _nft_common_filter(owner_uid)
    edge_out_filter = f" ip daddr {{ {_nft_ip_set(edge_ips)} }}" if edge_ips else ""
    edge_in_filter = f" ip saddr {{ {_nft_ip_set(edge_ips)} }}" if edge_ips else ""
    commands: list[RuntimeApplyCommand] = [
        RuntimeApplyCommand(
            label="nft-add-table",
            argv=("nft", "add", "table", "inet", table),
            requires_sudo=True,
            mutates_system=True,
            description="Создать отдельную nftables table, принадлежащую owner UID + workspace + profile.",
        ),
        RuntimeApplyCommand(
            label="nft-add-owner-meta-chain",
            argv=("nft", "add", "chain", "inet", table, "owner_meta"),
            requires_sudo=True,
            mutates_system=True,
            description="Создать служебную chain с доказуемым owner marker.",
        ),
        RuntimeApplyCommand(
            label="nft-add-owner-marker",
            argv=("nft", "add", "rule", "inet", table, "owner_meta", f'counter comment "{owner_marker}"'),
            requires_sudo=True,
            mutates_system=True,
            description="Записать owner marker; revert разрешён только при его совпадении.",
        ),
        RuntimeApplyCommand(
            label="nft-add-local-out-chain",
            argv=("nft", "add", "chain", "inet", table, chain, "{ type filter hook output priority filter; policy accept; }"),
            requires_sudo=True,
            mutates_system=True,
            description="Создать OUTPUT chain только внутри нашей table для owner-scoped NFQUEUE правил.",
        ),
    ]
    if queue_input_syn_ack or queue_input_fin_rst:
        commands.append(
            RuntimeApplyCommand(
                label="nft-add-local-in-chain",
                argv=("nft", "add", "chain", "inet", table, DEFAULT_NFT_INPUT_CHAIN, "{ type filter hook input priority filter; policy accept; }"),
                requires_sudo=True,
                mutates_system=True,
                description="Создать INPUT chain для opt-in early-flow диагностики reverse-direction TCP ответов.",
            )
        )
    if tcp_ports:
        tcp_set = _nft_port_set(tcp_ports)
        commands.append(
            RuntimeApplyCommand(
                label="nft-queue-tcp-strategy",
                argv=("nft", "add", "rule", "inet", table, chain, f'{common_filter}{edge_out_filter} tcp dport {{ {tcp_set} }} ct original packets {DEFAULT_TCP_ORIGINAL_PACKET_RANGE} counter queue num {qnum} bypass comment "zap2:{table}:tcp-out"'),
                requires_sudo=True,
                mutates_system=True,
                description=f"Отправить TCP владельца UID {owner_uid} ({tcp_set}) в NFQUEUE с loop-guard mark, counters и queue-bypass.",
            )
        )
        if queue_input_syn_ack:
            commands.append(
                RuntimeApplyCommand(
                    label="nft-queue-input-synack-diagnostic",
                    argv=("nft", "add", "rule", "inet", table, DEFAULT_NFT_INPUT_CHAIN, f'{edge_in_filter} tcp sport {{ {tcp_set} }} tcp flags & (syn|ack) == (syn|ack) counter queue num {qnum} bypass comment "zap2:{table}:tcp-in-synack"'),
                    requires_sudo=True,
                    mutates_system=True,
                    description="Opt-in diagnostic queue for inbound SYN+ACK packets from early-flow edge IPs.",
                )
            )
        if queue_input_fin_rst:
            commands.append(
                RuntimeApplyCommand(
                    label="nft-queue-input-fin-rst-diagnostic",
                    argv=("nft", "add", "rule", "inet", table, DEFAULT_NFT_INPUT_CHAIN, f'{edge_in_filter} tcp sport {{ {tcp_set} }} tcp flags & (fin|rst) != 0 counter queue num {qnum} bypass comment "zap2:{table}:tcp-in-fin-rst"'),
                    requires_sudo=True,
                    mutates_system=True,
                    description="Opt-in diagnostic queue for inbound FIN/RST packets from early-flow edge IPs.",
                )
            )
    if udp_ports:
        udp_set = _nft_port_set(udp_ports)
        commands.append(
            RuntimeApplyCommand(
                label="nft-queue-udp-strategy",
                argv=("nft", "add", "rule", "inet", table, chain, f'{common_filter}{edge_out_filter} udp dport {{ {udp_set} }} ct original packets {DEFAULT_UDP_ORIGINAL_PACKET_RANGE} counter queue num {qnum} bypass comment "zap2:{table}:udp-out"'),
                requires_sudo=True,
                mutates_system=True,
                description=f"Отправить UDP владельца UID {owner_uid} ({udp_set}) в NFQUEUE с loop-guard mark, counters и queue-bypass.",
            )
        )
    return tuple(commands)

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
    strategy = strategies[profile.strategy_id]
    capture_policy = strategy.capture_policy or None
    if capture_policy is not None and "tcpOutPorts" in capture_policy:
        tcp_ports = _capture_policy_ports(capture_policy, "tcpOutPorts")
    else:
        tcp_ports = _ports_from_strategy_args(strategy.runtime_args, "--filter-tcp") or DEFAULT_TCP_PORTS
    if capture_policy is not None and "udpOutPorts" in capture_policy:
        udp_ports = _capture_policy_ports(capture_policy, "udpOutPorts")
    else:
        udp_ports = _ports_from_strategy_args(strategy.runtime_args, "--filter-udp")
    edge_ips = _capture_policy_edge_ips(capture_policy)
    queue_input_syn_ack = bool((capture_policy or {}).get("queueInputSynAck", False))
    queue_input_fin_rst = bool((capture_policy or {}).get("queueInputFinRst", False))
    identity = runtime_owner_identity(layout.root, profile.profile_id)
    owner_uid, owner_uid_source = identity.uid, identity.uid_source
    table = _nft_table_name(layout.root, profile.profile_id)
    plan_id = f"runtime-{profile.profile_id}-{profile.strategy_id}-{action}-owner-rules-plan"
    queue = resolve_runtime_queue(layout.root, profile.profile_id)
    commands = (
        _nft_apply_commands(
            table,
            DEFAULT_NFT_CHAIN,
            queue.qnum,
            tcp_ports,
            udp_ports,
            owner_uid,
            identity.marker,
            edge_ips=edge_ips,
            queue_input_syn_ack=queue_input_syn_ack,
            queue_input_fin_rst=queue_input_fin_rst,
        )
        if action == "apply"
        else _nft_revert_commands(table)
    )
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
        nfqueue_num=queue.qnum,
        queued_tcp_ports=tcp_ports if action == "apply" else (),
        queued_udp_ports=udp_ports if action == "apply" else (),
        queued_edge_ips=edge_ips if action == "apply" else (),
        capture_policy=capture_policy if action == "apply" else None,
        queue_input_syn_ack=queue_input_syn_ack if action == "apply" else False,
        queue_input_fin_rst=queue_input_fin_rst if action == "apply" else False,
        owner_uid=owner_uid,
        owner_uid_source=owner_uid_source,
        owner_key=identity.owner_key,
        owner_marker=identity.marker,
        desync_mark=DEFAULT_DESYNC_MARK,
        commands=commands,
        rollback_notes=rollback_notes,
        binary_relative_path=start_plan.binary_relative_path,
        hostlists=tuple(hostlist.path for hostlist in start_plan.hostlists),
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
            "metadata": {"profileId": profile_id, "engine": "nftables", "nftTable": plan.nft_table, "nfqueueNum": plan.nfqueue_num, "ownerUid": plan.owner_uid, "ownerKey": plan.owner_key, "queuedTcpPorts": list(plan.queued_tcp_ports), "queuedUdpPorts": list(plan.queued_udp_ports), "queuedEdgeIps": list(plan.queued_edge_ips), "capturePolicy": plan.capture_policy or {}, "nftCountersEnabled": True},
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


def _saved_command(item: dict[str, Any]) -> RuntimeApplyCommand:
    argv = item.get("argv")
    if not isinstance(argv, list) or not all(isinstance(part, str) for part in argv):
        raise ValueError("Saved owner-rules plan повреждён: command.argv должен быть списком строк")
    return RuntimeApplyCommand(
        label=str(item.get("label", "saved-command")),
        argv=tuple(argv),
        requires_sudo=bool(item.get("requiresSudo", True)),
        mutates_system=bool(item.get("mutatesSystem", True)),
        description=str(item.get("description", "Команда из подтверждённого owner-rules plan.")),
        ignore_missing_on_revert=bool(item.get("ignoreMissingOnRevert", False)),
    )


def _saved_commands(saved: dict[str, Any]) -> tuple[RuntimeApplyCommand, ...]:
    raw_commands = saved.get("commands")
    if not isinstance(raw_commands, list):
        raise ValueError("Saved owner-rules plan повреждён: commands отсутствуют")
    return tuple(_saved_command(item) for item in raw_commands if isinstance(item, dict))


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
    if saved.get("marker") != APPLY_MARKER:
        raise ValueError("Prepared owner-rules plan имеет неизвестный marker")
    if saved.get("action") != expected.action or saved.get("profileId") != expected.profile_id or saved.get("strategyId") != expected.strategy_id:
        raise ValueError("Prepared owner-rules plan не соответствует запрошенному action/profile/strategy")
    saved_hash = plan_payload_hash(_payload_without_runtime_fields(saved))
    if saved.get("planHash") != saved_hash:
        raise ValueError("Saved owner-rules plan hash не совпадает с содержимым плана")
    if saved.get("confirmed") is not True:
        raise ValueError("Prepared owner-rules plan ещё не подтверждён owner confirmation")
    if confirmation.get("planHash") != saved_hash or confirmation.get("confirmedByOwner") is not True:
        raise ValueError("Confirmation не соответствует сохранённому owner-rules plan hash")
    _saved_commands(saved)
    return saved, saved_hash


def _missing_table_is_ok(result: RuntimeCommandResult) -> bool:
    text = f"{result.stdout}\n{result.stderr}".lower()
    return result.returncode != 0 and ("no such file" in text or "no such table" in text or "not found" in text)




def _nft_batch_line(command: RuntimeApplyCommand) -> str:
    if not command.argv or command.argv[0] != "nft":
        raise ValueError(f"Unexpected non-nft runtime command: {command.argv}")
    return " ".join(command.argv[1:])


def _apply_batch_text(
    commands: tuple[RuntimeApplyCommand, ...],
    *,
    table_exists: bool,
    legacy_table_to_delete: str | None = None,
) -> str:
    lines: list[str] = []
    if legacy_table_to_delete:
        lines.append(f"delete table inet {legacy_table_to_delete}")
    for command in commands:
        if table_exists and command.label == "nft-add-table":
            lines.append(f"flush table inet {command.argv[4]}")
            continue
        lines.append(_nft_batch_line(command))
    return "\n".join(lines) + "\n"


def _revert_batch_text(table: str) -> str:
    return f"delete table inet {table}\n"


def _table_probe(runner: CommandRunner, table: str) -> RuntimeCommandResult:
    return runner(("nft", "list", "table", "inet", table))


def _table_probe_missing(result: RuntimeCommandResult) -> bool:
    return result.returncode != 0 and _missing_table_is_ok(result)


def _table_has_owner_marker(result: RuntimeCommandResult, owner_marker: str) -> bool:
    return result.ok and owner_marker in f"{result.stdout}\n{result.stderr}"


def _write_nft_transaction(paths: Any, profile_id: str, plan_hash: str, action: str, text: str) -> Path:
    path = paths.transactions_dir / f"{profile_id}.{action}.{plan_hash[:12]}.nft"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


@contextmanager
def _runtime_owner_lock(paths: Any, owner_key: str, profile_id: str):
    lock_path = paths.locks_dir / f"{owner_key}.{profile_id}.lock"
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield lock_path
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()

@dataclass(frozen=True)
class RuntimeOwnerReconciliation:
    """Read-only comparison of saved owner state and observed nft resources."""

    state: str
    profile_id: str
    nft_table: str
    owner_key: str
    state_path: Path
    observed_table: bool | None
    owner_marker_matches: bool | None
    message: str

    def to_text(self) -> str:
        observed = "unknown" if self.observed_table is None else ("yes" if self.observed_table else "no")
        marker = "unknown" if self.owner_marker_matches is None else ("yes" if self.owner_marker_matches else "no")
        return "\n".join([
            f"Runtime owner reconciliation: {self.state}",
            f"profile: {self.profile_id}",
            f"nft table: inet {self.nft_table}",
            f"owner key: {self.owner_key}",
            f"observed table: {observed}",
            f"owner marker matches: {marker}",
            f"saved state: {self.state_path}",
            f"message: {self.message}",
            "mutates firewall/services now: no",
            "automatic cleanup: no",
        ])


def reconcile_runtime_owner_rules(
    root: Path | None = None,
    profile_id: str = "default",
    *,
    runner: CommandRunner | None = None,
) -> RuntimeOwnerReconciliation:
    """Observe owned nft resources without changing them.

    Unknown or conflicting ownership is never treated as stopped and never
    triggers automatic deletion.  A cleanup-required result can be recovered
    through the normal owner-confirmed revert plan.
    """

    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    expected = create_runtime_apply_plan(paths.root, action="apply", profile_id=profile_id)
    state_path = paths.sessions_dir / f"{profile_id}.owner-rules.json"
    saved: dict[str, Any] | None = None
    if state_path.is_file():
        try:
            loaded = _read_json(state_path)
            if isinstance(loaded, dict):
                saved = loaded
        except (OSError, ValueError, json.JSONDecodeError):
            return RuntimeOwnerReconciliation(
                state="unknown", profile_id=profile_id, nft_table=expected.nft_table,
                owner_key=expected.owner_key, state_path=state_path, observed_table=None,
                owner_marker_matches=None, message="saved owner-rules state is unreadable; no cleanup was attempted",
            )

    if runner is None:
        if shutil.which("nft") is None:
            return RuntimeOwnerReconciliation(
                state="unknown", profile_id=profile_id, nft_table=expected.nft_table,
                owner_key=expected.owner_key, state_path=state_path, observed_table=None,
                owner_marker_matches=None, message="nft command is unavailable; observed firewall state is unknown",
            )
        runner = _default_runner

    try:
        probe = _table_probe(runner, expected.nft_table)
    except OSError as exc:
        return RuntimeOwnerReconciliation(
            state="unknown", profile_id=profile_id, nft_table=expected.nft_table,
            owner_key=expected.owner_key, state_path=state_path, observed_table=None,
            owner_marker_matches=None, message=f"could not inspect nft table: {exc}",
        )

    if _table_probe_missing(probe):
        saved_applied = bool(saved and saved.get("state") == "applied")
        return RuntimeOwnerReconciliation(
            state="stale-state" if saved_applied else "clean", profile_id=profile_id,
            nft_table=expected.nft_table, owner_key=expected.owner_key, state_path=state_path,
            observed_table=False, owner_marker_matches=None,
            message=("saved state says applied but the owned table is absent; state is stale, firewall cleanup is not required"
                     if saved_applied else "owned nft table is absent"),
        )
    if not probe.ok:
        return RuntimeOwnerReconciliation(
            state="unknown", profile_id=profile_id, nft_table=expected.nft_table,
            owner_key=expected.owner_key, state_path=state_path, observed_table=None,
            owner_marker_matches=None, message="nft table could not be inspected; ownership is unknown",
        )

    marker_matches = _table_has_owner_marker(probe, expected.owner_marker)
    if not marker_matches:
        return RuntimeOwnerReconciliation(
            state="conflict", profile_id=profile_id, nft_table=expected.nft_table,
            owner_key=expected.owner_key, state_path=state_path, observed_table=True,
            owner_marker_matches=False, message="table name exists but owner marker differs; automatic cleanup is refused",
        )

    saved_matches = bool(
        saved
        and saved.get("state") == "applied"
        and saved.get("ownerKey") == expected.owner_key
        and saved.get("nftTable") == expected.nft_table
    )
    return RuntimeOwnerReconciliation(
        state="consistent-applied" if saved_matches else "cleanup-required",
        profile_id=profile_id, nft_table=expected.nft_table, owner_key=expected.owner_key,
        state_path=state_path, observed_table=True, owner_marker_matches=True,
        message=("saved state and observed owned table agree" if saved_matches
                 else "owned table exists without matching applied state; use the normal confirmed revert workflow for explicit recovery"),
    )


def _saved_owner_rules_state(paths: Any, profile_id: str) -> dict[str, Any] | None:
    state_path = paths.sessions_dir / f"{profile_id}.owner-rules.json"
    if not state_path.exists():
        return None
    try:
        return _read_json(state_path)
    except Exception:
        return None


def _legacy_table_is_proven_owned(paths: Any, profile_id: str, expected: RuntimeApplyPlan, legacy_table: str) -> bool:
    """Return True only for an applied legacy state owned by this workspace user/profile.

    Old builds had no workspace digest in the table name, so the table itself is
    not enough proof.  We require the old state file, marker, profile, owner UID
    and exact legacy table name before a migration is allowed to delete it.
    """

    state = _saved_owner_rules_state(paths, profile_id)
    if state is None:
        return False
    return bool(
        state.get("marker") == APPLY_MARKER
        and state.get("state") == "applied"
        and state.get("profileId") == profile_id
        and state.get("nftTable") == legacy_table
        and int(state.get("ownerUid", -1)) == int(expected.owner_uid)
    )


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
    expected = create_runtime_apply_plan(paths.root, action=action, profile_id=profile_id)
    saved, plan_hash = _load_confirmed_plan(paths.root, expected, confirm_plan_id)
    commands = _saved_commands(saved)
    if runner is None:
        if shutil.which("nft") is None:
            raise ValueError("Команда nft не найдена. Установите nftables или используйте другой будущий apply backend.")
        runner = _default_runner
    if not allow_without_root and not _is_root():
        raise ValueError("Runtime apply/revert требует root. Запустите owner-confirmed команду через sudo на своей машине.")

    results: list[RuntimeCommandResult] = []
    state = "applied" if action == "apply" else "reverted"
    message = f"owner-confirmed {action} completed"
    saved_table = str(saved.get("nftTable", expected.nft_table))
    owner_key = str(saved.get("ownerKey", expected.owner_key))
    owner_marker = str(saved.get("ownerMarker", expected.owner_marker))
    transaction_path: Path | None = None
    legacy_table = _legacy_nft_table_name(profile_id)
    legacy_table_migrated: str | None = None
    prior_owner_state = _saved_owner_rules_state(paths, profile_id)

    with _runtime_owner_lock(paths, owner_key, profile_id):
        probe = _table_probe(runner, saved_table)
        results.append(probe)
        table_missing = _table_probe_missing(probe)
        if action == "apply":
            if not table_missing and not probe.ok:
                state = "failed"
                message = "could not inspect existing nft table before apply"
            elif probe.ok and not _table_has_owner_marker(probe, owner_marker):
                state = "conflict"
                message = "nft table exists but owner marker does not match; refusing to reuse or delete it"
            else:
                legacy_delete: str | None = None
                should_probe_legacy = legacy_table != saved_table and (
                    prior_owner_state is None or str(prior_owner_state.get("nftTable", "")) == legacy_table
                )
                if should_probe_legacy:
                    legacy_probe = _table_probe(runner, legacy_table)
                    results.append(legacy_probe)
                    legacy_missing = _table_probe_missing(legacy_probe)
                    if not legacy_missing and not legacy_probe.ok:
                        state = "failed"
                        message = "could not inspect legacy nft table before apply"
                    elif legacy_probe.ok:
                        if _legacy_table_is_proven_owned(paths, profile_id, expected, legacy_table):
                            legacy_delete = legacy_table
                        else:
                            state = "conflict"
                            message = (
                                f"legacy nft table inet {legacy_table} exists but ownership cannot be proven from old applied state; "
                                "automatic deletion is refused"
                            )
                if state == "applied":
                    batch = _apply_batch_text(commands, table_exists=probe.ok, legacy_table_to_delete=legacy_delete)
                    transaction_path = _write_nft_transaction(paths, profile_id, plan_hash, action, batch)
                    check_result = runner(("nft", "--check", "-f", str(transaction_path)))
                    results.append(check_result)
                    if not check_result.ok:
                        state = "failed"
                        message = "nft transaction precheck failed; existing rules were not changed"
                    else:
                        apply_batch_result = runner(("nft", "-f", str(transaction_path)))
                        results.append(apply_batch_result)
                        if not apply_batch_result.ok:
                            state = "failed"
                            message = "nft transaction failed; nftables rejected the batch"
                        elif legacy_delete:
                            legacy_table_migrated = legacy_delete
                            message = f"owner-confirmed apply completed; migrated legacy nft table inet {legacy_delete}"
        else:
            if table_missing:
                state = "reverted"
                message = "owned nft table was already missing; revert considered safe"
            elif not probe.ok:
                state = "failed"
                message = "could not inspect nft table before revert"
            elif not _table_has_owner_marker(probe, owner_marker):
                state = "conflict"
                message = "nft table owner marker does not match; revert refused"
            else:
                batch = _revert_batch_text(saved_table)
                transaction_path = _write_nft_transaction(paths, profile_id, plan_hash, action, batch)
                check_result = runner(("nft", "--check", "-f", str(transaction_path)))
                results.append(check_result)
                if not check_result.ok:
                    state = "failed"
                    message = "nft revert precheck failed; owned table was left intact"
                else:
                    revert_result = runner(("nft", "-f", str(transaction_path)))
                    results.append(revert_result)
                    if not revert_result.ok:
                        state = "failed"
                        message = "nft revert transaction failed"

    state_path = paths.sessions_dir / f"{profile_id}.owner-rules.json"
    state_record = {
        "schemaVersion": APPLY_SCHEMA_VERSION,
        "stage": APPLY_STAGE,
        "marker": APPLY_MARKER,
        "state": state,
        "action": action,
        "profileId": profile_id,
        "strategyId": str(saved.get("strategyId", expected.strategy_id)),
        "planId": str(saved.get("planId", expected.plan_id)),
        "planHash": plan_hash,
        "engine": "nftables",
        "nftTable": str(saved.get("nftTable", expected.nft_table)),
        "nfqueueNum": int(saved.get("nfqueueNum", expected.nfqueue_num)),
        "queuedTcpPorts": list(saved.get("queuedTcpPorts", list(expected.queued_tcp_ports))),
        "queuedUdpPorts": list(saved.get("queuedUdpPorts", list(expected.queued_udp_ports))),
        "queuedEdgeIps": list(saved.get("queuedEdgeIps", list(expected.queued_edge_ips))),
        "capturePolicy": dict(saved.get("capturePolicy", expected.capture_policy or {})),
        "queueInputSynAck": bool(saved.get("queueInputSynAck", expected.queue_input_syn_ack)),
        "queueInputFinRst": bool(saved.get("queueInputFinRst", expected.queue_input_fin_rst)),
        "nftCountersEnabled": bool(saved.get("nftCountersEnabled", True)),
        "ownerUid": int(saved.get("ownerUid", expected.owner_uid)),
        "ownerUidSource": str(saved.get("ownerUidSource", expected.owner_uid_source)),
        "ownerKey": owner_key,
        "ownerMarker": owner_marker,
        "transactionPath": str(transaction_path.relative_to(paths.root)) if transaction_path is not None else None,
        "legacyNftTableMigrated": legacy_table_migrated,
        "desyncMark": str(saved.get("desyncMark", expected.desync_mark)),
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
    saved_plan_id = str(saved.get("planId", expected.plan_id))
    saved_nft_table = str(saved.get("nftTable", expected.nft_table))
    saved_owner_uid = int(saved.get("ownerUid", expected.owner_uid))
    log_path = append_runtime_event(
        paths,
        {
            "schemaVersion": APPLY_SCHEMA_VERSION,
            "stage": APPLY_STAGE,
            "eventId": f"owner-rules-{action}-{state}-{saved_plan_id}-{plan_hash[:12]}",
            "eventType": f"owner-rules-{action}-{state}",
            "level": "info" if state in {"applied", "reverted"} else "error",
            "planId": saved_plan_id,
            "planHash": plan_hash,
            "message": message,
            "createdAt": _utc_now(),
            "metadata": {"profileId": profile_id, "engine": "nftables", "nftTable": saved_nft_table, "ownerUid": saved_owner_uid, "ownerKey": owner_key, "statePath": str(state_path.relative_to(paths.root))},
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
        plan_id=str(saved.get("planId", expected.plan_id)),
        plan_hash=plan_hash,
        executed_commands=tuple(results),
        state_path=state_path,
        log_path=log_path,
        message=message,
    )
