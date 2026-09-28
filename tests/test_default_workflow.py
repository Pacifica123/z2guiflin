import json
import shutil
import stat
from pathlib import Path

import pytest

from zap2_gui.adapters.runtime_apply import RuntimeCommandResult
from zap2_gui.adapters.core_provenance import write_core_build_receipt
from zap2_gui.adapters.runtime_default import (
    DEFAULT_WORKFLOW_MARKER,
    execute_default_workflow,
    prepare_default_workflow_plan,
)
from zap2_gui.adapters.runtime_state import confirm_runtime_plan

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc")
    shutil.copytree(ROOT, target, ignore=ignore)
    return target


def _install_fake_nfqws2(project: Path, *, exits_immediately: bool = False) -> Path:
    binary = project / "core" / "zapret2" / "nfq2" / "nfqws2"
    body = """#!/usr/bin/env python3
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
"""
    if exits_immediately:
        body = """#!/bin/sh
echo fake immediate failure >&2
exit 1
"""
    binary.write_text(body, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    write_core_build_receipt(project, [binary], "nfqws2")
    return binary


class FakeNftRunner:
    def __init__(self, calls: list[tuple[str, ...]]):
        self.calls = calls
        self.exists = False
        self.table_text = ""

    def __call__(self, argv: tuple[str, ...]) -> RuntimeCommandResult:
        self.calls.append(argv)
        if argv[:4] == ("nft", "list", "table", "inet"):
            if not self.exists:
                return RuntimeCommandResult(argv=argv, returncode=1, stderr="Error: No such file or directory")
            return RuntimeCommandResult(argv=argv, returncode=0, stdout=self.table_text)
        if argv[:3] == ("nft", "--check", "-f"):
            return RuntimeCommandResult(argv=argv, returncode=0)
        if argv[:2] == ("nft", "-f"):
            text = Path(argv[2]).read_text(encoding="utf-8")
            if text.lstrip().startswith("delete table"):
                self.exists = False; self.table_text = ""
            else:
                self.exists = True; self.table_text = text
            return RuntimeCommandResult(argv=argv, returncode=0)
        return RuntimeCommandResult(argv=argv, returncode=0)


def _ok_runner(calls: list[tuple[str, ...]]):
    return FakeNftRunner(calls)


def test_default_start_plan_prepares_composite_and_child_plans(tmp_path):
    project = _copy_project(tmp_path)

    plan = prepare_default_workflow_plan(project, action="start", profile_id="default")

    assert plan.plan_id == "runtime-default-manual-local-default-start-workflow-plan"
    assert len(plan.plan_hash) == 64
    assert plan.requires_sudo is True
    assert [child.role for child in plan.child_plans] == ["runtime-start", "owner-rules-apply", "owner-rules-revert-on-start-failure"]
    assert plan.plan_path.exists()
    assert plan.rollback_path.exists()
    saved = json.loads(plan.plan_path.read_text(encoding="utf-8"))
    assert saved["marker"] == DEFAULT_WORKFLOW_MARKER
    assert saved["safety"]["usesServiceMode"] is False
    assert saved["safety"]["containsRemoteBootstrap"] is False
    assert saved["safety"]["containsUpstreamInstallerScript"] is False
    assert saved["safety"]["bootstrapMixedIn"] is False
    assert saved["execution"]["automaticChecksMayExecute"] is False
    assert "owner-rules-apply" in plan.to_text()


@pytest.mark.parametrize(
    ("action", "expected_id", "child_roles"),
    [
        ("start", "runtime-default-manual-local-default-start-workflow-plan", ["runtime-start", "owner-rules-apply", "owner-rules-revert-on-start-failure"]),
        ("stop", "runtime-default-manual-local-default-stop-workflow-plan", ["runtime-stop", "owner-rules-revert"]),
    ],
)
def test_default_workflow_plan_uses_runtime_confirmation_gate(tmp_path, action, expected_id, child_roles):
    project = _copy_project(tmp_path)

    plan = prepare_default_workflow_plan(project, action=action, profile_id="default")
    confirmation = confirm_runtime_plan(project, plan.plan_id)

    assert plan.plan_id == expected_id
    assert confirmation.plan_hash == plan.plan_hash
    saved = json.loads(plan.plan_path.read_text(encoding="utf-8"))
    assert saved["confirmed"] is True
    assert [child["role"] for child in saved["childPlans"]] == child_roles


def test_default_start_executes_apply_then_session_with_fake_runner(tmp_path):
    project = _copy_project(tmp_path)
    _install_fake_nfqws2(project)
    plan = prepare_default_workflow_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, plan.plan_id)
    calls: list[tuple[str, ...]] = []

    result = execute_default_workflow(
        project,
        action="start",
        profile_id="default",
        confirm_plan_id=plan.plan_id,
        apply_runner=_ok_runner(calls),
        allow_without_root=True,
    )
    try:
        assert result.state == "started"
        assert result.session_result is not None
        assert result.session_result.state == "running"
        assert result.apply_result is not None
        assert result.apply_result.state == "applied"
        assert len(calls) == 4
        state = json.loads(result.workflow_state_path.read_text(encoding="utf-8"))
        assert state["marker"] == DEFAULT_WORKFLOW_MARKER
        assert state["state"] == "started"
        assert state["usesServiceMode"] is False
        assert state["containsRemoteBootstrap"] is False
        assert state["containsUpstreamInstallerScript"] is False
        assert state["runId"].startswith("run-")
        owner_state = json.loads((project / ".zap2/runtime/sessions/default.owner-rules.json").read_text(encoding="utf-8"))
        session_state = json.loads((project / ".zap2/runtime/sessions/default.session.json").read_text(encoding="utf-8"))
        assert owner_state["runId"] == state["runId"]
        assert session_state["runId"] == state["runId"]
        log_text = result.log_path.read_text(encoding="utf-8")
        assert "default-start-started" in log_text
        assert "owner-rules-apply-applied" in log_text
        assert "session-started" in log_text
    finally:
        # Страховочный stop/revert для fake process.
        stop_plan = prepare_default_workflow_plan(project, action="stop", profile_id="default")
        confirm_runtime_plan(project, stop_plan.plan_id)
        execute_default_workflow(
            project,
            action="stop",
            profile_id="default",
            confirm_plan_id=stop_plan.plan_id,
            apply_runner=_ok_runner([]),
            allow_without_root=True,
        )



def test_default_start_rolls_back_owner_rules_when_session_fails(tmp_path):
    project = _copy_project(tmp_path)
    _install_fake_nfqws2(project, exits_immediately=True)
    plan = prepare_default_workflow_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, plan.plan_id)
    calls: list[tuple[str, ...]] = []

    result = execute_default_workflow(
        project,
        action="start",
        profile_id="default",
        confirm_plan_id=plan.plan_id,
        apply_runner=_ok_runner(calls),
        allow_without_root=True,
    )

    assert result.state == "failed-rolled-back"
    assert result.rollback_result is not None
    assert result.rollback_result.state == "reverted"
    assert len(calls) == 7
    assert calls[-1][0:2] == ("nft", "-f")
    state = json.loads(result.workflow_state_path.read_text(encoding="utf-8"))
    assert state["state"] == "failed-rolled-back"
    assert state["ownerRulesRollbackResult"]["state"] == "reverted"
    assert "session start failed" in state["sessionResult"]["message"] if state.get("sessionResult") else True


def test_default_stop_stops_session_and_reverts_owner_rules(tmp_path):
    project = _copy_project(tmp_path)
    _install_fake_nfqws2(project)
    start_plan = prepare_default_workflow_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, start_plan.plan_id)
    nft_calls: list[tuple[str, ...]] = []
    nft_runner = _ok_runner(nft_calls)
    execute_default_workflow(
        project,
        action="start",
        profile_id="default",
        confirm_plan_id=start_plan.plan_id,
        apply_runner=nft_runner,
        allow_without_root=True,
    )

    stop_plan = prepare_default_workflow_plan(project, action="stop", profile_id="default")
    confirm_runtime_plan(project, stop_plan.plan_id)
    calls: list[tuple[str, ...]] = []
    result = execute_default_workflow(
        project,
        action="stop",
        profile_id="default",
        confirm_plan_id=stop_plan.plan_id,
        apply_runner=nft_runner,
        allow_without_root=True,
    )

    assert result.state == "stopped"
    assert result.session_result is not None
    assert result.session_result.state == "stopped"
    assert result.apply_result is not None
    assert result.apply_result.state == "reverted"
    assert nft_calls[-3][0:4] == ("nft", "list", "table", "inet")
    assert nft_calls[-2][0:3] == ("nft", "--check", "-f")
    assert nft_calls[-1][0:2] == ("nft", "-f")
    state = json.loads(result.workflow_state_path.read_text(encoding="utf-8"))
    assert state["state"] == "stopped"
    assert "default-stop-stopped" in result.log_path.read_text(encoding="utf-8")


def test_default_start_requires_confirmed_composite_plan(tmp_path):
    project = _copy_project(tmp_path)
    _install_fake_nfqws2(project)
    plan = prepare_default_workflow_plan(project, action="start", profile_id="default")

    with pytest.raises(ValueError, match="Confirmation"):
        execute_default_workflow(
            project,
            action="start",
            profile_id="default",
            confirm_plan_id=plan.plan_id,
            apply_runner=_ok_runner([]),
            allow_without_root=True,
        )


def test_default_start_rejects_missing_binary_before_apply(tmp_path):
    project = _copy_project(tmp_path)
    plan = prepare_default_workflow_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, plan.plan_id)
    calls: list[tuple[str, ...]] = []

    with pytest.raises(ValueError, match="nfqws2 binary"):
        execute_default_workflow(
            project,
            action="start",
            profile_id="default",
            confirm_plan_id=plan.plan_id,
            apply_runner=_ok_runner(calls),
            allow_without_root=True,
        )
    assert calls == []


def test_p02_failure_after_session_start_compensates_session_and_owner_rules(tmp_path):
    project = _copy_project(tmp_path)
    _install_fake_nfqws2(project)
    plan = prepare_default_workflow_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, plan.plan_id)
    calls: list[tuple[str, ...]] = []
    runner = _ok_runner(calls)

    def failpoint(name: str) -> None:
        if name == "after-session-start":
            raise RuntimeError("P02_FAILPOINT:after-session-start")

    result = execute_default_workflow(
        project,
        action="start",
        profile_id="default",
        confirm_plan_id=plan.plan_id,
        apply_runner=runner,
        allow_without_root=True,
        failure_injector=failpoint,
    )

    assert result.state == "failed-rolled-back"
    assert result.rollback_result is not None and result.rollback_result.state == "reverted"
    assert result.session_status is not None and result.session_status.state == "stopped"
    assert "P02_FAILPOINT:after-session-start" in result.message
    assert "session compensation: stopped" in result.message
    state = json.loads(result.workflow_state_path.read_text(encoding="utf-8"))
    assert state["runId"].startswith("run-")
