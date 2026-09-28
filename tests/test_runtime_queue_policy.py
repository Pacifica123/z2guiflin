from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from zap2_gui.adapters.core_provenance import write_core_build_receipt
from zap2_gui.adapters.runtime_apply import create_runtime_apply_plan
from zap2_gui.adapters.runtime_queue import find_nfqueue_processes, resolve_nfqueue_num, resolve_runtime_queue
from zap2_gui.adapters.runtime_state import confirm_runtime_plan
from zap2_gui.adapters.runtime_session import build_runtime_session_config
from zap2_gui.adapters.runtime_state import prepare_runtime_plan

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc")
    shutil.copytree(ROOT, target, ignore=ignore)
    return target


def test_workspace_queue_is_stable_and_not_fixed_global_200(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    q1 = resolve_runtime_queue(project, "default")
    q2 = resolve_runtime_queue(project, "default")
    assert q1.qnum == q2.qnum
    assert q1.source == "owner-workspace-hash"
    assert 200 <= q1.qnum <= 599


def test_nfqueue_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZAP2_NFQUEUE_NUM", "321")
    assert resolve_nfqueue_num(ROOT, "default") == 321


def test_apply_and_session_use_same_workspace_queue(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    qnum = resolve_nfqueue_num(project, "default")
    apply_plan = create_runtime_apply_plan(project, action="apply", profile_id="default")
    assert apply_plan.nfqueue_num == qnum
    all_rules = "\n".join(" ".join(cmd.argv) for cmd in apply_plan.commands)
    assert f"queue num {qnum} bypass" in all_rules
    assert "udp dport" not in all_rules
    assert f"meta skuid {apply_plan.owner_uid}" in all_rules
    assert "meta mark & 0x40000000 == 0" in all_rules

    binary = project / "core" / "zapret2" / "nfq2" / "nfqws2"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    write_core_build_receipt(project, [binary], "nfqws2")
    prepared = prepare_runtime_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, prepared.plan_id)
    config = build_runtime_session_config(project, profile_id="default")
    assert config.nfqueue_num == qnum
    assert f"--qnum={qnum}" in config.runtime_args
    assert "--fwmark=0x40000000" in config.runtime_args


def test_find_nfqueue_processes_is_best_effort_read_only() -> None:
    # The result depends on the host, but the function must be safe and typed.
    matches = find_nfqueue_processes(200)
    assert isinstance(matches, tuple)
