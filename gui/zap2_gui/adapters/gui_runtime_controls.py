"""GUI-facing helpers for default build/start/stop workflow.

Этот слой переносит уже существующие CLI workflow в PyQt shell как явные
действия с текстовым выводом. Он не обходит confirmation-gate и не делает hidden
apply. Непривилегированные действия выполняются напрямую, а privileged start/stop
передаются отдельному GUI sudo-askpass adapter, чтобы пароль запрашивался
в графическом окне, а не в терминале.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .runtime_default import default_workflow_status, prepare_default_workflow_plan
from .runtime_default_build import execute_default_build, prepare_default_build_plan
from .runtime_logs import runtime_log_snapshot_to_text
from .runtime_kernel import runtime_kernel_status
from .build_dependencies import run_build_dependency_preflight
from .runtime_state import confirm_runtime_plan, ensure_runtime_store
from .gui_first_overview import gui_first_runtime_overview_to_text
from .gui_privilege import (
    default_plan_id_for_action,
    gui_privileged_command_to_text,
    execute_gui_privileged_workflow,
    execute_gui_privileged_discord_probe,
)
from .workspace_profiles import load_workspace_catalog
from ..project_paths import discover_layout

DEFAULT_BUILD_PLAN_ID = "runtime-default-manual-local-default-build-workflow-plan"
DEFAULT_START_PLAN_ID = "runtime-default-manual-local-default-start-workflow-plan"
DEFAULT_STOP_PLAN_ID = "runtime-default-manual-local-default-stop-workflow-plan"


def default_build_plan_id(root: Path | None = None, profile_id: str = "default") -> str:
    layout = discover_layout(root)
    catalog = load_workspace_catalog(layout.root)
    profiles = catalog.profile_by_id()
    if profile_id not in profiles:
        raise ValueError(f"Неизвестный workspace-профиль: {profile_id}")
    return f"runtime-{profile_id}-{profiles[profile_id].strategy_id}-default-build-workflow-plan"


def current_default_plan_id(root: Path | None = None, action: str = "start", profile_id: str = "default") -> str:
    if action == "build":
        return default_build_plan_id(root, profile_id)
    return default_plan_id_for_action(root, action=action, profile_id=profile_id)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def gui_overview_action_output_path(root: Path | None = None, profile_id: str = "default") -> Path:
    """Path for the last verbose Overview action output moved to Logs tab."""

    paths = ensure_runtime_store(root)
    return paths.logs_dir / f"{profile_id}.overview-action-output.log"


def write_gui_overview_action_output(root: Path | None, profile_id: str, label: str, text: str) -> Path:
    """Store verbose Overview action output so Overview can stay table-first."""

    path = gui_overview_action_output_path(root=root, profile_id=profile_id)
    path.write_text(
        "\n".join(
            [
                f"createdAt: {_utc_now()}",
                f"source: Runtime Overview",
                f"action: {label}",
                "",
                text.rstrip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def gui_overview_action_output_to_text(root: Path | None = None, profile_id: str = "default") -> str:
    """Read the last verbose Overview action output for the Logs tab."""

    path = gui_overview_action_output_path(root=root, profile_id=profile_id)
    if not path.exists():
        return "\n".join(
            [
                "Overview action output",
                f"path: {path}",
                "status: нет сохранённого вывода",
                "read-only: yes",
            ]
        )
    return "\n".join(
        [
            "Overview action output",
            f"path: {path}",
            "",
            path.read_text(encoding="utf-8", errors="replace").rstrip(),
            "",
            "read-only: yes",
        ]
    )


def gui_runtime_logs_with_overview_output(root: Path | None = None, profile_id: str = "default") -> str:
    """Combined Logs tab text: last Overview output plus normal runtime logs."""

    return "\n\n".join(
        [
            gui_overview_action_output_to_text(root=root, profile_id=profile_id),
            gui_runtime_logs(root=root, profile_id=profile_id),
        ]
    )


def gui_runtime_logs(root: Path | None = None, profile_id: str = "default") -> str:
    """Показать агрегированные runtime logs для GUI-вкладки «Логи»."""

    return runtime_log_snapshot_to_text(root=root, profile_id=profile_id)


def _default_binary_ready(root: Path | None) -> bool:
    layout = discover_layout(root)
    binary = layout.root / "core" / "zapret2" / "nfq2" / "nfqws2"
    return binary.is_file() and bool(binary.stat().st_mode & 0o111)


def gui_default_toggle_label(root: Path | None = None, profile_id: str = "default") -> str:
    """Return a compact label for the single GUI on/off button."""

    status = default_workflow_status(root=root, profile_id=profile_id)
    if status.workflow_state == "started" and status.session_status.state == "running":
        return "Выключить Default"
    return "Включить Default"


def gui_toggle_default_workflow(root: Path | None = None, profile_id: str = "default") -> str:
    """One-button default workflow for the PyQt shell.

    Если default уже запущен, функция строит/подтверждает stop-plan и вызывает
    GUI privileged stop через sudo-askpass. Если default не запущен, функция при
    необходимости выполняет build workflow без sudo, затем строит/подтверждает
    start-plan и вызывает GUI privileged start через sudo-askpass.
    """

    status = default_workflow_status(root=root, profile_id=profile_id)
    parts: list[str] = ["GUI toggle Default workflow", gui_first_runtime_overview_to_text(root=root, profile_id=profile_id)]
    if status.workflow_state == "started" and status.session_status.state == "running":
        parts.append("\nШаг 1/3: подготовка stop-plan")
        stop_plan = prepare_default_workflow_plan(root=root, action="stop", profile_id=profile_id)
        parts.append(stop_plan.to_text())
        parts.append("\nШаг 2/3: подтверждение stop-plan")
        parts.append(gui_confirm_plan(root=root, plan_id=stop_plan.plan_id))
        parts.append("\nШаг 3/3: privileged stop через графический sudo prompt")
        parts.append(gui_privileged_default_stop(root=root, profile_id=profile_id, confirm_plan_id=stop_plan.plan_id))
        parts.append("\nGUI-first state after stop:")
        parts.append(gui_first_runtime_overview_to_text(root=root, profile_id=profile_id))
        parts.append("\nRuntime logs:")
        parts.append(gui_runtime_logs(root=root, profile_id=profile_id))
        return "\n\n".join(parts)

    if not _default_binary_ready(root):
        parts.append("\nШаг 1/7: проверка build dependencies")
        parts.append(gui_default_build_deps(root=root, profile_id=profile_id))
        parts.append("\nШаг 2/7: подготовка build-plan")
        build_plan = prepare_default_build_plan(root=root, profile_id=profile_id)
        parts.append(build_plan.to_text())
        parts.append("\nШаг 3/7: подтверждение build-plan")
        parts.append(gui_confirm_plan(root=root, plan_id=build_plan.plan_id))
        parts.append("\nШаг 4/7: локальная сборка без sudo")
        build_output = gui_execute_default_build(root=root, profile_id=profile_id, confirm_plan_id=build_plan.plan_id)
        parts.append(build_output)
        if not _default_binary_ready(root):
            parts.append("\nСборка не дала executable nfqws2; privileged start пропущен.")
            parts.append("\nGUI-first state after blocked start:")
            parts.append(gui_first_runtime_overview_to_text(root=root, profile_id=profile_id))
            parts.append("\nRuntime logs:")
            parts.append(gui_runtime_logs(root=root, profile_id=profile_id))
            return "\n\n".join(parts)
        next_step = 5
        total_steps = 7
    else:
        next_step = 1
        total_steps = 3

    parts.append(f"\nШаг {next_step}/{total_steps}: подготовка start-plan")
    start_plan = prepare_default_workflow_plan(root=root, action="start", profile_id=profile_id)
    parts.append(start_plan.to_text())
    parts.append(f"\nШаг {next_step + 1}/{total_steps}: подтверждение start-plan")
    parts.append(gui_confirm_plan(root=root, plan_id=start_plan.plan_id))
    parts.append(f"\nШаг {next_step + 2}/{total_steps}: privileged start через графический sudo prompt")
    parts.append(gui_privileged_default_start(root=root, profile_id=profile_id, confirm_plan_id=start_plan.plan_id))
    parts.append("\nGUI-first state after start:")
    parts.append(gui_first_runtime_overview_to_text(root=root, profile_id=profile_id))
    parts.append("\nRuntime logs:")
    parts.append(gui_runtime_logs(root=root, profile_id=profile_id))
    return "\n\n".join(parts)


@dataclass(frozen=True)
class GuiRuntimeCommandSet:
    """Copy-paste команды для owner-controlled default workflow."""

    profile_id: str
    build_plan_id: str = DEFAULT_BUILD_PLAN_ID
    start_plan_id: str = DEFAULT_START_PLAN_ID
    stop_plan_id: str = DEFAULT_STOP_PLAN_ID

    def to_text(self) -> str:
        return "\n".join(
            [
                "GUI runtime commands для default workflow",
                f"profile: {self.profile_id}",
                "",
                "1) Сборка:",
                "PYTHONPATH=gui python -m zap2_gui.app --default-build-plan",
                f"PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm {self.build_plan_id}",
                f"PYTHONPATH=gui python -m zap2_gui.app --default-build --confirm {self.build_plan_id}",
                "",
                "2) Запуск:",
                "PYTHONPATH=gui python -m zap2_gui.app --default-start-plan",
                f"PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm {self.start_plan_id}",
                f"GUI button: Включить через графический sudo-запрос -> --default-start --confirm {self.start_plan_id}",
                "",
                "3) Статус:",
                "PYTHONPATH=gui python -m zap2_gui.app --default-status",
                "",
                "4) Отключение:",
                "PYTHONPATH=gui python -m zap2_gui.app --default-stop-plan",
                f"PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm {self.stop_plan_id}",
                f"GUI button: Отключить через графический sudo-запрос -> --default-stop --confirm {self.stop_plan_id}",
                "",
                "GUI не просит пароль в терминале: P02 оставляет GUI unprivileged; sudo -A вызывает только root-owned finite executor с confirmed PlanHash.",
            ]
        )


def gui_runtime_commands(root: Path | None = None, profile_id: str = "default") -> GuiRuntimeCommandSet:
    return GuiRuntimeCommandSet(
        profile_id=profile_id,
        build_plan_id=current_default_plan_id(root, "build", profile_id),
        start_plan_id=current_default_plan_id(root, "start", profile_id),
        stop_plan_id=current_default_plan_id(root, "stop", profile_id),
    )


def gui_default_build_deps(root: Path | None = None, profile_id: str = "default") -> str:
    """Показать dependency preflight для default build без установки пакетов."""

    discover_layout(root)
    return run_build_dependency_preflight("nfqws2").to_text()


def gui_prepare_default_build(root: Path | None = None, profile_id: str = "default") -> str:
    discover_layout(root)  # ранняя проверка workspace
    return prepare_default_build_plan(root=root, profile_id=profile_id).to_text()


def gui_execute_default_build(root: Path | None = None, profile_id: str = "default", confirm_plan_id: str | None = None) -> str:
    """Исполнить подтверждённую локальную сборку из GUI без sudo."""

    discover_layout(root)
    result = execute_default_build(root=root, profile_id=profile_id, confirm_plan_id=confirm_plan_id or current_default_plan_id(root, "build", profile_id))
    status = gui_default_status(root=root, profile_id=profile_id)
    return "\n\n".join([result.to_text(), "После сборки текущий статус:", status])


def gui_prepare_default_start(root: Path | None = None, profile_id: str = "default") -> str:
    discover_layout(root)
    return prepare_default_workflow_plan(root=root, action="start", profile_id=profile_id).to_text()


def gui_prepare_default_stop(root: Path | None = None, profile_id: str = "default") -> str:
    discover_layout(root)
    return prepare_default_workflow_plan(root=root, action="stop", profile_id=profile_id).to_text()


def gui_confirm_default_build(root: Path | None = None, profile_id: str = "default") -> str:
    return gui_confirm_plan(root=root, plan_id=current_default_plan_id(root, "build", profile_id))


def gui_confirm_default_start(root: Path | None = None, profile_id: str = "default") -> str:
    return gui_confirm_plan(root=root, plan_id=current_default_plan_id(root, "start", profile_id))


def gui_confirm_default_stop(root: Path | None = None, profile_id: str = "default") -> str:
    return gui_confirm_plan(root=root, plan_id=current_default_plan_id(root, "stop", profile_id))


def gui_confirm_plan(root: Path | None = None, plan_id: str = "") -> str:
    if not plan_id:
        raise ValueError("GUI confirmation требует явный plan id")
    return confirm_runtime_plan(root=root, plan_id=plan_id).to_text()


def gui_default_status(root: Path | None = None, profile_id: str = "default") -> str:
    # GUI and CLI project the same P02 ownership evidence; retain the legacy
    # workflow summary below it for user-facing continuity.
    return "\n\n".join([
        runtime_kernel_status(root=root, profile_id=profile_id).to_text(),
        default_workflow_status(root=root, profile_id=profile_id).to_text(),
    ])


def _with_status_after_action(root: Path | None, profile_id: str, action_text: str, body: str) -> str:
    """Append read-only status so GUI does not leave the owner guessing."""

    try:
        status = gui_default_status(root=root, profile_id=profile_id)
    except Exception as exc:  # pragma: no cover - defensive GUI diagnostic path
        status = f"Статус после действия не удалось прочитать: {exc}"
    try:
        overview = gui_first_runtime_overview_to_text(root=root, profile_id=profile_id)
    except Exception as exc:  # pragma: no cover - defensive GUI diagnostic path
        overview = f"GUI-first overview не удалось прочитать: {exc}"
    return "\n\n".join([body, f"Статус после действия: {action_text}", overview, status])


def _default_binary_guidance(root: Path | None) -> str | None:
    layout = discover_layout(root)
    binary = layout.root / "core" / "zapret2" / "nfq2" / "nfqws2"
    if binary.is_file() and binary.stat().st_mode & 0o111:
        return None
    return "\n".join(
        [
            "Default start заблокирован до privileged start: nfqws2 binary отсутствует или не исполняемый.",
            f"binary: {binary}",
            "В GUI выполните полный build workflow:",
            "1) Проверить зависимости сборки",
            "2) План сборки",
            "3) Подтвердить сборку",
            "4) Собрать без sudo",
            "5) План запуска",
            "6) Подтвердить запуск",
            "7) Включить через графический запрос прав",
            "",
            "bounded executor сейчас не запускался; firewall/session не менялись.",
        ]
    )


def gui_privileged_default_start(root: Path | None = None, profile_id: str = "default", confirm_plan_id: str | None = None) -> str:
    """Запустить confirmed default-start через графический sudo askpass из GUI."""

    guidance = _default_binary_guidance(root)
    if guidance:
        return _with_status_after_action(root, profile_id, "start blocked", guidance)
    result = execute_gui_privileged_workflow(
        root=root,
        action="start",
        profile_id=profile_id,
        confirm_plan_id=confirm_plan_id or current_default_plan_id(root, "start", profile_id),
    ).to_text()
    return _with_status_after_action(root, profile_id, "start", result)


def gui_privileged_default_stop(root: Path | None = None, profile_id: str = "default", confirm_plan_id: str | None = None) -> str:
    """Запустить confirmed default-stop через графический sudo askpass из GUI."""

    result = execute_gui_privileged_workflow(
        root=root,
        action="stop",
        profile_id=profile_id,
        confirm_plan_id=confirm_plan_id or current_default_plan_id(root, "stop", profile_id),
    ).to_text()
    return _with_status_after_action(root, profile_id, "stop", result)


def gui_privileged_discord_pretls_probe(root: Path | None = None, profile_id: str = "default", wait_seconds: int = 30) -> str:
    """Run Discord guided probe through sudo-askpass so nft counters are readable."""

    result = execute_gui_privileged_discord_probe(
        root=root,
        profile_id=profile_id,
        wait_seconds=wait_seconds,
    ).to_text()
    return _with_status_after_action(root, profile_id, "discord privileged probe", result)



def gui_privileged_default_start_command(root: Path | None = None, profile_id: str = "default") -> str:
    return gui_privileged_command_to_text(
        root=root,
        action="start",
        profile_id=profile_id,
        confirm_plan_id=current_default_plan_id(root, "start", profile_id),
    )


def gui_privileged_default_stop_command(root: Path | None = None, profile_id: str = "default") -> str:
    return gui_privileged_command_to_text(
        root=root,
        action="stop",
        profile_id=profile_id,
        confirm_plan_id=current_default_plan_id(root, "stop", profile_id),
    )
