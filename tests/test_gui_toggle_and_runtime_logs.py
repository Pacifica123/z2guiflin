from __future__ import annotations

import os
from pathlib import Path

from zap2_gui.adapters.gui_privilege import build_gui_privileged_command
from zap2_gui.adapters.gui_runtime_controls import gui_default_toggle_label, gui_runtime_logs
from zap2_gui.adapters.runtime_logs import runtime_log_snapshot
from zap2_gui.adapters import runtime_session
from zap2_gui.project_paths import discover_layout


def test_gui_privileged_start_uses_sudo_askpass_not_pkexec() -> None:
    command = build_gui_privileged_command(action="start")
    assert "sudo" == command.argv[0]
    assert "-A" in command.argv
    assert "env" not in command.argv
    assert not any("PYTHONPATH=" in item for item in command.argv)
    assert "/usr/local/libexec/zap2-runtime-executor" in command.argv
    assert command.uses_sudo_askpass is True
    assert "SUDO_ASKPASS" in command.env_overrides
    assert "--request-hash" in command.argv


def test_gui_privileged_stop_uses_sudo_askpass() -> None:
    command = build_gui_privileged_command(action="stop")
    assert command.argv[0] == "sudo"
    assert "-A" in command.argv
    assert "--request-hash" in command.argv
    assert not any("PYTHONPATH=" in item for item in command.argv)


def test_runtime_session_sudo_owner_path_remains_default(monkeypatch) -> None:
    root = discover_layout().root
    monkeypatch.delenv("ZAP2_RUNTIME_DROP_IDENTITY", raising=False)
    monkeypatch.setenv("SUDO_UID", "1000")
    monkeypatch.setenv("SUDO_GID", "1000")
    monkeypatch.setattr(runtime_session.os, "geteuid", lambda: 0, raising=False)
    identity = runtime_session._detect_drop_identity(root)  # noqa: SLF001 - adapter contract regression
    assert identity is not None
    assert identity.uid == 1000
    assert identity.gid == 1000
    assert identity.source == "sudo-owner"


def test_runtime_session_keeps_legacy_polkit_root_mode_for_diagnostics(monkeypatch) -> None:
    root = discover_layout().root
    monkeypatch.setenv("ZAP2_RUNTIME_DROP_IDENTITY", "polkit-root")
    monkeypatch.setattr(runtime_session.os, "geteuid", lambda: 0, raising=False)
    identity = runtime_session._detect_drop_identity(root)  # noqa: SLF001 - adapter contract regression
    assert identity is not None
    assert identity.uid == 0
    assert identity.gid == 0
    assert identity.source == "legacy-polkit-root-preserve"


def test_runtime_logs_snapshot_reads_stderr_tail(tmp_path: Path) -> None:
    root = discover_layout().root
    log_root = root / ".zap2" / "runtime" / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    runtime_log = log_root / "default.runtime.jsonl"
    stderr_log = log_root / "default.nfqws2.stderr.log"
    runtime_log.write_text(
        '{"createdAt":"2026-06-07T00:00:00Z","level":"error","eventType":"default-start-failed","message":"nfq_create_queue failed"}\n',
        encoding="utf-8",
    )
    stderr_log.write_text("nfq_create_queue(): Operation not permitted\n", encoding="utf-8")
    snapshot = runtime_log_snapshot(root=root)
    text = snapshot.to_text()
    assert "default-start-failed" in text
    assert "nfq_create_queue(): Operation not permitted" in text
    assert "read-only: yes" in text


def test_gui_toggle_label_is_stable() -> None:
    label = gui_default_toggle_label()
    assert label in {"Включить Default", "Выключить Default"}
    assert "Runtime logs" in gui_runtime_logs()


def test_gui_privileged_discord_probe_is_staged_not_broad_root() -> None:
    from zap2_gui.adapters.gui_privilege import build_gui_privileged_discord_probe_command

    command = build_gui_privileged_discord_probe_command(wait_seconds=30)
    assert command.argv[0] == "P02-STAGED"
    assert "sudo" not in command.argv
    assert "PYTHONPATH" not in " ".join(command.argv)
    assert command.uses_sudo_askpass is False
    assert command.mutates_firewall_or_services is False
    assert not command.env_overrides


def test_overview_action_output_moves_verbose_text_to_logs(tmp_path: Path) -> None:
    from zap2_gui.adapters.gui_runtime_controls import (
        gui_overview_action_output_to_text,
        gui_runtime_logs_with_overview_output,
        write_gui_overview_action_output,
    )

    project = tmp_path / "project"
    project.mkdir()
    write_gui_overview_action_output(project, "default", "Probe", "line one\nline two")
    text = gui_overview_action_output_to_text(project)

    assert "Overview action output" in text
    assert "action: Probe" in text
    assert "line two" in text
    combined = gui_runtime_logs_with_overview_output(project)
    assert "Runtime logs" in combined
    assert "action: Probe" in combined
