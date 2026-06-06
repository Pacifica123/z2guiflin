"""Owner-controlled default build workflow для v0.3-beta.

Stage `v0.3-beta_stage_2` добавляет dependency preflight поверх Stage 1: теперь workflow не должен доходить до compiler error, если заранее отсутствуют системные build dependencies. Stage 1 закрывал разрыв между default start workflow и
фактическим отсутствием локального бинарника `nfqws2`. Модуль не является
bootstrap-слоем: он не скачивает код, не вызывает upstream installer scripts,
не требует sudo и не меняет firewall/service state. Он только строит и, после
явного owner confirmation, исполняет локальный `make` для vendored-ядра.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .build_dependencies import (
    BuildDependencyReport,
    build_dependency_requirements_for_target,
    run_build_dependency_preflight,
)
from .local_build import BuildCommand, LocalBuildPlan, create_local_build_plan, inspect_artifacts
from .runtime_state import append_runtime_event, ensure_runtime_store, plan_payload_hash
from .workspace_profiles import load_workspace_catalog
from ..project_paths import discover_layout

DEFAULT_BUILD_STAGE = "v0.3-beta_stage_2"
DEFAULT_BUILD_SCHEMA_VERSION = 1
DEFAULT_BUILD_MARKER = "zap2-default-build-workflow-v1"

BuildCommandRunner = Callable[[Path, tuple[str, ...]], "DefaultBuildCommandResult"]


@dataclass(frozen=True)
class DefaultBuildCommandResult:
    """Результат одной команды локальной сборки."""

    cwd: Path
    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class DefaultBuildWorkflowPlan:
    """Сохранённый default build plan для профиля."""

    profile_id: str
    strategy_id: str
    build_target: str
    plan_id: str
    plan_hash: str
    plan_path: Path
    rollback_path: Path
    log_path: Path
    local_build_plan: LocalBuildPlan
    dependency_report: BuildDependencyReport

    @property
    def artifact_paths(self) -> tuple[Path, ...]:
        return tuple(item.absolute_path for item in self.local_build_plan.expected_artifacts)

    def to_text(self) -> str:
        command_lines = [f"  - {command.shell_preview()}" for command in self.local_build_plan.commands]
        artifact_lines = [f"  - {artifact.absolute_path}" for artifact in self.local_build_plan.expected_artifacts]
        libraries = ", ".join(self.local_build_plan.required_libraries_hint) or "нет явных подсказок"
        return "\n".join(
            [
                "Default build workflow plan",
                f"profile: {self.profile_id}",
                f"strategy: {self.strategy_id}",
                f"build target: {self.build_target}",
                f"plan id: {self.plan_id}",
                f"plan hash: {self.plan_hash}",
                "commands:",
                *(command_lines or ["  - нет"]),
                "expected artifacts:",
                *(artifact_lines or ["  - нет"]),
                f"libraries hint: {libraries}",
                "dependency preflight:",
                f"  status: {self.dependency_report.summary_line()}",
                *(f"  - {check.status}: {check.check_id} — {check.details}" for check in self.dependency_report.checks),
                "  executes install now: no",
                "  runs make now: no",
                f"plan file: {self.plan_path}",
                f"rollback notes: {self.rollback_path}",
                f"runtime log: {self.log_path}",
                "requires owner confirmation: yes",
                "requires sudo: no",
                "rejects sudo/root execution: yes",
                "mutates worktree when executed by owner: yes",
                "mutates services/firewall: no",
                "uses service mode: no",
                "bootstrap mixed in: no",
                "contains remote bootstrap: no",
                "contains upstream installer script: no",
                "automatic checks may execute: no",
                "executes now: no",
            ]
        )


@dataclass(frozen=True)
class DefaultBuildExecutionResult:
    """CLI-friendly результат подтверждённой локальной сборки."""

    state: str
    profile_id: str
    strategy_id: str
    build_target: str
    plan_id: str
    plan_hash: str
    executed_commands: tuple[DefaultBuildCommandResult, ...]
    artifact_status: tuple[tuple[Path, bool, bool, int | None], ...]
    state_path: Path
    log_path: Path
    message: str
    dependency_report: BuildDependencyReport | None = None

    def to_text(self) -> str:
        lines = [
            f"Default build: {self.state}",
            f"profile: {self.profile_id}",
            f"strategy: {self.strategy_id}",
            f"build target: {self.build_target}",
            f"plan id: {self.plan_id}",
            f"plan hash: {self.plan_hash}",
            f"message: {self.message}",
            f"build state: {self.state_path}",
            f"runtime log: {self.log_path}",
            f"dependency preflight: {self.dependency_report.summary_line() if self.dependency_report else 'not recorded'}",
            "executed commands:",
        ]
        if self.dependency_report and self.dependency_report.missing_required:
            lines.append("missing required dependencies:")
            for check in self.dependency_report.missing_required:
                lines.append(f"  - {check.check_id}: {check.details}")
            lines.append("owner action hints:")
            for family, commands in self.dependency_report.install_hints.items():
                lines.append(f"  {family}:")
                for command in commands:
                    lines.append(f"    - {command}")
        for result in self.executed_commands:
            lines.append(f"  - rc={result.returncode}: cd {result.cwd} && {' '.join(result.argv)}")
            if result.stderr:
                lines.append(f"    stderr: {result.stderr.strip()}")
        lines.append("artifacts:")
        for path, exists, executable, size_bytes in self.artifact_status:
            size = "?" if size_bytes is None else str(size_bytes)
            lines.append(f"  - {path}: exists={'yes' if exists else 'no'}; executable={'yes' if executable else 'no'}; size={size}")
        lines.extend(
            [
                "owner confirmation verified: yes",
                "requires sudo: no",
                "mutates services/firewall: no",
                "service mode: no",
                "bootstrap mixed in: no",
                "next: заново выполните --default-start-plan и --runtime-confirm перед --default-start",
            ]
        )
        return "\n".join(lines)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    return True if geteuid is None else geteuid() == 0


def _default_build_plan_id(profile_id: str, strategy_id: str) -> str:
    return f"runtime-{profile_id}-{strategy_id}-default-build-workflow-plan"


def _command_to_dict(command: BuildCommand, root: Path) -> dict[str, Any]:
    try:
        cwd = str(command.cwd.relative_to(root))
    except ValueError:
        cwd = str(command.cwd)
    return {
        "label": command.label,
        "cwd": cwd,
        "argv": list(command.argv),
        "description": command.description,
        "mutatesWorktree": command.mutates_worktree,
        "requiresSudo": command.requires_sudo,
    }


def _payload(root: Path, profile_id: str) -> tuple[dict[str, Any], LocalBuildPlan, str, str]:
    catalog = load_workspace_catalog(root)
    profiles = catalog.profile_by_id()
    if profile_id not in profiles:
        raise ValueError(f"Неизвестный workspace-профиль: {profile_id}")
    profile = profiles[profile_id]
    strategy_id = profile.strategy_id
    plan_id = _default_build_plan_id(profile.profile_id, strategy_id)
    local_plan = create_local_build_plan(root, target=profile.build_target)
    artifact_status = inspect_artifacts(local_plan)
    dependency_requirements = build_dependency_requirements_for_target(local_plan.target)
    payload = {
        "schemaVersion": DEFAULT_BUILD_SCHEMA_VERSION,
        "stage": DEFAULT_BUILD_STAGE,
        "marker": DEFAULT_BUILD_MARKER,
        "planId": plan_id,
        "action": "build",
        "profileId": profile.profile_id,
        "strategyId": strategy_id,
        "buildTarget": profile.build_target,
        "commands": [_command_to_dict(command, root) for command in local_plan.commands],
        "expectedArtifacts": [
            {
                "unitName": status.artifact.unit_name,
                "relativePath": status.artifact.relative_path,
                "existsAtPrepare": status.exists,
                "sizeBytesAtPrepare": status.size_bytes,
            }
            for status in artifact_status
        ],
        "requiredLibrariesHint": list(local_plan.required_libraries_hint),
        "buildDependencyPreflight": dependency_requirements,
        "safety": {
            "requiresOwnerConfirmation": True,
            "requiresSudoWhenExecutedByOwner": False,
            "rejectsRootExecutionByDefault": True,
            "mutatesWorktreeWhenExecutedByOwner": True,
            "mutatesFirewallWhenExecutedByOwner": False,
            "managesServiceWhenExecutedByOwner": False,
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
    return payload, local_plan, plan_id, strategy_id


def _rollback_text(plan_id: str, plan_hash: str, profile_id: str, strategy_id: str, local_plan: LocalBuildPlan) -> str:
    artifacts = "\n".join(f"- `{artifact.relative_path}`" for artifact in local_plan.expected_artifacts)
    commands = "\n".join(f"- `{command.shell_preview()}`" for command in local_plan.commands)
    return f"""# Rollback notes для {plan_id}

- stage: `{DEFAULT_BUILD_STAGE}`
- plan hash: `{plan_hash}`
- action: `build`
- profile: `{profile_id}`
- strategy: `{strategy_id}`
- sudo: нет
- service/firewall: нет
- bootstrap/install scripts: нет

## Команды плана

{commands}

## Ожидаемые артефакты

{artifacts}

## Откат

Локальная сборка меняет только build artifacts внутри `core/zapret2`. Для отката
можно выполнить обычный local build plan target `clean`:

```bash
PYTHONPATH=gui python -m zap2_gui.app --build-plan --build-target clean
cd core/zapret2 && make clean
```

После успешной сборки нужно заново подготовить и подтвердить `--default-start-plan`,
потому что runtime start preflight должен видеть уже существующий executable.
"""


def prepare_default_build_plan(root: Path | None = None, profile_id: str = "default") -> DefaultBuildWorkflowPlan:
    """Сохраняет default build plan в `.zap2/runtime`, но не запускает make."""

    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    payload, local_plan, plan_id, strategy_id = _payload(paths.root, profile_id)
    dependency_report = run_build_dependency_preflight(local_plan.target)
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
    rollback_path.write_text(_rollback_text(plan_id, plan_hash, profile_id, strategy_id, local_plan), encoding="utf-8")
    log_path = append_runtime_event(
        paths,
        {
            "schemaVersion": DEFAULT_BUILD_SCHEMA_VERSION,
            "stage": DEFAULT_BUILD_STAGE,
            "eventId": f"default-build-planned-{plan_id}-{plan_hash[:12]}",
            "eventType": "default-build-planned",
            "level": "info",
            "planId": plan_id,
            "planHash": plan_hash,
            "message": f"Prepared default build workflow plan for profile {profile_id}; make disabled until owner confirmation.",
            "createdAt": _utc_now(),
            "metadata": {"profileId": profile_id, "strategyId": strategy_id, "buildTarget": local_plan.target, "dependencyPreflight": dependency_report.to_dict()},
            "executesNow": False,
            "mutatesFirewallOrServicesNow": False,
            "managesServiceNow": False,
        },
        profile_id=profile_id,
    )
    return DefaultBuildWorkflowPlan(
        profile_id=profile_id,
        strategy_id=strategy_id,
        build_target=local_plan.target,
        plan_id=plan_id,
        plan_hash=plan_hash,
        plan_path=plan_path,
        rollback_path=rollback_path,
        log_path=log_path,
        local_build_plan=local_plan,
        dependency_report=dependency_report,
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


def _load_confirmed_default_build_plan(root: Path, profile_id: str, confirm_plan_id: str) -> tuple[dict[str, Any], str, LocalBuildPlan, str, str]:
    paths = ensure_runtime_store(root)
    payload, local_plan, expected_plan_id, strategy_id = _payload(paths.root, profile_id)
    if not confirm_plan_id:
        raise ValueError("Для default build нужен --confirm <plan-id>")
    if confirm_plan_id != expected_plan_id:
        raise ValueError(f"Передан не тот plan id: {confirm_plan_id}; ожидается {expected_plan_id}")
    plan_path = paths.plans_dir / f"{expected_plan_id}.json"
    confirmation_path = paths.confirmations_dir / f"{expected_plan_id}.confirmation.json"
    if not plan_path.exists():
        raise ValueError(f"Prepared default build plan не найден: {expected_plan_id}. Сначала выполните --default-build-plan.")
    if not confirmation_path.exists():
        raise ValueError(f"Confirmation не найден для {expected_plan_id}. Сначала выполните --runtime-confirm {expected_plan_id}.")
    saved = _read_json(plan_path)
    confirmation = _read_json(confirmation_path)
    current_hash = plan_payload_hash(_payload_without_runtime_fields(saved))
    # В отличие от start-plan, build plan intentionally привязан к observed artifact state at prepare.
    # Поэтому сверяем сохранённый план сам с собой и confirmation; новый prepare нужен только если сам план изменили.
    if saved.get("planHash") != current_hash:
        raise ValueError("Prepared default build plan устарел: текущий planHash не совпадает с сохранённым")
    if saved.get("confirmed") is not True:
        raise ValueError("Prepared default build plan ещё не подтверждён owner confirmation")
    if confirmation.get("planHash") != current_hash or confirmation.get("confirmedByOwner") is not True:
        raise ValueError("Confirmation не соответствует текущему default build plan hash")
    if plan_payload_hash(payload) != current_hash:
        # Это нормальный guard от silently changed build map/profile/command.
        raise ValueError("Текущий default build plan отличается от подтверждённого. Повторите --default-build-plan и --runtime-confirm.")
    return saved, current_hash, local_plan, expected_plan_id, strategy_id


def _default_runner(cwd: Path, argv: tuple[str, ...]) -> DefaultBuildCommandResult:
    result = subprocess.run(list(argv), cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return DefaultBuildCommandResult(cwd=cwd, argv=argv, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)


def _artifact_status(local_plan: LocalBuildPlan) -> tuple[tuple[Path, bool, bool, int | None], ...]:
    rows: list[tuple[Path, bool, bool, int | None]] = []
    for artifact in local_plan.expected_artifacts:
        path = artifact.absolute_path
        exists = path.exists()
        executable = path.is_file() and os.access(path, os.X_OK)
        rows.append((path, exists, executable, path.stat().st_size if exists else None))
    return tuple(rows)


def execute_default_build(
    root: Path | None = None,
    profile_id: str = "default",
    confirm_plan_id: str = "",
    *,
    runner: BuildCommandRunner | None = None,
    allow_as_root: bool = False,
    dependency_report: BuildDependencyReport | None = None,
) -> DefaultBuildExecutionResult:
    """Исполняет подтверждённую локальную сборку build target профиля."""

    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    _saved, plan_hash, local_plan, plan_id, strategy_id = _load_confirmed_default_build_plan(paths.root, profile_id, confirm_plan_id)
    effective_preflight = dependency_report or run_build_dependency_preflight(local_plan.target)
    if runner is None:
        if effective_preflight.ok and shutil.which("make") is None:
            raise ValueError("Команда make не найдена. Установите build toolchain и зависимости ядра.")
        runner = _default_runner
    if not allow_as_root and _is_root():
        raise ValueError("Default build не нужно запускать через sudo/root: это создаст root-owned артефакты в workspace.")

    results: list[DefaultBuildCommandResult] = []
    state = "built"
    message = "default build completed"
    if not effective_preflight.ok:
        state = "blocked"
        message = "build dependency preflight failed: установите недостающие build dependencies и повторите --default-build"
    if state == "built":
        for command in local_plan.commands:
            result = runner(command.cwd, command.argv)
            results.append(result)
            if not result.ok:
                state = "failed"
                message = f"build command failed: {command.label}"
                break
    statuses = _artifact_status(local_plan)
    if state == "built" and not all(exists and executable for _path, exists, executable, _size in statuses):
        state = "failed"
        message = "build command completed, but expected executable artifacts are missing"

    state_path = paths.sessions_dir / f"{profile_id}.default-build.json"
    state_record = {
        "schemaVersion": DEFAULT_BUILD_SCHEMA_VERSION,
        "stage": DEFAULT_BUILD_STAGE,
        "marker": DEFAULT_BUILD_MARKER,
        "state": state,
        "profileId": profile_id,
        "strategyId": strategy_id,
        "buildTarget": local_plan.target,
        "planId": plan_id,
        "planHash": plan_hash,
        "updatedAt": _utc_now(),
        "dependencyPreflight": effective_preflight.to_dict(),
        "commands": [
            {"cwd": str(item.cwd.relative_to(paths.root)) if item.cwd.is_relative_to(paths.root) else str(item.cwd), "argv": list(item.argv), "returncode": item.returncode, "stdout": item.stdout, "stderr": item.stderr}
            for item in results
        ],
        "artifacts": [
            {"path": str(path.relative_to(paths.root)) if path.is_relative_to(paths.root) else str(path), "exists": exists, "executable": executable, "sizeBytes": size}
            for path, exists, executable, size in statuses
        ],
        "requiresSudo": False,
        "mutatesFirewallOrServicesNow": False,
        "managesServiceNow": False,
        "containsRemoteBootstrap": False,
        "containsUpstreamInstallerScript": False,
    }
    _write_json(state_path, state_record)
    log_path = append_runtime_event(
        paths,
        {
            "schemaVersion": DEFAULT_BUILD_SCHEMA_VERSION,
            "stage": DEFAULT_BUILD_STAGE,
            "eventId": f"default-build-{state}-{plan_id}-{plan_hash[:12]}",
            "eventType": f"default-build-{state}",
            "level": "info" if state == "built" else "error",
            "planId": plan_id,
            "planHash": plan_hash,
            "message": message,
            "createdAt": _utc_now(),
            "metadata": {"profileId": profile_id, "strategyId": strategy_id, "statePath": str(state_path.relative_to(paths.root)), "dependencyPreflight": effective_preflight.to_dict()},
            "executesNow": True,
            "mutatesFirewallOrServicesNow": False,
            "managesServiceNow": False,
        },
        profile_id=profile_id,
    )
    return DefaultBuildExecutionResult(
        state=state,
        profile_id=profile_id,
        strategy_id=strategy_id,
        build_target=local_plan.target,
        plan_id=plan_id,
        plan_hash=plan_hash,
        executed_commands=tuple(results),
        artifact_status=statuses,
        state_path=state_path,
        log_path=log_path,
        message=message,
        dependency_report=effective_preflight,
    )
