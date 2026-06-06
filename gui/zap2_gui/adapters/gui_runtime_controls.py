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
from .runtime_default_build import prepare_default_build_plan
from .runtime_state import confirm_runtime_plan
from .gui_privilege import (
    gui_privileged_command_to_text,
    execute_gui_privileged_workflow,
)
from ..project_paths import discover_layout

DEFAULT_BUILD_PLAN_ID = "runtime-default-manual-local-default-build-workflow-plan"
DEFAULT_START_PLAN_ID = "runtime-default-manual-local-default-start-workflow-plan"
DEFAULT_STOP_PLAN_ID = "runtime-default-manual-local-default-stop-workflow-plan"


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


def gui_prepare_default_build(root: Path | None = None, profile_id: str = "default") -> str:
    discover_layout(root)  # ранняя проверка workspace
    return prepare_default_build_plan(root=root, profile_id=profile_id).to_text()


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


def gui_privileged_default_start(root: Path | None = None, profile_id: str = "default") -> str:
    """Запустить confirmed default-start через pkexec/polkit из GUI."""

    return execute_gui_privileged_workflow(
        root=root,
        action="start",
        profile_id=profile_id,
        confirm_plan_id=DEFAULT_START_PLAN_ID,
    ).to_text()


def gui_privileged_default_stop(root: Path | None = None, profile_id: str = "default") -> str:
    """Запустить confirmed default-stop через pkexec/polkit из GUI."""

    return execute_gui_privileged_workflow(
        root=root,
        action="stop",
        profile_id=profile_id,
        confirm_plan_id=DEFAULT_STOP_PLAN_ID,
    ).to_text()


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
