"""GUI-facing helpers for default build/start/stop workflow.

Этот слой переносит уже существующие CLI workflow в PyQt shell как явные
действия с текстовым выводом. Он не обходит confirmation-gate и не делает hidden
apply. Непривилегированные действия выполняются напрямую, а privileged start/stop
передаются отдельному GUI polkit adapter через pkexec, чтобы пароль запрашивал
системный графический authentication agent, а не терминальный sudo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .runtime_default import default_workflow_status, prepare_default_workflow_plan
from .runtime_default_build import execute_default_build, prepare_default_build_plan
from .runtime_logs import runtime_log_snapshot_to_text
from .build_dependencies import run_build_dependency_preflight
from .runtime_state import confirm_runtime_plan
from .gui_privilege import (
    gui_privileged_command_to_text,
    execute_gui_privileged_workflow,
)
from ..project_paths import discover_layout

DEFAULT_BUILD_PLAN_ID = "runtime-default-manual-local-default-build-workflow-plan"
DEFAULT_START_PLAN_ID = "runtime-default-manual-local-default-start-workflow-plan"
DEFAULT_STOP_PLAN_ID = "runtime-default-manual-local-default-stop-workflow-plan"


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
    GUI privileged stop через pkexec. Если default не запущен, функция при
    необходимости выполняет build workflow без sudo, затем строит/подтверждает
    start-plan и вызывает GUI privileged start через pkexec.
    """

    status = default_workflow_status(root=root, profile_id=profile_id)
    parts: list[str] = ["GUI toggle Default workflow", status.to_text()]
    if status.workflow_state == "started" and status.session_status.state == "running":
        parts.append("\nШаг 1/3: подготовка stop-plan")
        parts.append(gui_prepare_default_stop(root=root, profile_id=profile_id))
        parts.append("\nШаг 2/3: подтверждение stop-plan")
        parts.append(gui_confirm_plan(root=root, plan_id=DEFAULT_STOP_PLAN_ID))
        parts.append("\nШаг 3/3: privileged stop через графический polkit prompt")
        parts.append(gui_privileged_default_stop(root=root, profile_id=profile_id))
        parts.append("\nRuntime logs:")
        parts.append(gui_runtime_logs(root=root, profile_id=profile_id))
        return "\n\n".join(parts)

    if not _default_binary_ready(root):
        parts.append("\nШаг 1/7: проверка build dependencies")
        parts.append(gui_default_build_deps(root=root, profile_id=profile_id))
        parts.append("\nШаг 2/7: подготовка build-plan")
        parts.append(gui_prepare_default_build(root=root, profile_id=profile_id))
        parts.append("\nШаг 3/7: подтверждение build-plan")
        parts.append(gui_confirm_plan(root=root, plan_id=DEFAULT_BUILD_PLAN_ID))
        parts.append("\nШаг 4/7: локальная сборка без sudo")
        build_output = gui_execute_default_build(root=root, profile_id=profile_id)
        parts.append(build_output)
        if not _default_binary_ready(root):
            parts.append("\nСборка не дала executable nfqws2; privileged start пропущен.")
            parts.append("\nRuntime logs:")
            parts.append(gui_runtime_logs(root=root, profile_id=profile_id))
            return "\n\n".join(parts)
        next_step = 5
        total_steps = 7
    else:
        next_step = 1
        total_steps = 3

    parts.append(f"\nШаг {next_step}/{total_steps}: подготовка start-plan")
    parts.append(gui_prepare_default_start(root=root, profile_id=profile_id))
    parts.append(f"\nШаг {next_step + 1}/{total_steps}: подтверждение start-plan")
    parts.append(gui_confirm_plan(root=root, plan_id=DEFAULT_START_PLAN_ID))
    parts.append(f"\nШаг {next_step + 2}/{total_steps}: privileged start через графический polkit prompt")
    parts.append(gui_privileged_default_start(root=root, profile_id=profile_id))
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
                f"GUI button: Включить через графический запрос прав (pkexec) -> --default-start --confirm {self.start_plan_id}",
                "",
                "3) Статус:",
                "PYTHONPATH=gui python -m zap2_gui.app --default-status",
                "",
                "4) Отключение:",
                "PYTHONPATH=gui python -m zap2_gui.app --default-stop-plan",
                f"PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm {self.stop_plan_id}",
                f"GUI button: Отключить через графический запрос прав (pkexec) -> --default-stop --confirm {self.stop_plan_id}",
                "",
                "GUI не просит пароль в терминале: privileged start/stop идут через pkexec/polkit и требуют заранее сохранённый confirmation.",
            ]
        )


def gui_runtime_commands(profile_id: str = "default") -> GuiRuntimeCommandSet:
    return GuiRuntimeCommandSet(profile_id=profile_id)


def gui_default_build_deps(root: Path | None = None, profile_id: str = "default") -> str:
    """Показать dependency preflight для default build без установки пакетов."""

    discover_layout(root)
    return run_build_dependency_preflight("nfqws2").to_text()


def gui_prepare_default_build(root: Path | None = None, profile_id: str = "default") -> str:
    discover_layout(root)  # ранняя проверка workspace
    return prepare_default_build_plan(root=root, profile_id=profile_id).to_text()


def gui_execute_default_build(root: Path | None = None, profile_id: str = "default") -> str:
    """Исполнить подтверждённую локальную сборку из GUI без sudo."""

    discover_layout(root)
    result = execute_default_build(root=root, profile_id=profile_id, confirm_plan_id=DEFAULT_BUILD_PLAN_ID)
    status = gui_default_status(root=root, profile_id=profile_id)
    return "\n\n".join([result.to_text(), "После сборки текущий статус:", status])


def gui_prepare_default_start(root: Path | None = None, profile_id: str = "default") -> str:
    discover_layout(root)
    return prepare_default_workflow_plan(root=root, action="start", profile_id=profile_id).to_text()


def gui_prepare_default_stop(root: Path | None = None, profile_id: str = "default") -> str:
    discover_layout(root)
    return prepare_default_workflow_plan(root=root, action="stop", profile_id=profile_id).to_text()


def gui_confirm_plan(root: Path | None = None, plan_id: str = "") -> str:
    if not plan_id:
        raise ValueError("GUI confirmation требует явный plan id")
    return confirm_runtime_plan(root=root, plan_id=plan_id).to_text()


def gui_default_status(root: Path | None = None, profile_id: str = "default") -> str:
    return default_workflow_status(root=root, profile_id=profile_id).to_text()


def _with_status_after_action(root: Path | None, profile_id: str, action_text: str, body: str) -> str:
    """Append read-only status so GUI does not leave the owner guessing."""

    try:
        status = gui_default_status(root=root, profile_id=profile_id)
    except Exception as exc:  # pragma: no cover - defensive GUI diagnostic path
        status = f"Статус после действия не удалось прочитать: {exc}"
    return "\n\n".join([body, f"Статус после действия: {action_text}", status])


def _default_binary_guidance(root: Path | None) -> str | None:
    layout = discover_layout(root)
    binary = layout.root / "core" / "zapret2" / "nfq2" / "nfqws2"
    if binary.is_file() and binary.stat().st_mode & 0o111:
        return None
    return "\n".join(
        [
            "Default start заблокирован до pkexec: nfqws2 binary отсутствует или не исполняемый.",
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
            "pkexec/polkit сейчас не запускался; firewall/session не менялись.",
        ]
    )


def gui_privileged_default_start(root: Path | None = None, profile_id: str = "default") -> str:
    """Запустить confirmed default-start через pkexec/polkit из GUI."""

    guidance = _default_binary_guidance(root)
    if guidance:
        return _with_status_after_action(root, profile_id, "start blocked", guidance)
    result = execute_gui_privileged_workflow(
        root=root,
        action="start",
        profile_id=profile_id,
        confirm_plan_id=DEFAULT_START_PLAN_ID,
    ).to_text()
    return _with_status_after_action(root, profile_id, "start", result)


def gui_privileged_default_stop(root: Path | None = None, profile_id: str = "default") -> str:
    """Запустить confirmed default-stop через pkexec/polkit из GUI."""

    result = execute_gui_privileged_workflow(
        root=root,
        action="stop",
        profile_id=profile_id,
        confirm_plan_id=DEFAULT_STOP_PLAN_ID,
    ).to_text()
    return _with_status_after_action(root, profile_id, "stop", result)


def gui_privileged_default_start_command(root: Path | None = None, profile_id: str = "default") -> str:
    return gui_privileged_command_to_text(
        root=root,
        action="start",
        profile_id=profile_id,
        confirm_plan_id=DEFAULT_START_PLAN_ID,
    )


def gui_privileged_default_stop_command(root: Path | None = None, profile_id: str = "default") -> str:
    return gui_privileged_command_to_text(
        root=root,
        action="stop",
        profile_id=profile_id,
        confirm_plan_id=DEFAULT_STOP_PLAN_ID,
    )
