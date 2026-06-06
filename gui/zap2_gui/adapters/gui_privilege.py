"""GUI-side privileged execution helpers for default workflow.

Stage 12 switches the GUI privileged bridge from ``pkexec`` to graphical
``sudo -A`` askpass. On the target system, pkexec successfully authenticated but
started ``nfqws2`` without the capabilities needed for ``nfq_create_queue()``.
The normal terminal ``sudo`` path had already worked, so GUI uses the same sudo
execution semantics while still asking the password in a graphical window.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..project_paths import discover_layout

DEFAULT_START_PLAN_ID = "runtime-default-manual-local-default-start-workflow-plan"
DEFAULT_STOP_PLAN_ID = "runtime-default-manual-local-default-stop-workflow-plan"
SUPPORTED_GUI_PRIVILEGED_ACTIONS = ("start", "stop")


@dataclass(frozen=True)
class GuiPrivilegedCommand:
    """Команда для запуска privileged default workflow через GUI sudo askpass."""

    action: str
    profile_id: str
    confirm_plan_id: str
    argv: tuple[str, ...]
    cwd: Path
    env_overrides: dict[str, str] = field(default_factory=dict)
    backend: str = "sudo-askpass"
    asks_password_in_terminal: bool = False
    stores_password: bool = False

    @property
    def uses_pkexec(self) -> bool:
        return self.backend == "pkexec"

    @property
    def uses_sudo_askpass(self) -> bool:
        return self.backend == "sudo-askpass"

    def to_text(self) -> str:
        command = " ".join(self.argv)
        return "\n".join(
            [
                f"GUI privileged workflow command для action: {self.action}",
                f"profile: {self.profile_id}",
                f"confirm plan id: {self.confirm_plan_id}",
                f"cwd: {self.cwd}",
                f"command: {command}",
                "uses sudo askpass: yes",
                "uses pkexec/polkit: no",
                "asks password in terminal: no",
                "stores password: no",
                "password handled by: SUDO_ASKPASS helper",
                f"askpass helper: {self.env_overrides.get('SUDO_ASKPASS', 'auto')}",
                f"runtime drop identity: {'sudo-owner via SUDO_UID/SUDO_GID' if self.action == 'start' else 'not changed'}",
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
            "uses sudo askpass: yes",
            "uses pkexec/polkit: no",
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


def is_sudo_available() -> bool:
    """Return whether sudo is available in PATH."""

    return shutil.which("sudo") is not None


def _askpass_script_path(root: Path) -> Path:
    return root / ".zap2" / "runtime" / "askpass" / "zap2-sudo-askpass"


def ensure_sudo_askpass_helper(root: Path | None = None) -> Path:
    """Create an executable askpass helper script inside workspace state.

    ``sudo -A`` requires ``SUDO_ASKPASS`` to point to an executable. We create a
    tiny wrapper that starts ``python -m zap2_gui.askpass`` with the current
    project's GUI package on PYTHONPATH. The helper does not store the password;
    it only prints it to stdout as required by sudo's askpass protocol.
    """

    layout = discover_layout(root)
    helper = _askpass_script_path(layout.root)
    helper.parent.mkdir(parents=True, exist_ok=True)
    python = str(Path(sys.executable))
    pythonpath = str(layout.root / "gui")
    helper.write_text(
        "#!/usr/bin/env sh\n"
        "# Generated by Zap2 GUI. Do not edit; regenerated when needed.\n"
        f"PYTHONPATH={pythonpath!r} exec {python!r} -m zap2_gui.askpass \"$@\"\n",
        encoding="utf-8",
    )
    helper.chmod(0o700)
    return helper


def build_gui_privileged_command(
    *,
    root: Path | None = None,
    action: str,
    profile_id: str = "default",
    confirm_plan_id: str | None = None,
) -> GuiPrivilegedCommand:
    """Build a graphical sudo-askpass command without executing it."""

    if action not in SUPPORTED_GUI_PRIVILEGED_ACTIONS:
        raise ValueError(f"Неподдерживаемое GUI privileged action: {action}")
    layout = discover_layout(root)
    plan_id = confirm_plan_id or _default_plan_id_for_action(action)
    pythonpath = str(layout.root / "gui")
    executable = str(Path(sys.executable))
    askpass = ensure_sudo_askpass_helper(layout.root)
    bridge_env = ("ZAP2_GUI_PRIVILEGE_BRIDGE=sudo-askpass",)
    argv = (
        "sudo",
        "-A",
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
        env_overrides={"SUDO_ASKPASS": str(askpass)},
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


def _desktop_env_for_askpass(command: GuiPrivilegedCommand) -> dict[str, str]:
    env = os.environ.copy()
    env.update(command.env_overrides)
    env.setdefault("ZAP2_SUDO_ASKPASS_PROMPT", "Введите пароль sudo для Zap2 GUI")
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def execute_gui_privileged_workflow(
    *,
    root: Path | None = None,
    action: str,
    profile_id: str = "default",
    confirm_plan_id: str | None = None,
    timeout_seconds: int = 300,
) -> GuiPrivilegedResult:
    """Execute default start/stop through graphical sudo askpass.

    This function is meant for a local PyQt button. It never asks for a password
    in the terminal and never logs/stores the password. ``sudo -A`` delegates
    password input to ``SUDO_ASKPASS`` and then runs the same root path as a
    successful manual ``sudo PYTHONPATH=gui python -m zap2_gui.app ...``.
    """

    command = build_gui_privileged_command(
        root=root,
        action=action,
        profile_id=profile_id,
        confirm_plan_id=confirm_plan_id,
    )
    if not is_sudo_available():
        return GuiPrivilegedResult(
            action=action,
            profile_id=profile_id,
            confirm_plan_id=command.confirm_plan_id,
            returncode=127,
            stdout="",
            stderr="",
            command=command,
            skipped_reason=(
                "sudo не найден. Для GUI privileged workflow нужен sudo с поддержкой -A/SUDO_ASKPASS. "
                "Терминальный ввод пароля намеренно не используется."
            ),
        )

    completed = subprocess.run(
        list(command.argv),
        cwd=command.cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout_seconds,
        env=_desktop_env_for_askpass(command),
    )
    stderr = completed.stderr
    if completed.returncode != 0 and "no askpass program" in stderr.lower():
        stderr += (
            "\n\nПодсказка: sudo не смог запустить SUDO_ASKPASS helper. "
            "Проверьте, что GUI запущен в desktop-сессии с DISPLAY/WAYLAND_DISPLAY."
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
