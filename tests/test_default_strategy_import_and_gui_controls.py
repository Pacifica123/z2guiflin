from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from zap2_gui.adapters.gui_runtime_controls import (
    DEFAULT_START_PLAN_ID,
    gui_default_status,
    gui_prepare_default_start,
    gui_runtime_commands,
)
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
    assert "--lua-init=@core/zapret2/lua/zapret-lib.lua" in config.runtime_args
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
    assert "sudo PYTHONPATH=gui python -m zap2_gui.app --default-start" in commands
    assert "GUI не запускает sudo" in commands
    assert "Default workflow status:" in status
    assert "executes now: no" in status


def test_default_status_cli_is_read_only(capsys) -> None:
    assert main(["--default-status"]) == 0
    out = capsys.readouterr().out
    assert "Default workflow status:" in out
    assert "executes now: no" in out
