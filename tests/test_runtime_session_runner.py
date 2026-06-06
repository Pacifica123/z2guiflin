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
