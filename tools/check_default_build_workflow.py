#!/usr/bin/env python3
"""Проверка v0.3-beta Stage 1 default build workflow без запуска настоящего make."""

from __future__ import annotations

import json
import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))


def _copy_project() -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="zap2-beta1-build-check-"))
    target = temp_root / "project"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc")
    shutil.copytree(ROOT, target, ignore=ignore)
    return target


def main() -> int:
    from zap2_gui.adapters.runtime_default_build import (
        DEFAULT_BUILD_MARKER,
        DefaultBuildCommandResult,
        execute_default_build,
        prepare_default_build_plan,
    )
    from zap2_gui.adapters.runtime_state import confirm_runtime_plan

    project = _copy_project()
    try:
        plan = prepare_default_build_plan(project, profile_id="default")
        if plan.plan_id != "runtime-default-manual-local-default-build-workflow-plan":
            print("Неожиданный default build plan id")
            return 1
        saved = json.loads(plan.plan_path.read_text(encoding="utf-8"))
        if saved.get("marker") != DEFAULT_BUILD_MARKER:
            print("Default build plan должен иметь beta marker")
            return 1
        safety = saved.get("safety", {})
        if safety.get("requiresSudoWhenExecutedByOwner") is not False:
            print("Default build не должен требовать sudo")
            return 1
        if safety.get("mutatesFirewallWhenExecutedByOwner") is not False:
            print("Default build не должен менять firewall")
            return 1
        if safety.get("containsRemoteBootstrap") is not False or safety.get("containsUpstreamInstallerScript") is not False:
            print("Default build не должен содержать bootstrap/upstream installer")
            return 1
        if safety.get("automaticChecksMayExecute") is not False:
            print("Default build не должен исполняться автоматическими проверками")
            return 1

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
        )
        if result.state != "built":
            print("Fake default build должен завершиться built")
            return 1
        if calls != [(project / "core" / "zapret2" / "nfq2", ("make", "nfqws2"))]:
            print("Default build должен запускать только make nfqws2 в nfq2")
            return 1
        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        if state.get("requiresSudo") is not False or state.get("mutatesFirewallOrServicesNow") is not False:
            print("Default build state должен фиксировать отсутствие sudo/firewall mutation")
            return 1
        print("Default build workflow v0.3-beta Stage 1 OK; fake checks не запускают настоящий make")
        return 0
    finally:
        shutil.rmtree(project.parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
