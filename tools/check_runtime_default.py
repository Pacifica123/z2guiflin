#!/usr/bin/env python3
"""Проверка Stage 14 default start/stop workflow без root, nft и настоящего ядра."""

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
    temp_root = Path(tempfile.mkdtemp(prefix="zap2-stage14-check-"))
    target = temp_root / "project"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc")
    shutil.copytree(ROOT, target, ignore=ignore)
    return target


def _install_fake_nfqws2(project: Path) -> None:
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


def main() -> int:
    from zap2_gui.adapters.runtime_apply import RuntimeCommandResult
    from zap2_gui.adapters.runtime_default import (
        DEFAULT_WORKFLOW_MARKER,
        execute_default_workflow,
        prepare_default_workflow_plan,
    )
    from zap2_gui.adapters.runtime_state import confirm_runtime_plan

    project = _copy_project()
    try:
        _install_fake_nfqws2(project)
        start_plan = prepare_default_workflow_plan(project, action="start", profile_id="default")
        if start_plan.plan_id != "runtime-default-manual-local-default-start-workflow-plan":
            print("Неожиданный plan id для default-start")
            return 1
        start_saved = json.loads(start_plan.plan_path.read_text(encoding="utf-8"))
        if start_saved.get("marker") != DEFAULT_WORKFLOW_MARKER:
            print("Default start plan должен иметь Stage 14 marker")
            return 1
        if start_saved["safety"].get("usesServiceMode") is not False:
            print("Default workflow не должен использовать service mode")
            return 1
        if start_saved["safety"].get("containsRemoteBootstrap") is not False:
            print("Default workflow не должен содержать remote bootstrap")
            return 1
        if start_saved["safety"].get("containsUpstreamInstallerScript") is not False:
            print("Default workflow не должен содержать upstream installer scripts")
            return 1
        if start_saved["safety"].get("automaticChecksMayExecute") is not False:
            print("Default workflow не должен исполняться автоматическими проверками")
            return 1
        if [child["role"] for child in start_saved["childPlans"]] != ["runtime-start", "owner-rules-apply", "owner-rules-revert-on-start-failure"]:
            print("Default start должен связывать runtime-start, owner-rules-apply и аварийный revert")
            return 1
        if start_saved.get("rollbackOnStartFailure") is not True:
            print("Default start plan должен явно включать rollbackOnStartFailure")
            return 1

        calls: list[tuple[str, ...]] = []

        def fake_runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
            calls.append(argv)
            return RuntimeCommandResult(argv=argv, returncode=0)

        confirm_runtime_plan(project, start_plan.plan_id)
        started = execute_default_workflow(
            project,
            action="start",
            profile_id="default",
            confirm_plan_id=start_plan.plan_id,
            apply_runner=fake_runner,
            allow_without_root=True,
        )
        if started.state != "started" or started.session_result is None or started.session_result.state != "running":
            print("Fake default-start должен применить owner-rules и запустить session")
            return 1
        if len(calls) != 4:
            print("Fake default-start должен вызвать четыре nft-команды apply")
            return 1

        stop_plan = prepare_default_workflow_plan(project, action="stop", profile_id="default")
        stop_saved = json.loads(stop_plan.plan_path.read_text(encoding="utf-8"))
        if [child["role"] for child in stop_saved["childPlans"]] != ["runtime-stop", "owner-rules-revert"]:
            print("Default stop должен связывать runtime-stop и owner-rules-revert")
            return 1
        confirm_runtime_plan(project, stop_plan.plan_id)
        stop_calls: list[tuple[str, ...]] = []

        def fake_revert(argv: tuple[str, ...]) -> RuntimeCommandResult:
            stop_calls.append(argv)
            return RuntimeCommandResult(argv=argv, returncode=0)

        stopped = execute_default_workflow(
            project,
            action="stop",
            profile_id="default",
            confirm_plan_id=stop_plan.plan_id,
            apply_runner=fake_revert,
            allow_without_root=True,
        )
        if stopped.state != "stopped" or stopped.apply_result is None or stopped.apply_result.state != "reverted":
            print("Fake default-stop должен остановить session и выполнить revert")
            return 1
        if stop_calls != [("nft", "delete", "table", "inet", "zap2_default")]:
            print("Default stop должен удалять только owned nft table")
            return 1
        workflow_state = json.loads(stopped.workflow_state_path.read_text(encoding="utf-8"))
        if workflow_state.get("containsUpstreamInstallerScript") is not False or workflow_state.get("usesServiceMode") is not False:
            print("Workflow state должен фиксировать отсутствие bootstrap/service mode")
            return 1
        print("Default workflow v0.3-beta Stage 3 OK; fake checks не вызывают sudo/root/nft/systemctl")
        return 0
    finally:
        shutil.rmtree(project.parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
