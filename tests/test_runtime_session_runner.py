import json
import shutil
import stat
from pathlib import Path

import pytest

from zap2_gui.adapters import runtime_session as runtime_session_module
from zap2_gui.adapters.runtime_session import (
    build_runtime_session_config,
    runtime_session_status,
    start_runtime_session,
    stop_runtime_session,
)
from zap2_gui.adapters.runtime_state import confirm_runtime_plan, prepare_runtime_plan

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc")
    shutil.copytree(ROOT, target, ignore=ignore)
    return target


def _install_fake_nfqws2(project: Path) -> Path:
    binary = project / "core" / "zapret2" / "nfq2" / "nfqws2"
    binary.write_text(
        """#!/usr/bin/env python3
import pathlib
import signal
import sys
import time

running = True

def stop(signum, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, stop)
for arg in sys.argv[1:]:
    if arg.startswith('@'):
        pathlib.Path(arg[1:]).read_text(encoding='utf-8')
while running:
    time.sleep(0.1)
""",
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return binary


def test_session_start_requires_confirmed_plan(tmp_path):
    project = _copy_project(tmp_path)
    _install_fake_nfqws2(project)

    with pytest.raises(ValueError, match="Prepared start-plan"):
        start_runtime_session(project, profile_id="default")

    prepared = prepare_runtime_plan(project, action="start", profile_id="default")
    with pytest.raises(ValueError, match="Confirmation"):
        start_runtime_session(project, profile_id="default")

    confirm_runtime_plan(project, prepared.plan_id)
    config = build_runtime_session_config(project, profile_id="default")
    assert config.binary_path.exists()
    assert config.plan_hash == prepared.plan_hash
    assert config.args_path.name == "default.nfqws2.args"


def test_session_runner_starts_statuses_and_stops_only_owned_process(tmp_path):
    project = _copy_project(tmp_path)
    _install_fake_nfqws2(project)
    prepared = prepare_runtime_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, prepared.plan_id)

    started = start_runtime_session(project, profile_id="default")
    try:
        assert started.state == "running"
        assert started.pid is not None
        assert started.plan_hash == prepared.plan_hash
        assert started.session_path.exists()

        session = json.loads(started.session_path.read_text(encoding="utf-8"))
        assert session["marker"] == "zap2-runtime-session-v1"
        assert session["mutatesFirewallOrServicesNow"] is False
        assert session["managesServiceNow"] is False
        assert session["containsBootstrap"] is False
        assert session["containsUpstreamInstallerScript"] is False

        status = runtime_session_status(project, profile_id="default")
        assert status.state == "running"
        assert status.pid == started.pid

        stopped = stop_runtime_session(project, profile_id="default")
        assert stopped.state == "stopped"
        after = runtime_session_status(project, profile_id="default")
        assert after.state == "stopped"
    finally:
        # Идемпотентная страховка для случая падения assertion до stop.
        try:
            stop_runtime_session(project, profile_id="default")
        except Exception:
            pass


def test_session_start_rejects_missing_binary_even_with_confirmation(tmp_path):
    project = _copy_project(tmp_path)
    prepared = prepare_runtime_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, prepared.plan_id)

    with pytest.raises(ValueError, match="nfqws2 binary"):
        build_runtime_session_config(project, profile_id="default")


def test_session_stop_refuses_foreign_session_marker(tmp_path):
    project = _copy_project(tmp_path)
    session_dir = project / ".zap2" / "runtime" / "sessions"
    session_dir.mkdir(parents=True)
    (session_dir / "default.session.json").write_text(
        json.dumps({"marker": "foreign", "pid": 999999}, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="не принадлежит"):
        stop_runtime_session(project, profile_id="default")



def test_session_config_adds_sudo_owner_uid_for_root_run(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    _install_fake_nfqws2(project)
    prepared = prepare_runtime_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, prepared.plan_id)

    monkeypatch.setattr(runtime_session_module, "_running_as_root", lambda: True)
    monkeypatch.setenv("SUDO_UID", "1000")
    monkeypatch.setenv("SUDO_GID", "1000")

    config = build_runtime_session_config(project, profile_id="default")

    assert "--uid=1000:1000" in config.runtime_args
    assert config.drop_identity is not None
    assert config.drop_identity.source == "sudo-owner"



def test_session_status_marks_copied_state_from_other_workspace_as_stale(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    _install_fake_nfqws2(project)
    prepare_runtime_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, "runtime-default-manual-local-start-plan")
    result = start_runtime_session(project, profile_id="default")
    try:
        copied = tmp_path / "copied"
        shutil.copytree(project, copied, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        status = runtime_session_status(copied, profile_id="default")
        assert status.state == "stale"
        assert "другому workspace" in status.message
    finally:
        stop_runtime_session(project, profile_id="default")

def test_session_uses_public_runtime_inputs_after_dropcaps(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    public_base = tmp_path / "public-runtime"
    monkeypatch.setenv("ZAP2_PUBLIC_RUNTIME_INPUTS_DIR", str(public_base))
    _install_fake_nfqws2(project)
    source = project / "profiles" / "hostlists" / "default.hosts"
    source.write_text("example.org\n", encoding="utf-8")
    source.chmod(0o600)
    lua_source = project / "core" / "zapret2" / "lua" / "zapret-lib.lua"
    lua_source.chmod(0o600)
    prepared = prepare_runtime_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, prepared.plan_id)

    config = build_runtime_session_config(project, profile_id="default")

    assert config.public_session_inputs_dir is not None
    assert config.hostlist_input_paths
    copied = config.hostlist_input_paths[0]
    assert copied.exists()
    assert copied.read_text(encoding="utf-8") == "example.org\n"
    assert copied.is_absolute()
    assert copied.is_relative_to(public_base / "zap2-runtime-inputs")
    assert copied.stat().st_mode & 0o077 == 0o044
    assert copied.parent.stat().st_mode & 0o077 == 0o055
    hostlist_args = [arg for arg in config.runtime_args if arg.startswith("--hostlist=")]
    assert hostlist_args == [f"--hostlist={copied.resolve()}"]

    assert config.lua_input_paths
    lua_args = [arg for arg in config.runtime_args if arg.startswith("--lua-init=@")]
    assert len(lua_args) == 2
    for lua_path in config.lua_input_paths:
        assert lua_path.exists()
        assert lua_path.is_absolute()
        assert lua_path.is_relative_to(public_base / "zap2-runtime-inputs")
        assert lua_path.stat().st_mode & 0o077 == 0o044
        assert lua_path.parent.stat().st_mode & 0o077 == 0o055
    assert any("zapret-lib.lua" in arg and str(public_base) in arg for arg in lua_args)
    assert any("zapret-antidpi.lua" in arg and str(public_base) in arg for arg in lua_args)

    args_text = "\n".join(config.runtime_args)
    assert str(source) not in args_text
    assert str(lua_source) not in args_text
    assert "/.zap2/runtime/session-inputs/" not in args_text

