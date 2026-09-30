"""Plan-only генератор runtime plan для default strategy.

Stage 9 превращает workspace profile + strategy + build map в явные start/stop/status
планы. Модуль намеренно не запускает процессы, не вызывает sudo, не меняет firewall
и не управляет service manager: он только строит typed-представление будущего
runtime workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .execution_plan import materialize_execution_plan
from .local_build import BuildArtifact, create_local_build_plan, inspect_artifacts
from .workspace_profiles import load_workspace_catalog
from ..models.execution_plan import ImmutableExecutionPlan
from ..models.lifecycle import RUNTIME_CONTRACT_STAGE
from ..models.runtime_plan import (
    RuntimePlanCommandPreview,
    RuntimePlanContract,
    RuntimePlanLifecycle,
    RuntimePlanSafety,
    RuntimePlanSection,
    RuntimePlanStep,
)
from ..models.strategy import WorkspaceStrategy
from ..models.workspace_profile import HostlistRef, WorkspaceProfile
from ..project_paths import discover_layout

SUPPORTED_RUNTIME_PLAN_ACTIONS = ("start", "stop", "status")


@dataclass(frozen=True)
class RuntimePlanFileRef:
    """Файл, который будущий runtime workflow будет читать или писать."""

    label: str
    relative_path: str
    purpose: str


@dataclass(frozen=True)
class GeneratedRuntimePlan:
    """Сгенерированный plan-only runtime plan для CLI/GUI."""

    action: str
    profile: WorkspaceProfile
    strategy: WorkspaceStrategy
    binary_relative_path: str
    hostlists: tuple[HostlistRef, ...]
    required_artifacts: tuple[BuildArtifact, ...]
    required_artifacts_exist: tuple[bool, ...]
    session_files: tuple[RuntimePlanFileRef, ...]
    log_files: tuple[RuntimePlanFileRef, ...]
    contract: RuntimePlanContract
    execution_plan: ImmutableExecutionPlan

    @property
    def plan_id(self) -> str:
        return self.contract.plan_id

    @property
    def requires_owner_confirmation(self) -> bool:
        return self.contract.safety.requires_owner_confirmation

    @property
    def requires_sudo_for_apply(self) -> bool:
        return any(
            command.requires_sudo
            for section in self.contract.sections
            if section.kind == "apply"
            for step in section.steps
            for command in step.commands
        )

    @property
    def mutates_services_or_firewall(self) -> bool:
        return any(
            command.mutates_system
            for section in self.contract.sections
            for step in section.steps
            for command in step.commands
        )

    def _format_artifacts(self) -> tuple[str, ...]:
        lines: list[str] = []
        for artifact, exists in zip(self.required_artifacts, self.required_artifacts_exist):
            state = "exists" if exists else "missing"
            lines.append(f"  - core/zapret2/{artifact.relative_path} ({state})")
        return tuple(lines) or ("  - нет",)

    def _format_hostlists(self) -> tuple[str, ...]:
        return tuple(f"  - {hostlist.path} ({hostlist.purpose})" for hostlist in self.hostlists) or ("  - нет",)

    def _format_files(self, files: tuple[RuntimePlanFileRef, ...]) -> tuple[str, ...]:
        return tuple(f"  - {item.relative_path} — {item.purpose}" for item in files) or ("  - нет",)

    def _format_apply_steps(self) -> tuple[str, ...]:
        lines: list[str] = []
        for section in self.contract.sections:
            if section.kind != "apply":
                continue
            for step in section.steps:
                if step.commands:
                    sudo = "yes" if any(command.requires_sudo for command in step.commands) else "no"
                    mutates = "yes" if any(command.mutates_system for command in step.commands) else "no"
                else:
                    sudo = "no"
                    mutates = "no"
                lines.append(f"  - {step.step_id}: {step.title}; requires sudo: {sudo}; mutates system: {mutates}")
        return tuple(lines) or ("  - нет",)

    def _format_rollback_notes(self) -> tuple[str, ...]:
        return tuple(f"  - {note}" for note in self.contract.rollback_notes) or ("  - нет",)

    def to_text(self) -> str:
        artifact_lines = "\n".join(self._format_artifacts())
        hostlist_lines = "\n".join(self._format_hostlists())
        session_file_lines = "\n".join(self._format_files(self.session_files))
        log_file_lines = "\n".join(self._format_files(self.log_files))
        apply_lines = "\n".join(self._format_apply_steps())
        rollback_lines = "\n".join(self._format_rollback_notes())
        runtime_arg_lines = "\n".join(f"  - {arg}" for arg in self.execution_plan.runtime_args) or "  - нет"
        source = self.strategy.source_preset or {}
        source_name = str(source.get("name", "не указан"))
        source_level = str(source.get("portingLevel", "не указан"))
        return "\n".join(
            [
                f"Runtime plan для action: {self.action}",
                f"plan id: {self.plan_id}",
                f"profile: {self.profile.profile_id}",
                f"strategy: {self.strategy.strategy_id}",
                f"normalized execution plan: {self.execution_plan.plan_hash}",
                f"strategy source: {source_name} ({source_level})",
                f"build target: {self.profile.build_target}",
                f"binary: {self.binary_relative_path}",
                "hostlists:",
                hostlist_lines,
                "strategy runtime args:",
                runtime_arg_lines,
                "required artifacts:",
                artifact_lines,
                "session files:",
                session_file_lines,
                "log files:",
                log_file_lines,
                "apply steps:",
                apply_lines,
                "rollback steps:",
                rollback_lines,
                f"requires owner confirmation: {'yes' if self.requires_owner_confirmation else 'no'}",
                f"requires sudo for apply: {'yes' if self.requires_sudo_for_apply else 'no'}",
                f"may mutate services/firewall when executed by owner: {'yes' if self.mutates_services_or_firewall else 'no'}",
                "mutates now: no",
                "automatic checks may execute: no",
                "executes now: no",
                "bootstrap mixed in: no",
            ]
        )


def _hostlists_for_strategy(profile: WorkspaceProfile, strategy: WorkspaceStrategy) -> tuple[HostlistRef, ...]:
    """Return profile hostlists that should be passed to nfqws2 for a strategy.

    Most strategies inherit the owner-maintained profile hostlist.  A broad
    Windows-style all-sites port must be able to act on SYN packets before any
    hostname is known; a regular --hostlist would make such SYN packets fail
    profile matching.  Such strategies opt out explicitly through
    capturePolicy.profileHostlists="omit" or by declaring readsHostlists=false.
    """

    capture_policy = strategy.capture_policy or {}
    if str(capture_policy.get("profileHostlists") or "").lower() in {"omit", "none", "disabled"}:
        return ()
    if not strategy.capabilities.reads_hostlists:
        return ()
    return profile.hostlists


def _runtime_relative_paths(profile_id: str, action: str, plan_id: str) -> tuple[tuple[RuntimePlanFileRef, ...], tuple[RuntimePlanFileRef, ...]]:
    session_files = (
        RuntimePlanFileRef(
            label="session-state",
            relative_path=f".zap2/runtime/sessions/{profile_id}.session.json",
            purpose="будущий PID/state текущей runtime session",
        ),
        RuntimePlanFileRef(
            label="prepared-plan",
            relative_path=f".zap2/runtime/plans/{plan_id}.json",
            purpose="будущая сохранённая копия плана перед подтверждением",
        ),
    )
    log_files = (
        RuntimePlanFileRef(
            label="runtime-log",
            relative_path=f".zap2/runtime/logs/{profile_id}.runtime.log",
            purpose="будущий append-only журнал runtime lifecycle",
        ),
        RuntimePlanFileRef(
            label="rollback-notes",
            relative_path=f".zap2/runtime/rollback/{plan_id}.md",
            purpose="будущие заметки отката, связанные с plan id",
        ),
    )
    return session_files, log_files


def _command(label: str, cwd: str, argv: tuple[str, ...], requires_sudo: bool, mutates_system: bool, description: str) -> RuntimePlanCommandPreview:
    return RuntimePlanCommandPreview(
        label=label,
        cwd=cwd,
        argv=argv,
        requires_sudo=requires_sudo,
        mutates_system=mutates_system,
        description=description,
    )


def _step(step_id: str, title: str, description: str, requires_owner_confirmation: bool, commands: tuple[RuntimePlanCommandPreview, ...] = ()) -> RuntimePlanStep:
    return RuntimePlanStep(
        step_id=step_id,
        title=title,
        description=description,
        requires_owner_confirmation=requires_owner_confirmation,
        commands=commands,
    )


def _sections_for_action(action: str, profile: WorkspaceProfile, binary_relative_path: str) -> tuple[RuntimePlanSection, ...]:
    if action == "start":
        apply_command = _command(
            label="future-apply-owner-rules",
            cwd=".",
            argv=("zap2-gui", "--runtime-apply", "--profile", profile.profile_id, "--confirm", "<plan-id>"),
            requires_sudo=True,
            mutates_system=True,
            description="Будущий owner-confirmed apply системных правил; Stage 9 только показывает план.",
        )
        session_command = _command(
            label="future-session-start",
            cwd=".",
            argv=(binary_relative_path, "<runtime-args-from-confirmed-plan>"),
            requires_sudo=False,
            mutates_system=False,
            description="Будущий запуск локального nfqws2; Stage 9 не запускает процесс.",
        )
        return (
            RuntimePlanSection("run", "Проверить профиль, стратегию, hostlist и бинарник перед стартом.", (
                _step("run.preflight", "Предварительная проверка", "Read-only проверка default profile, manual-local strategy и build target.", False),
                _step("run.artifacts", "Проверка артефактов", "Read-only проверка ожидаемого бинарника ядра перед будущим стартом.", False),
            )),
            RuntimePlanSection("apply", "Будущий owner-confirmed apply системных правил перед session start.", (
                _step("apply.owner-confirmed-rules", "Применить системные правила после подтверждения", "Stage 9 не меняет firewall. Реальный apply появится отдельным патчем с точечным revert.", True, (apply_command,)),
            )),
            RuntimePlanSection("session", "Будущий lifecycle локального процесса nfqws2.", (
                _step("session.start-process", "Запустить session процесс", "Stage 9 только показывает будущую команду и state/log файлы.", True, (session_command,)),
            )),
            RuntimePlanSection("service", "Service mode остаётся отдельным путём и не входит в default start.", (
                _step("service.not-default", "Не устанавливать service", "Default workflow Stage 9 не создаёт и не запускает systemd unit.", True),
            )),
        )

    if action == "stop":
        revert_command = _command(
            label="future-revert-owner-rules",
            cwd=".",
            argv=("zap2-gui", "--runtime-revert", "--profile", profile.profile_id, "--confirm", "<plan-id>"),
            requires_sudo=True,
            mutates_system=True,
            description="Будущий owner-confirmed revert системных правил; Stage 9 только показывает план.",
        )
        return (
            RuntimePlanSection("run", "Прочитать runtime state и определить, что было запущено нашим workspace.", (
                _step("run.read-state", "Прочитать runtime state", "Read-only чтение будущего .zap2/runtime state перед остановкой.", False),
            )),
            RuntimePlanSection("apply", "Будущий owner-confirmed revert системных правил после остановки session.", (
                _step("apply.revert-owner-rules", "Откатить системные правила после подтверждения", "Stage 9 не меняет firewall. Реальный revert появится отдельным патчем.", True, (revert_command,)),
            )),
            RuntimePlanSection("session", "Будущий stop только процесса, который записан в runtime state.", (
                _step("session.stop-recorded-process", "Остановить записанный процесс", "Останавливать только PID/session, созданные нашим будущим session runner.", True),
            )),
            RuntimePlanSection("service", "Service mode не трогается default stop workflow.", (
                _step("service.not-default", "Не управлять service", "Default stop Stage 9 не вызывает systemctl и не удаляет unit.", True),
            )),
        )

    if action == "status":
        return (
            RuntimePlanSection("run", "Read-only status: проверить профиль, build artifact и runtime state.", (
                _step("run.status-preflight", "Проверить доступность данных", "Read-only проверка профиля, стратегии, hostlist и ожидаемых путей.", False),
            )),
            RuntimePlanSection("apply", "Status не применяет и не откатывает системные правила.", (
                _step("apply.noop", "Нет apply-действий", "Status plan не требует sudo и не мутирует систему.", False),
            )),
            RuntimePlanSection("session", "Read-only чтение будущего session state.", (
                _step("session.read-state", "Прочитать session state", "Status не отправляет сигналы процессам и не запускает nfqws2.", False),
            )),
            RuntimePlanSection("service", "Read-only service summary без systemctl.", (
                _step("service.noop", "Не управлять service", "Status plan не вызывает service manager.", False),
            )),
        )

    raise ValueError(f"Неизвестный runtime action: {action}")


def _rollback_notes_for_action(action: str, profile_id: str) -> tuple[str, ...]:
    if action == "start":
        return (
            "Перед будущим apply должен существовать stop/revert plan для того же profile и strategy.",
            "Если session start не удался, будущий executor должен выполнить revert apply plan и записать failure event.",
            f"Откат должен затрагивать только runtime markers и правила, созданные для profile {profile_id}.",
        )
    if action == "stop":
        return (
            "Stop workflow должен сначала остановить только записанную session, затем выполнить revert apply plan.",
            "Если revert не удался, future executor должен оставить rollback notes и не очищать diagnostic logs.",
            f"Очистка state допустима только для markers, созданных workspace profile {profile_id}.",
        )
    if action == "status":
        return (
            "Status не имеет rollback-действий, потому что не меняет систему.",
            "Если runtime state повреждён, status должен сообщить unknown, а не чинить систему автоматически.",
        )
    raise ValueError(f"Неизвестный runtime action: {action}")


def create_runtime_plan(root: Path | None = None, action: str = "start", profile_id: str = "default") -> GeneratedRuntimePlan:
    """Создаёт plan-only runtime plan для action=start/stop/status.

    План строится из workspace-профиля, стратегии и local build adapter. Функция
    выполняет только чтение файлов проекта и stat ожидаемых артефактов.
    """

    if action not in SUPPORTED_RUNTIME_PLAN_ACTIONS:
        raise ValueError(f"Неизвестное runtime action: {action}. Доступно: {', '.join(SUPPORTED_RUNTIME_PLAN_ACTIONS)}")

    layout = discover_layout(root)
    catalog = load_workspace_catalog(layout.root)
    profiles = catalog.profile_by_id()
    if profile_id not in profiles:
        raise ValueError(f"Неизвестный workspace-профиль: {profile_id}. Доступно: {', '.join(sorted(profiles))}")
    profile = profiles[profile_id]
    strategies = catalog.strategy_by_id()
    if profile.strategy_id not in strategies:
        raise ValueError(f"Профиль {profile.profile_id} ссылается на неизвестную стратегию: {profile.strategy_id}")
    strategy = strategies[profile.strategy_id]
    execution_materialization = materialize_execution_plan(layout.root, runtime_context_id=profile.runtime_context_id)
    execution_plan = execution_materialization.plan
    if execution_plan.preset_id != strategy.preset_id:
        raise ValueError(
            f"Normalized Plan preset mismatch: {execution_plan.preset_id} != {strategy.preset_id}"
        )

    build_plan = create_local_build_plan(layout.root, target=profile.build_target)
    artifact_statuses = inspect_artifacts(build_plan)
    required_artifacts = tuple(status.artifact for status in artifact_statuses)
    artifact_exists = tuple(status.exists for status in artifact_statuses)
    binary_relative_path = f"core/zapret2/{required_artifacts[0].relative_path}" if required_artifacts else f"core/zapret2/{profile.build_target}"

    plan_id = f"runtime-{profile.profile_id}-{strategy.strategy_id}-{action}-plan"
    session_files, log_files = _runtime_relative_paths(profile.profile_id, action, plan_id)
    sections = _sections_for_action(action, profile, binary_relative_path)
    may_require_sudo = any(
        command.requires_sudo
        for section in sections
        for step in section.steps
        for command in step.commands
    )
    may_mutate_firewall = any(
        command.mutates_system
        for section in sections
        for step in section.steps
        for command in step.commands
    )
    contract = RuntimePlanContract(
        schema_version=1,
        plan_id=plan_id,
        title=f"Runtime {action} plan для {profile.profile_id}/{strategy.strategy_id}",
        profile_id=profile.profile_id,
        strategy_id=strategy.strategy_id,
        action=action,
        lifecycle=RuntimePlanLifecycle(
            contract_stage=RUNTIME_CONTRACT_STAGE,
            bootstrap_mixed_in=False,
            automatic_checks_may_execute=False,
        ),
        safety=RuntimePlanSafety(
            requires_owner_confirmation=True,
            may_require_sudo_when_executed_by_owner=may_require_sudo,
            may_mutate_firewall_when_executed_by_owner=may_mutate_firewall,
            may_manage_service_when_executed_by_owner=False,
            contains_remote_bootstrap=False,
            contains_upstream_installer_script=False,
        ),
        sections=sections,
        rollback_notes=_rollback_notes_for_action(action, profile.profile_id),
        source_path=None,
    )
    runtime_hostlists = _hostlists_for_strategy(profile, strategy)
    return GeneratedRuntimePlan(
        action=action,
        profile=profile,
        strategy=strategy,
        binary_relative_path=binary_relative_path,
        hostlists=runtime_hostlists,
        required_artifacts=required_artifacts,
        required_artifacts_exist=artifact_exists,
        session_files=session_files,
        log_files=log_files,
        contract=contract,
        execution_plan=execution_plan,
    )


def runtime_plan_to_text(action: str = "start", profile_id: str = "default", root: Path | None = None) -> str:
    """CLI-friendly текст сгенерированного runtime plan."""

    return create_runtime_plan(root=root, action=action, profile_id=profile_id).to_text()
