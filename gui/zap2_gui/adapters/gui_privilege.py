"""GUI-side privileged execution helpers for default workflow.

P02 removes the historical ``sudo -A env PYTHONPATH=<workspace> python -m
zap2_gui.app`` bridge.  The GUI remains unprivileged and delegates only finite,
plan-bound effects to a separately installed root-owned executor.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .workspace_profiles import load_workspace_catalog
from .privileged_executor import (
    DEFAULT_PRIVILEGED_EXECUTOR,
    bounded_privilege_preview,
    execute_bounded_default_workflow,
    privileged_executor_status,
)
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
        return self.backend.startswith("sudo-askpass")

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
                "root imports writable project Python: no",
                "privileged argv surface: fixed helper + finite action request hash",
                "request body transport: canonical JSON bytes over stdin",
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

    @property
    def success(self) -> bool:
        """Backward-compatible success alias used by GUI transaction adapters."""

        return self.ok

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


@dataclass(frozen=True)
class GuiPrivilegedProbeCommand:
    """Read-only diagnostic command executed through GUI sudo askpass."""

    probe: str
    profile_id: str
    wait_seconds: int
    argv: tuple[str, ...]
    cwd: Path
    env_overrides: dict[str, str] = field(default_factory=dict)
    backend: str = "sudo-askpass"
    asks_password_in_terminal: bool = False
    stores_password: bool = False
    mutates_firewall_or_services: bool = False

    @property
    def uses_sudo_askpass(self) -> bool:
        return self.backend.startswith("sudo-askpass")

    def to_text(self) -> str:
        return "\n".join(
            [
                f"GUI privileged read-only probe: {self.probe}",
                f"profile: {self.profile_id}",
                f"wait seconds: {self.wait_seconds}",
                f"cwd: {self.cwd}",
                f"command: {' '.join(self.argv)}",
                "uses sudo askpass: yes",
                "uses pkexec/polkit: no",
                "asks password in terminal: no",
                "stores password: no",
                "read-only probe: yes",
                "applies firewall/services now: no",
                f"askpass helper: {self.env_overrides.get('SUDO_ASKPASS', 'auto')}",
            ]
        )


@dataclass(frozen=True)
class GuiPrivilegedProbeResult:
    """Result of a GUI privileged read-only diagnostic probe."""

    probe: str
    profile_id: str
    wait_seconds: int
    returncode: int
    stdout: str
    stderr: str
    command: GuiPrivilegedProbeCommand
    skipped_reason: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.skipped_reason

    def to_text(self) -> str:
        lines = [
            f"GUI privileged read-only probe {self.probe}: {'OK' if self.ok else 'FAILED'}",
            f"profile: {self.profile_id}",
            f"wait seconds: {self.wait_seconds}",
            f"return code: {self.returncode}",
            "uses sudo askpass: yes",
            "asks password in terminal: no",
            "stores password: no",
            "read-only: yes",
            "applies firewall/services now: no",
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



def default_plan_id_for_action(root: Path | None = None, action: str = "start", profile_id: str = "default") -> str:
    if action not in SUPPORTED_GUI_PRIVILEGED_ACTIONS:
        raise ValueError(f"Неподдерживаемое GUI privileged action: {action}")
    layout = discover_layout(root)
    catalog = load_workspace_catalog(layout.root)
    profiles = catalog.profile_by_id()
    if profile_id not in profiles:
        raise ValueError(f"Неизвестный workspace-профиль: {profile_id}")
    strategy_id = profiles[profile_id].strategy_id
    return f"runtime-{profile_id}-{strategy_id}-default-{action}-workflow-plan"


def _default_plan_id_for_action(action: str) -> str:
    # Backward-compatible constant for tests/docs when no root is available.
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
    """Build a read-only preview of the P02 bounded privilege shape."""

    if action not in SUPPORTED_GUI_PRIVILEGED_ACTIONS:
        raise ValueError(f"Неподдерживаемое GUI privileged action: {action}")
    layout = discover_layout(root)
    plan_id = confirm_plan_id or default_plan_id_for_action(layout.root, action=action, profile_id=profile_id)
    # Preview must stay read-only.  The path is deterministic, but the helper
    # file itself is created only when execution is actually requested.
    askpass = _askpass_script_path(layout.root)
    argv = bounded_privilege_preview(layout.root, askpass=True)
    return GuiPrivilegedCommand(
        action=action,
        profile_id=profile_id,
        confirm_plan_id=plan_id,
        argv=argv,
        cwd=layout.root,
        env_overrides={"SUDO_ASKPASS": str(askpass)},
        backend="sudo-askpass-bounded-executor",
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


def build_gui_privileged_discord_probe_command(
    *,
    root: Path | None = None,
    profile_id: str = "default",
    wait_seconds: int = 30,
) -> GuiPrivilegedProbeCommand:
    """Report the P02 truth for the old privileged Discord diagnostic lane.

    P02 deliberately does not widen the finite root executor for a diagnostic
    probe.  The owner-run/non-privileged diagnostic remains available; this GUI
    root bridge is staged until a dedicated bounded action is justified.
    """

    layout = discover_layout(root)
    wait_seconds = max(0, min(int(wait_seconds), 600))
    return GuiPrivilegedProbeCommand(
        probe="discord-pretls-guided-probe",
        profile_id=profile_id,
        wait_seconds=wait_seconds,
        argv=("P02-STAGED", "discord-pretls-guided-probe", "no-root-execution"),
        cwd=layout.root,
        env_overrides={},
        backend="staged-no-root",
    )


def execute_gui_privileged_discord_probe(
    *,
    root: Path | None = None,
    profile_id: str = "default",
    wait_seconds: int = 30,
    timeout_seconds: int = 420,
) -> GuiPrivilegedProbeResult:
    """Refuse the historical broad-root diagnostic bridge under P02."""

    del timeout_seconds
    command = build_gui_privileged_discord_probe_command(root=root, profile_id=profile_id, wait_seconds=wait_seconds)
    return GuiPrivilegedProbeResult(
        probe=command.probe,
        profile_id=profile_id,
        wait_seconds=command.wait_seconds,
        returncode=2,
        stdout="",
        stderr="",
        command=command,
        skipped_reason=(
            "P02: privileged Discord probe staged/unsupported. "
            "Broad root import of writable GUI code removed; use the owner-run read-only diagnostic lane."
        ),
    )


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
    """Execute default start/stop while the GUI process remains unprivileged."""

    del timeout_seconds
    command = build_gui_privileged_command(
        root=root,
        action=action,
        profile_id=profile_id,
        confirm_plan_id=confirm_plan_id,
    )
    status = privileged_executor_status(command.cwd)
    if not status.ready:
        return GuiPrivilegedResult(
            action=action,
            profile_id=profile_id,
            confirm_plan_id=command.confirm_plan_id,
            returncode=126,
            stdout="",
            stderr="",
            command=command,
            skipped_reason=status.message,
        )
    if not is_sudo_available():
        return GuiPrivilegedResult(
            action=action, profile_id=profile_id, confirm_plan_id=command.confirm_plan_id,
            returncode=127, stdout="", stderr="", command=command,
            skipped_reason="sudo не найден; bounded privileged executor недоступен",
        )
    try:
        askpass = ensure_sudo_askpass_helper(command.cwd)
        result = execute_bounded_default_workflow(
            command.cwd,
            action=action,
            profile_id=profile_id,
            confirm_plan_id=command.confirm_plan_id,
            askpass=askpass,
            installed_path=DEFAULT_PRIVILEGED_EXECUTOR,
        )
        ok_states = {"started", "stopped"}
        return GuiPrivilegedResult(
            action=action, profile_id=profile_id, confirm_plan_id=command.confirm_plan_id,
            returncode=0 if result.state in ok_states else 1,
            stdout=result.to_text(), stderr="", command=command,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return GuiPrivilegedResult(
            action=action, profile_id=profile_id, confirm_plan_id=command.confirm_plan_id,
            returncode=2, stdout="", stderr=str(exc), command=command,
        )

