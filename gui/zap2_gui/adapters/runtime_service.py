"""Service plans для controlled runtime lifecycle.

Stage 13 добавляет service mode как отдельный режим, не смешивая его с
session mode и bootstrap. Модуль умеет:

* строить и сохранять service plans для install/start/stop/remove;
* привязывать guarded install/remove execution к существующему planHash
  confirmation gate;
* генерировать systemd unit как данные;
* выполнять install/remove только явно, локально и после owner confirmation.

Автоматические проверки не вызывают настоящий systemctl, не пишут в
/etc/systemd/system и не требуют root. Тесты используют временную service-dir и
fake runner.
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
from .runtime_queue import resolve_nfqueue_num
from .runtime_state import PreparedRuntimePlan, append_runtime_event, ensure_runtime_store, plan_payload_hash
from .workspace_profiles import load_workspace_catalog
from ..project_paths import discover_layout

SERVICE_STAGE = "v0.3-alpha_stage_13"
SERVICE_SCHEMA_VERSION = 1
SERVICE_MARKER = "zap2-runtime-service-v1"
SUPPORTED_SERVICE_PLAN_ACTIONS = ("install", "start", "stop", "remove")
SUPPORTED_SERVICE_EXECUTION_ACTIONS = ("install", "remove")
DEFAULT_SERVICE_DIR = Path("/etc/systemd/system")
DEFAULT_DESYNC_MARK = "0x40000000"

ServicePlanAction = Literal["install", "start", "stop", "remove"]
ServiceExecutionAction = Literal["install", "remove"]
CommandRunner = Callable[[tuple[str, ...]], "ServiceCommandResult"]


@dataclass(frozen=True)
class ServicePlanCommand:
    """Одна команда/операция service plan как данные."""

    label: str
    argv: tuple[str, ...]
    requires_sudo: bool
    mutates_system: bool
    description: str
    ignore_failure_on_remove: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "argv": list(self.argv),
            "requiresSudo": self.requires_sudo,
            "mutatesSystem": self.mutates_system,
            "description": self.description,
            "ignoreFailureOnRemove": self.ignore_failure_on_remove,
        }


@dataclass(frozen=True)
class ServicePlan:
    """Service plan для systemd mode, отделённый от session runner."""

    action: ServicePlanAction
    profile_id: str
    strategy_id: str
    plan_id: str
    service_name: str
    service_dir: Path
    unit_path: Path
    args_path: Path
    pidfile_path: Path
    debug_log_path: Path
    binary_path: Path
    hostlist_paths: tuple[Path, ...]
    unit_content: str
    args_content: str
    commands: tuple[ServicePlanCommand, ...]
    rollback_notes: tuple[str, ...]

    @property
    def requires_sudo(self) -> bool:
        return any(command.requires_sudo for command in self.commands)

    @property
    def mutates_service(self) -> bool:
        return any(command.mutates_system for command in self.commands)

    @property
    def can_execute_now(self) -> bool:
        return self.action in SUPPORTED_SERVICE_EXECUTION_ACTIONS

    def to_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": SERVICE_SCHEMA_VERSION,
            "stage": SERVICE_STAGE,
            "marker": SERVICE_MARKER,
            "planId": self.plan_id,
            "action": self.action,
            "profileId": self.profile_id,
            "strategyId": self.strategy_id,
            "serviceManager": "systemd",
            "serviceName": self.service_name,
            "serviceDir": str(self.service_dir),
            "unitPath": str(self.unit_path),
            "argsPath": str(self.args_path),
            "pidfilePath": str(self.pidfile_path),
            "debugLogPath": str(self.debug_log_path),
            "binaryPath": str(self.binary_path),
            "hostlists": [str(path) for path in self.hostlist_paths],
            "unitContent": self.unit_content,
            "argsContent": self.args_content,
            "commands": [command.to_dict() for command in self.commands],
            "rollbackNotes": list(self.rollback_notes),
            "safety": {
                "requiresOwnerConfirmation": True,
                "requiresSudoWhenExecutedByOwner": self.requires_sudo,
                "mutatesServiceWhenExecutedByOwner": self.mutates_service,
                "mutatesFirewallWhenExecutedByOwner": False,
                "containsRemoteBootstrap": False,
                "containsUpstreamInstallerScript": False,
                "automaticChecksMayExecute": False,
                "bootstrapMixedIn": False,
                "defaultWorkflow": False,
                "separateFromSessionMode": True,
            },
            "execution": {
                "executesNow": False,
                "guardedExecutionAvailable": self.can_execute_now,
                "automaticChecksMayExecute": False,
            },
        }

    def to_text(self) -> str:
        command_lines = [
            f"  - {command.label}: {' '.join(command.argv)}; requires sudo: {'yes' if command.requires_sudo else 'no'}; mutates service: {'yes' if command.mutates_system else 'no'}"
            for command in self.commands
        ]
        rollback_lines = [f"  - {note}" for note in self.rollback_notes]
        return "\n".join(
            [
                f"Service plan для action: {self.action}",
                f"profile: {self.profile_id}",
                f"strategy: {self.strategy_id}",
                f"plan id: {self.plan_id}",
                f"service manager: systemd",
                f"service name: {self.service_name}",
                f"unit path: {self.unit_path}",
                f"binary: {self.binary_path}",
                f"args file: {self.args_path}",
                "commands:",
                *(command_lines or ["  - нет"]),
                "rollback notes:",
                *(rollback_lines or ["  - нет"]),
                "requires owner confirmation: yes",
                f"requires sudo when executed by owner: {'yes' if self.requires_sudo else 'no'}",
                f"mutates service when executed by owner: {'yes' if self.mutates_service else 'no'}",
                "mutates firewall when executed by owner: no",
                "service mode is default workflow: no",
                "separate from session mode: yes",
                "contains remote bootstrap: no",
                "contains upstream installer script: no",
                "automatic checks may execute: no",
                "executes now: no",
                f"guarded execution available: {'yes' if self.can_execute_now else 'no'}",
            ]
        )


@dataclass(frozen=True)
class ServiceCommandResult:
    """Результат одной systemd/service команды."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class ServiceExecutionResult:
    """CLI-friendly результат guarded service execution."""

    action: ServiceExecutionAction
    state: str
    profile_id: str
    plan_id: str
    plan_hash: str
    service_name: str
    unit_path: Path
    state_path: Path
    log_path: Path
    executed_commands: tuple[ServiceCommandResult, ...]
    message: str

    def to_text(self) -> str:
        lines = [
            f"Service {self.action}: {self.state}",
            f"profile: {self.profile_id}",
            f"service name: {self.service_name}",
            f"plan id: {self.plan_id}",
            f"plan hash: {self.plan_hash}",
            f"unit path: {self.unit_path}",
            f"service state: {self.state_path}",
            f"runtime log: {self.log_path}",
            f"message: {self.message}",
            "executed commands:",
        ]
        for result in self.executed_commands:
            lines.append(f"  - rc={result.returncode}: {' '.join(result.argv)}")
            if result.stderr:
                lines.append(f"    stderr: {result.stderr.strip()}")
        lines.extend(
            [
                "owner confirmation verified: yes",
                "mutates service now: yes",
                "mutates firewall now: no",
                "service mode is default workflow: no",
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


def _safe_profile_slug(profile_id: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in profile_id.lower()).strip("-") or "default"


def _service_name(profile_id: str) -> str:
    return f"zap2-{_safe_profile_slug(profile_id)}.service"


def _args_content(pidfile_path: Path, debug_log_path: Path, hostlists: tuple[Path, ...], qnum: int) -> str:
    lines = [
        f"--qnum={qnum}",
        f"--pidfile={pidfile_path}",
        f"--fwmark={DEFAULT_DESYNC_MARK}",
        f"--debug=@{debug_log_path}",
    ]
    if hostlists:
        lines.append(f"--hostlist={hostlists[0]}")
    return "\n".join(lines) + "\n"


def _unit_content(plan_id: str, profile_id: str, binary_path: Path, args_path: Path, cwd: Path) -> str:
    return "\n".join(
        [
            "[Unit]",
            f"Description=Zap2 runtime service for profile {profile_id}",
            "Documentation=file://" + str(cwd / "docs" / "RUNTIME_SERVICE_PLANS.md"),
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={cwd}",
            f"ExecStart={binary_path} @{args_path}",
            "Restart=on-failure",
            "RestartSec=3",
            "KillSignal=SIGTERM",
            f"Environment=ZAP2_PROFILE={profile_id}",
            f"Environment=ZAP2_SERVICE_PLAN_ID={plan_id}",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


def _commands(action: ServicePlanAction, service_name: str, unit_path: Path) -> tuple[ServicePlanCommand, ...]:
    if action == "install":
        return (
            ServicePlanCommand("write-args-file", ("write-file", "<workspace-args-file>"), False, False, "Создать workspace args-file для nfqws2 service mode."),
            ServicePlanCommand("write-systemd-unit", ("write-file", str(unit_path)), True, True, "Записать systemd unit в выбранную service-dir."),
            ServicePlanCommand("systemd-daemon-reload", ("systemctl", "daemon-reload"), True, True, "Перечитать unit-файлы systemd после install."),
        )
    if action == "start":
        return (
            ServicePlanCommand("systemd-start", ("systemctl", "start", service_name), True, True, "Запустить уже установленный service."),
        )
    if action == "stop":
        return (
            ServicePlanCommand("systemd-stop", ("systemctl", "stop", service_name), True, True, "Остановить service без удаления unit-файла."),
        )
    if action == "remove":
        return (
            ServicePlanCommand("systemd-stop", ("systemctl", "stop", service_name), True, True, "Остановить service перед удалением; отсутствие service не считается фатальным.", True),
            ServicePlanCommand("systemd-disable", ("systemctl", "disable", service_name), True, True, "Отключить автозапуск перед удалением; отсутствие enable-state не считается фатальным.", True),
            ServicePlanCommand("remove-systemd-unit", ("remove-file", str(unit_path)), True, True, "Удалить только unit-файл, созданный Zap2 service plan."),
            ServicePlanCommand("systemd-daemon-reload", ("systemctl", "daemon-reload"), True, True, "Перечитать systemd после удаления unit-файла."),
        )
    raise ValueError(f"Неизвестное service action: {action}")


def _rollback_notes(action: ServicePlanAction, service_name: str, unit_path: Path) -> tuple[str, ...]:
    if action == "install":
        return (
            f"Откат install выполняется service remove plan для {service_name}.",
            "Install не запускает service и не включает автозапуск по умолчанию.",
            f"Удалять можно только unit-файл {unit_path}, созданный этим plan.",
        )
    if action == "start":
        return (
            f"Откат start — service stop plan для {service_name}.",
            "Stage 13 не исполняет start автоматически; это только план service mode.",
        )
    if action == "stop":
        return (
            f"После stop можно снова выполнить start plan для {service_name}, если service был установлен.",
            "Stop не удаляет unit-файл и не чистит runtime logs.",
        )
    return (
        f"Remove удаляет только unit-файл {unit_path} и не трогает firewall/nftables rules.",
        "Если unit уже отсутствует, remove считается безопасным для повторения.",
        "Logs и rollback notes в .zap2/runtime не удаляются автоматически.",
    )


def create_service_plan(
    root: Path | None = None,
    action: ServicePlanAction = "install",
    profile_id: str = "default",
    service_dir: Path | str | None = None,
) -> ServicePlan:
    """Создаёт service plan как данные без исполнения."""

    if action not in SUPPORTED_SERVICE_PLAN_ACTIONS:
        raise ValueError(f"Неизвестное service action: {action}. Доступно: {', '.join(SUPPORTED_SERVICE_PLAN_ACTIONS)}")
    layout = discover_layout(root)
    catalog = load_workspace_catalog(layout.root)
    profiles = catalog.profile_by_id()
    if profile_id not in profiles:
        raise ValueError(f"Неизвестный workspace-профиль: {profile_id}")
    profile = profiles[profile_id]
    strategies = catalog.strategy_by_id()
    if profile.strategy_id not in strategies:
        raise ValueError(f"Профиль {profile.profile_id} ссылается на неизвестную стратегию: {profile.strategy_id}")
    start_plan = create_runtime_plan(layout.root, action="start", profile_id=profile_id)
    service_root = Path(service_dir) if service_dir is not None else DEFAULT_SERVICE_DIR
    service_name = _service_name(profile.profile_id)
    unit_path = service_root / service_name
    paths = ensure_runtime_store(layout.root)
    args_path = paths.sessions_dir / f"{profile.profile_id}.service.nfqws2.args"
    pidfile_path = paths.sessions_dir / f"{profile.profile_id}.service.nfqws2.pid"
    debug_log_path = paths.logs_dir / f"{profile.profile_id}.service.nfqws2.debug.log"
    hostlists = tuple((layout.root / hostlist.path).resolve() for hostlist in start_plan.hostlists)
    binary_path = (layout.root / start_plan.binary_relative_path).resolve()
    plan_id = f"runtime-{profile.profile_id}-{profile.strategy_id}-service-{action}-plan"
    args = _args_content(pidfile_path, debug_log_path, hostlists, resolve_nfqueue_num(layout.root, profile.profile_id))
    unit = _unit_content(plan_id, profile.profile_id, binary_path, args_path, layout.root)
    return ServicePlan(
        action=action,
        profile_id=profile.profile_id,
        strategy_id=profile.strategy_id,
        plan_id=plan_id,
        service_name=service_name,
        service_dir=service_root,
        unit_path=unit_path,
        args_path=args_path,
        pidfile_path=pidfile_path,
        debug_log_path=debug_log_path,
        binary_path=binary_path,
        hostlist_paths=hostlists,
        unit_content=unit,
        args_content=args,
        commands=_commands(action, service_name, unit_path),
        rollback_notes=_rollback_notes(action, service_name, unit_path),
    )


def service_plan_to_text(action: ServicePlanAction = "install", profile_id: str = "default", root: Path | None = None) -> str:
    return create_service_plan(root=root, action=action, profile_id=profile_id).to_text()


def _rollback_text(plan: ServicePlan, plan_hash: str) -> str:
    notes = "\n".join(f"- {note}" for note in plan.rollback_notes)
    commands = "\n".join(f"- `{' '.join(command.argv)}`" for command in plan.commands)
    return f"""# Rollback notes для {plan.plan_id}

- stage: `{SERVICE_STAGE}`
- plan hash: `{plan_hash}`
- action: `{plan.action}`
- profile: `{plan.profile_id}`
- strategy: `{plan.strategy_id}`
- service name: `{plan.service_name}`
- unit path: `{plan.unit_path}`
- firewall/nftables: не трогать
- bootstrap/install scripts: нет
- default workflow: нет

## Команды плана

{commands}

## Заметки отката

{notes}
"""


def prepare_service_plan(
    root: Path | None = None,
    action: ServicePlanAction = "install",
    profile_id: str = "default",
    service_dir: Path | str | None = None,
) -> PreparedRuntimePlan:
    """Сохраняет service plan в `.zap2/runtime`, но не исполняет его."""

    paths = ensure_runtime_store(root)
    plan = create_service_plan(paths.root, action=action, profile_id=profile_id, service_dir=service_dir)
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
            "schemaVersion": SERVICE_SCHEMA_VERSION,
            "stage": SERVICE_STAGE,
            "eventId": f"service-{action}-planned-{plan.plan_id}-{plan_hash[:12]}",
            "eventType": f"service-{action}-planned",
            "level": "info",
            "planId": plan.plan_id,
            "planHash": plan_hash,
            "message": f"Prepared service {action} plan for profile {profile_id}; service execution disabled until explicit --service-apply for supported actions.",
            "createdAt": _utc_now(),
            "metadata": {"profileId": profile_id, "serviceName": plan.service_name, "unitPath": str(plan.unit_path)},
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


def _default_runner(argv: tuple[str, ...]) -> ServiceCommandResult:
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return ServiceCommandResult(argv=argv, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)


def _is_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    return True if geteuid is None else geteuid() == 0


def _load_confirmed_service_plan(root: Path, expected: ServicePlan, confirm_plan_id: str) -> tuple[dict[str, Any], str]:
    paths = ensure_runtime_store(root)
    if not confirm_plan_id:
        raise ValueError("Для service execution нужен --confirm <plan-id>")
    if confirm_plan_id != expected.plan_id:
        raise ValueError(f"Передан не тот plan id: {confirm_plan_id}; ожидается {expected.plan_id}")
    plan_path = paths.plans_dir / f"{expected.plan_id}.json"
    confirmation_path = paths.confirmations_dir / f"{expected.plan_id}.confirmation.json"
    if not plan_path.exists():
        raise ValueError(f"Prepared service plan не найден: {expected.plan_id}. Сначала выполните --service-plan {expected.action}.")
    if not confirmation_path.exists():
        raise ValueError(f"Confirmation не найден для {expected.plan_id}. Сначала выполните --runtime-confirm {expected.plan_id}.")
    saved = _read_json(plan_path)
    confirmation = _read_json(confirmation_path)
    current_hash = plan_payload_hash(expected.to_payload())
    if saved.get("planHash") != current_hash:
        raise ValueError("Prepared service plan устарел: текущий planHash не совпадает с сохранённым")
    if saved.get("confirmed") is not True:
        raise ValueError("Prepared service plan ещё не подтверждён owner confirmation")
    if confirmation.get("planHash") != current_hash or confirmation.get("confirmedByOwner") is not True:
        raise ValueError("Confirmation не соответствует текущему service plan hash")
    return saved, current_hash


def _service_root_requires_root(service_dir: Path) -> bool:
    return service_dir.resolve() == DEFAULT_SERVICE_DIR.resolve()


def _run_command(command: ServicePlanCommand, runner: CommandRunner) -> ServiceCommandResult:
    if command.argv and command.argv[0] in {"write-file", "remove-file"}:
        return ServiceCommandResult(command.argv, 0)
    return runner(command.argv)


def execute_service_plan(
    root: Path | None = None,
    action: ServiceExecutionAction = "install",
    profile_id: str = "default",
    confirm_plan_id: str = "",
    *,
    service_dir: Path | str | None = None,
    runner: CommandRunner | None = None,
    allow_without_root: bool = False,
) -> ServiceExecutionResult:
    """Исполняет только подтверждённые service install/remove plans."""

    if action not in SUPPORTED_SERVICE_EXECUTION_ACTIONS:
        raise ValueError("Stage 13 исполняет только service install/remove; start/stop пока остаются plan-only")
    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    plan = create_service_plan(paths.root, action=action, profile_id=profile_id, service_dir=service_dir)
    _saved, plan_hash = _load_confirmed_service_plan(paths.root, plan, confirm_plan_id)
    if runner is None:
        if shutil.which("systemctl") is None:
            raise ValueError("Команда systemctl не найдена. Service execution требует systemd на локальной машине владельца.")
        runner = _default_runner
    if _service_root_requires_root(plan.service_dir) and not allow_without_root and not _is_root():
        raise ValueError("Service install/remove требует root для /etc/systemd/system. Запустите команду через sudo на своей машине.")

    plan.args_path.parent.mkdir(parents=True, exist_ok=True)
    results: list[ServiceCommandResult] = []
    state = "installed" if action == "install" else "removed"
    message = f"owner-confirmed service {action} completed"

    if action == "install":
        plan.args_path.write_text(plan.args_content, encoding="utf-8")
        plan.unit_path.parent.mkdir(parents=True, exist_ok=True)
        plan.unit_path.write_text(plan.unit_content, encoding="utf-8")
    elif action == "remove":
        # Сначала systemctl stop/disable, затем удаление только нашего unit-файла.
        pass

    for command in plan.commands:
        if action == "remove" and command.label == "remove-systemd-unit":
            if plan.unit_path.exists():
                plan.unit_path.unlink()
            result = ServiceCommandResult(command.argv, 0)
        elif action == "install" and command.label in {"write-args-file", "write-systemd-unit"}:
            result = ServiceCommandResult(command.argv, 0)
        else:
            result = _run_command(command, runner)
        results.append(result)
        if result.ok:
            continue
        if action == "remove" and command.ignore_failure_on_remove:
            state = "removed"
            message = "service stop/disable returned error but remove may proceed safely"
            continue
        state = "failed"
        message = f"service command failed: {command.label}"
        break

    state_path = paths.sessions_dir / f"{profile_id}.service.json"
    state_record = {
        "schemaVersion": SERVICE_SCHEMA_VERSION,
        "stage": SERVICE_STAGE,
        "marker": SERVICE_MARKER,
        "state": state,
        "action": action,
        "profileId": profile_id,
        "strategyId": plan.strategy_id,
        "planId": plan.plan_id,
        "planHash": plan_hash,
        "serviceManager": "systemd",
        "serviceName": plan.service_name,
        "serviceDir": str(plan.service_dir),
        "unitPath": str(plan.unit_path),
        "updatedAt": _utc_now(),
        "commands": [
            {"argv": list(item.argv), "returncode": item.returncode, "stdout": item.stdout, "stderr": item.stderr}
            for item in results
        ],
        "mutatesFirewallNow": False,
        "managesServiceNow": True,
        "defaultWorkflow": False,
        "containsRemoteBootstrap": False,
        "containsUpstreamInstallerScript": False,
    }
    _write_json(state_path, state_record)
    log_path = append_runtime_event(
        paths,
        {
            "schemaVersion": SERVICE_SCHEMA_VERSION,
            "stage": SERVICE_STAGE,
            "eventId": f"service-{action}-{state}-{plan.plan_id}-{plan_hash[:12]}",
            "eventType": f"service-{action}-{state}",
            "level": "info" if state in {"installed", "removed"} else "error",
            "planId": plan.plan_id,
            "planHash": plan_hash,
            "message": message,
            "createdAt": _utc_now(),
            "metadata": {"profileId": profile_id, "serviceName": plan.service_name, "unitPath": str(plan.unit_path), "statePath": str(state_path.relative_to(paths.root))},
            "executesNow": True,
            "mutatesFirewallOrServicesNow": True,
            "managesServiceNow": True,
        },
        profile_id=profile_id,
    )
    return ServiceExecutionResult(
        action=action,
        state=state,
        profile_id=profile_id,
        plan_id=plan.plan_id,
        plan_hash=plan_hash,
        service_name=plan.service_name,
        unit_path=plan.unit_path,
        state_path=state_path,
        log_path=log_path,
        executed_commands=tuple(results),
        message=message,
    )
