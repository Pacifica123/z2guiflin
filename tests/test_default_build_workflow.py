from __future__ import annotations

import json
import shutil
import stat
import sys
from pathlib import Path

from zap2_gui.adapters.build_dependencies import make_success_report, run_build_dependency_preflight
from zap2_gui.adapters.runtime_default_build import (
    DEFAULT_BUILD_MARKER,
    DefaultBuildCommandResult,
    execute_default_build,
    prepare_default_build_plan,
)
from zap2_gui.adapters.runtime_state import confirm_runtime_plan


def _copy_project(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    target = tmp_path / "project"
    shutil.copytree(
        root,
        target,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc"),
    )
    return target


def test_default_build_plan_is_hash_confirmed_and_safe(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    plan = prepare_default_build_plan(project, profile_id="default")
    saved = json.loads(plan.plan_path.read_text(encoding="utf-8"))

    assert plan.plan_id == "runtime-default-manual-local-default-build-workflow-plan"
    assert saved["marker"] == DEFAULT_BUILD_MARKER
    assert saved["buildTarget"] == "nfqws2"
    assert saved["safety"]["requiresSudoWhenExecutedByOwner"] is False
    assert saved["safety"]["mutatesFirewallWhenExecutedByOwner"] is False
    assert saved["safety"]["containsRemoteBootstrap"] is False
    assert saved["safety"]["containsUpstreamInstallerScript"] is False
    assert saved["safety"]["automaticChecksMayExecute"] is False
    assert saved["buildDependencyPreflight"]["runsMakeNow"] is False
    assert "libnetfilter_queue" in str(saved["buildDependencyPreflight"])
    assert any(item["relativePath"] == "nfq2/nfqws2" for item in saved["expectedArtifacts"])

    confirmation = confirm_runtime_plan(project, plan.plan_id)
    assert confirmation.plan_hash == plan.plan_hash


def test_default_build_execution_uses_fake_runner_and_writes_artifact_state(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    plan = prepare_default_build_plan(project, profile_id="default")
    confirm_runtime_plan(project, plan.plan_id)
    calls: list[tuple[Path, tuple[str, ...]]] = []

    def fake_runner(cwd: Path, argv: tuple[str, ...]) -> DefaultBuildCommandResult:
        calls.append((cwd, argv))
        binary = project / "core" / "zapret2" / "nfq2" / "nfqws2"
        binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return DefaultBuildCommandResult(cwd=cwd, argv=argv, returncode=0, stdout="fake build ok")

    result = execute_default_build(
        project,
        profile_id="default",
        confirm_plan_id=plan.plan_id,
        runner=fake_runner,
        allow_as_root=True,
        dependency_report=make_success_report(),
    )

    assert result.state == "built"
    assert calls == [(project, (sys.executable, str(project / "tools" / "core_generation_build.py"), "nfqws2"))]
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["marker"] == DEFAULT_BUILD_MARKER
    assert state["requiresSudo"] is False
    assert state["mutatesFirewallOrServicesNow"] is False
    assert state["artifacts"][0]["exists"] is True
    assert state["artifacts"][0]["executable"] is True


def test_default_build_refuses_missing_confirmation(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    plan = prepare_default_build_plan(project, profile_id="default")
    try:
        execute_default_build(project, profile_id="default", confirm_plan_id=plan.plan_id, runner=lambda cwd, argv: DefaultBuildCommandResult(cwd, argv, 0), allow_as_root=True, dependency_report=make_success_report())
    except ValueError as exc:
        assert "Confirmation не найден" in str(exc)
    else:
        raise AssertionError("default build должен требовать owner confirmation")


def test_default_build_blocks_before_make_when_dependencies_are_missing(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    plan = prepare_default_build_plan(project, profile_id="default")
    confirm_runtime_plan(project, plan.plan_id)
    calls: list[tuple[Path, tuple[str, ...]]] = []

    def fake_runner(cwd: Path, argv: tuple[str, ...]) -> DefaultBuildCommandResult:
        calls.append((cwd, argv))
        return DefaultBuildCommandResult(cwd=cwd, argv=argv, returncode=0)

    missing_report = run_build_dependency_preflight(
        "nfqws2",
        include_paths=(tmp_path / "empty-include",),
        command_resolver=lambda command: f"/fake/{command}",
    )
    result = execute_default_build(
        project,
        profile_id="default",
        confirm_plan_id=plan.plan_id,
        runner=fake_runner,
        allow_as_root=True,
        dependency_report=missing_report,
    )

    assert result.state == "blocked"
    assert calls == []
    assert "dependency preflight" in result.to_text()
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["dependencyPreflight"]["ok"] is False
    assert state["commands"] == []
