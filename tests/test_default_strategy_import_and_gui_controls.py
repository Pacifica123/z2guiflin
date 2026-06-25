from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from zap2_gui.adapters.gui_runtime_controls import (
    DEFAULT_BUILD_PLAN_ID,
    DEFAULT_START_PLAN_ID,
    gui_default_status,
    gui_execute_default_build,
    gui_prepare_default_start,
    gui_privileged_default_start,
    gui_privileged_default_start_command,
    gui_runtime_commands,
)
from zap2_gui.adapters.gui_privilege import build_gui_privileged_command
from zap2_gui.adapters.runtime_plan_generator import create_runtime_plan
from zap2_gui.adapters.runtime_session import build_runtime_session_config
from zap2_gui.adapters.runtime_state import confirm_runtime_plan, prepare_runtime_plan
from zap2_gui.adapters.workspace_profiles import load_workspace_catalog, workspace_strategy_to_text
from zap2_gui.app import main

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    ignore = shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache")
    shutil.copytree(ROOT, project, ignore=ignore)
    return project


def _make_fake_binary(project: Path) -> None:
    binary = project / "core/zapret2/nfq2/nfqws2"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/usr/bin/env sh\nsleep 30\n", encoding="utf-8")
    binary.chmod(0o755)


def test_windows_default_preset_is_imported_as_reference() -> None:
    source = ROOT / "strategies/imported/windows-default-v1-game-filter.txt"
    meta = json.loads((ROOT / "strategies/imported/windows-default-v1-game-filter.json").read_text(encoding="utf-8"))
    text = source.read_text(encoding="utf-8")

    assert "# Preset: Default v1 (game filter)" in text
    assert "--wf-tcp-out" in text
    assert meta["presetName"] == "Default v1 (game filter)"
    assert meta["importPolicy"] == "partial-linux-bridge"
    assert "lists/youtube.txt" in meta["hostlistRefs"]


def test_default_hostlist_seed_is_not_empty() -> None:
    hosts = [
        line.strip()
        for line in (ROOT / "profiles/hostlists/default.hosts").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert len(hosts) >= 20
    for required in ("youtube.com", "googlevideo.com", "discord.com", "telegram.org"):
        assert required in hosts


def test_manual_local_strategy_exposes_default_source_and_runtime_args() -> None:
    catalog = load_workspace_catalog(ROOT)
    strategy = catalog.strategy_by_id()["manual-local"]

    assert strategy.source_preset is not None
    assert strategy.source_preset["name"] == "Default v1 (game filter)"
    assert strategy.source_preset["windowsOptionsExecuted"] is False
    assert any(arg.startswith("--lua-init=@core/zapret2/lua/zapret-lib.lua") for arg in strategy.runtime_args)
    assert any(arg.startswith("--lua-desync=") for arg in strategy.runtime_args)
    assert not any(arg.startswith("--wf-") for arg in strategy.runtime_args)
    assert "Default v1 (game filter)" in workspace_strategy_to_text("manual-local", ROOT)


def test_runtime_plan_and_session_config_include_strategy_runtime_args(tmp_path: Path, monkeypatch) -> None:
    project = _copy_project(tmp_path)
    _make_fake_binary(project)
    prepare_runtime_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, "runtime-default-manual-local-start-plan")

    monkeypatch.delenv("ZAP2_RUNTIME_DEBUG", raising=False)
    config = build_runtime_session_config(project, profile_id="default")
    assert "--debug=@" not in "\n".join(config.runtime_args)
    lua_args = [arg for arg in config.runtime_args if arg.startswith("--lua-init=@")]
    assert len(lua_args) == 2
    assert any("/zap2-runtime-inputs" in arg and arg.endswith("/lua/zapret-lib.lua") for arg in lua_args)
    assert not any("@core/zapret2/lua/" in arg for arg in config.runtime_args)
    assert "--lua-desync=multisplit:pos=1:seqovl=5:seqovl_pattern=0x1603030000" in config.runtime_args

    monkeypatch.setenv("ZAP2_RUNTIME_DEBUG", "1")
    debug_config = build_runtime_session_config(project, profile_id="default")
    assert any(arg.startswith("--debug=@") for arg in debug_config.runtime_args)


def test_runtime_plan_text_shows_default_source_and_args() -> None:
    text = create_runtime_plan(ROOT, action="start", profile_id="default").to_text()
    assert "strategy source: Default v1 (game filter)" in text
    assert "strategy runtime args:" in text
    assert "--lua-desync=" in text


def test_gui_runtime_controls_are_confirmation_gate_wrappers(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    start_text = gui_prepare_default_start(project)
    commands = gui_runtime_commands().to_text()
    status = gui_default_status(project)

    assert DEFAULT_START_PLAN_ID in start_text
    assert "GUI button: Включить через графический sudo-запрос" in commands
    assert "sudo -A/SUDO_ASKPASS" in commands
    assert "терминале" in commands
    assert "Default workflow status:" in status
    assert "executes now: no" in status


def test_gui_privileged_command_uses_sudo_askpass_not_terminal_password(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    command = build_gui_privileged_command(root=project, action="start")
    text = gui_privileged_default_start_command(project)

    assert command.argv[0] == "sudo"
    assert "-A" in command.argv
    assert "env" in command.argv
    assert "--default-start" in command.argv
    assert DEFAULT_START_PLAN_ID in command.argv
    assert command.asks_password_in_terminal is False
    assert command.stores_password is False
    assert "asks password in terminal: no" in text
    assert "stores password: no" in text
    assert "PYTHONPATH=" in " ".join(command.argv)
    assert "SUDO_ASKPASS" in command.env_overrides
    assert "uses sudo askpass: yes" in text


def test_gui_privileged_command_cli_preview_is_read_only(capsys) -> None:
    assert main(["--gui-privileged-command", "start"]) == 0
    out = capsys.readouterr().out
    assert "GUI privileged workflow command для action: start" in out
    assert "sudo" in out
    assert "SUDO_ASKPASS" in out
    assert "asks password in terminal: no" in out


def test_default_status_cli_is_read_only(capsys) -> None:
    assert main(["--default-status"]) == 0
    out = capsys.readouterr().out
    assert "Default workflow status:" in out
    assert "executes now: no" in out



def test_gui_start_blocks_before_privileged_start_when_binary_missing(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    text = gui_privileged_default_start(project)

    assert "Default start заблокирован до privileged start" in text
    assert "nfqws2 binary отсутствует" in text
    assert "sudo-askpass сейчас не запускался" in text
    assert "Статус после действия: start blocked" in text


def test_gui_build_execute_reports_status_with_confirmed_fake_build(tmp_path: Path, monkeypatch) -> None:
    project = _copy_project(tmp_path)
    plan_text = __import__("zap2_gui.adapters.gui_runtime_controls", fromlist=["gui_prepare_default_build"]).gui_prepare_default_build(project)
    assert DEFAULT_BUILD_PLAN_ID in plan_text
    confirm_runtime_plan(project, DEFAULT_BUILD_PLAN_ID)

    # Подменяем make на безопасный локальный fake, чтобы проверить именно GUI wrapper.
    nfq = project / "core/zapret2/nfq2/nfqws2"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_make = fake_bin / "make"
    fake_make.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, stat\n"
        f"p = pathlib.Path({str(nfq)!r})\n"
        "p.parent.mkdir(parents=True, exist_ok=True)\n"
        "p.write_text('#!/bin/sh\\nsleep 30\\n')\n"
        "p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)\n",
        encoding="utf-8",
    )
    fake_make.chmod(0o755)
    from zap2_gui.adapters import runtime_default_build as build_module
    from zap2_gui.adapters.build_dependencies import BuildDependencyReport

    monkeypatch.setattr(build_module, "_is_root", lambda: False)
    monkeypatch.setattr(
        build_module,
        "run_build_dependency_preflight",
        lambda target: BuildDependencyReport(
            target=target,
            stage="test",
            marker="test",
            checks=(),
            install_hints={},
        ),
    )
    old_path = os.environ.get("PATH", "")
    try:
        os.environ["PATH"] = f"{fake_bin}:{old_path}"
        text = gui_execute_default_build(project)
    finally:
        os.environ["PATH"] = old_path

    assert "Default build: built" in text
    assert "После сборки текущий статус:" in text
    assert nfq.exists()
    assert os.access(nfq, os.X_OK)
