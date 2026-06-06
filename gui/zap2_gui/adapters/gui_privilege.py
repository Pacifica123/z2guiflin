"""GUI-side privileged execution helpers for default workflow.

Модуль намеренно не реализует собственный ввод пароля и не принимает пароль как
строку. Для графического запроса прав используется системный polkit через
``pkexec``. Это оставляет пароль/подтверждение в зоне ответственности desktop
authentication agent и не смешивает GUI с терминальным ``sudo``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ..project_paths import discover_layout

DEFAULT_START_PLAN_ID = "runtime-default-manual-local-default-start-workflow-plan"
DEFAULT_STOP_PLAN_ID = "runtime-default-manual-local-default-stop-workflow-plan"
SUPPORTED_GUI_PRIVILEGED_ACTIONS = ("start", "stop")


@dataclass(frozen=True)
class GuiPrivilegedCommand:
    """Команда для запуска privileged default workflow через polkit."""

    action: str
    profile_id: str
    confirm_plan_id: str
    argv: tuple[str, ...]
    cwd: Path
    uses_pkexec: bool = True
    asks_password_in_terminal: bool = False
    stores_password: bool = False

    def to_text(self) -> str:
        command = " ".join(self.argv)
        return "\n".join(
            [
                f"GUI privileged workflow command для action: {self.action}",
                f"profile: {self.profile_id}",
                f"confirm plan id: {self.confirm_plan_id}",
                f"cwd: {self.cwd}",
                f"command: {command}",
                "uses pkexec/polkit: yes",
                "asks password in terminal: no",
                "stores password: no",
                f"runtime drop identity: {'upstream default' if self.action == 'start' else 'not changed'}",
                "requires saved runtime confirmation: yes",
                "bootstrap mixed in: no",
                "contains remote bootstrap: no",
                "contains upstream installer script: no",
            ]
        )


@dataclass(frozen=True)
class GuiPrivilegedResult:
    """Результат GUI-triggered privileged workflow."""

    action: str
    profile_id: str
    confirm_plan_id: str
    returncode: int
    stdout: str
    stderr: str
    command: GuiPrivilegedCommand
    skipped_reason: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.skipped_reason

    def to_text(self) -> str:
        lines = [
            f"GUI privileged workflow {self.action}: {'OK' if self.ok else 'FAILED'}",
            f"profile: {self.profile_id}",
            f"confirm plan id: {self.confirm_plan_id}",
            f"return code: {self.returncode}",
            "uses pkexec/polkit: yes",
            "asks password in terminal: no",
            "stores password: no",
        ]
        if self.skipped_reason:
            lines.append(f"message: {self.skipped_reason}")
        if self.stdout.strip():
            lines.extend(["", "stdout:", self.stdout.rstrip()])
        if self.stderr.strip():
            lines.extend(["", "stderr:", self.stderr.rstrip()])
        if not self.stdout.strip() and not self.stderr.strip() and not self.skipped_reason:
            lines.append("message: команда завершилась без вывода")
        return "\n".join(lines)


def _default_plan_id_for_action(action: str) -> str:
    if action == "start":
        return DEFAULT_START_PLAN_ID
    if action == "stop":
        return DEFAULT_STOP_PLAN_ID
    raise ValueError(f"Неподдерживаемое GUI privileged action: {action}")


def is_pkexec_available() -> bool:
    """Return whether pkexec is available in PATH."""

    return shutil.which("pkexec") is not None


def build_gui_privileged_command(
    *,
    root: Path | None = None,
    action: str,
    profile_id: str = "default",
    confirm_plan_id: str | None = None,
) -> GuiPrivilegedCommand:
    """Build a pkexec command without executing it."""

    if action not in SUPPORTED_GUI_PRIVILEGED_ACTIONS:
        raise ValueError(f"Неподдерживаемое GUI privileged action: {action}")
    layout = discover_layout(root)
    plan_id = confirm_plan_id or _default_plan_id_for_action(action)
    pythonpath = str(layout.root / "gui")
    executable = str(Path(sys.executable))
    bridge_env = ()
    if action == "start":
        bridge_env = (
            "ZAP2_GUI_PRIVILEGE_BRIDGE=pkexec",
            "ZAP2_RUNTIME_DROP_IDENTITY=upstream-default",
        )
    argv = (
        "pkexec",
        "env",
        f"PYTHONPATH={pythonpath}",
        *bridge_env,
        executable,
        "-m",
        "zap2_gui.app",
        f"--default-{action}",
        "--profile",
        profile_id,
        "--confirm",
        plan_id,
    )
    return GuiPrivilegedCommand(
        action=action,
        profile_id=profile_id,
        confirm_plan_id=plan_id,
        argv=argv,
        cwd=layout.root,
    )


def gui_privileged_command_to_text(
    *,
    root: Path | None = None,
    action: str,
    profile_id: str = "default",
    confirm_plan_id: str | None = None,
) -> str:
    return build_gui_privileged_command(
        root=root,
        action=action,
        profile_id=profile_id,
        confirm_plan_id=confirm_plan_id,
    ).to_text()


def execute_gui_privileged_workflow(
    *,
    root: Path | None = None,
    action: str,
    profile_id: str = "default",
    confirm_plan_id: str | None = None,
    timeout_seconds: int = 300,
) -> GuiPrivilegedResult:
    """Execute default start/stop through pkexec and return captured output.

    This function is meant for a local PyQt button. It never accepts a password
    and never falls back to terminal ``sudo``. If a desktop polkit agent is not
    running, pkexec will fail and the result explains that the graphical auth
    agent must be available.
    """

    command = build_gui_privileged_command(
        root=root,
        action=action,
        profile_id=profile_id,
        confirm_plan_id=confirm_plan_id,
    )
    if not is_pkexec_available():
        return GuiPrivilegedResult(
            action=action,
            profile_id=profile_id,
            confirm_plan_id=command.confirm_plan_id,
            returncode=127,
            stdout="",
            stderr="",
            command=command,
            skipped_reason=(
                "pkexec не найден. Установите polkit/pkexec и запустите GUI в desktop-сессии "
                "с работающим polkit authentication agent. Терминальный sudo здесь намеренно не используется."
            ),
        )

    env = os.environ.copy()
    # pkexec сбрасывает окружение, но локальному subprocess полезно сохранить
    # нейтральные desktop-переменные для поиска графического authentication agent.
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):
        if key in os.environ:
            env[key] = os.environ[key]
    completed = subprocess.run(
        list(command.argv),
        cwd=command.cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout_seconds,
        env=env,
    )
    stderr = completed.stderr
    if completed.returncode != 0 and "No authentication agent" in stderr:
        stderr += (
            "\n\nПодсказка: pkexec не нашёл графический authentication agent. "
            "Запустите polkit agent вашей среды рабочего стола или используйте desktop-сессию, "
            "где системный графический запрос прав уже работает."
        )
    return GuiPrivilegedResult(
        action=action,
        profile_id=profile_id,
        confirm_plan_id=command.confirm_plan_id,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=stderr,
        command=command,
    )
