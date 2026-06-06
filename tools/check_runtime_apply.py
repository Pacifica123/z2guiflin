#!/usr/bin/env python3
"""Проверка Stage 12 owner-confirmed apply/revert без root и без реального nft."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))


def _copy_project() -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="zap2-stage12-check-"))
    target = temp_root / "project"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc")
    shutil.copytree(ROOT, target, ignore=ignore)
    return target


def main() -> int:
    from zap2_gui.adapters.runtime_apply import (
        RuntimeCommandResult,
        create_runtime_apply_plan,
        execute_runtime_owner_rules,
        prepare_runtime_owner_rules_plan,
    )
    from zap2_gui.adapters.runtime_state import confirm_runtime_plan

    project = _copy_project()
    try:
        plan = create_runtime_apply_plan(project, action="apply", profile_id="default")
        payload = plan.to_payload()
        if payload["safety"].get("containsRemoteBootstrap") is not False:
            print("Stage 12 apply plan не должен содержать remote bootstrap")
            return 1
        if payload["safety"].get("containsUpstreamInstallerScript") is not False:
            print("Stage 12 apply plan не должен содержать upstream installer scripts")
            return 1
        if payload["execution"].get("automaticChecksMayExecute") is not False:
            print("Stage 12 apply plan не должен исполняться автоматическими проверками")
            return 1
        command_text = "\n".join(" ".join(command.argv) for command in plan.commands)
        forbidden = ["curl", "wget", "install_easy", "systemctl", "service "]
        bad = [word for word in forbidden if word in command_text]
        if bad:
            print("Stage 12 apply plan содержит запрещённые команды:", ", ".join(bad))
            return 1
        if "nft add table inet zap2_default" not in command_text or "queue num 200 bypass" not in command_text:
            print("Stage 12 apply plan должен явно использовать отдельную nft table и NFQUEUE 200")
            return 1

        prepared = prepare_runtime_owner_rules_plan(project, action="apply", profile_id="default")
        confirm_runtime_plan(project, prepared.plan_id)
        calls: list[tuple[str, ...]] = []

        def fake_runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
            calls.append(argv)
            return RuntimeCommandResult(argv=argv, returncode=0)

        result = execute_runtime_owner_rules(
            project,
            action="apply",
            profile_id="default",
            confirm_plan_id=prepared.plan_id,
            runner=fake_runner,
            allow_without_root=True,
        )
        if result.state != "applied" or len(calls) != 4:
            print("Fake apply runner должен исполнить четыре nft-команды и вернуть state=applied")
            return 1
        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        if state.get("marker") != "zap2-runtime-apply-v1" or state.get("nftTable") != "zap2_default":
            print("Stage 12 apply state должен иметь marker и owned nft table")
            return 1

        revert_plan = create_runtime_apply_plan(project, action="revert", profile_id="default")
        if revert_plan.commands[0].argv != ("nft", "delete", "table", "inet", "zap2_default"):
            print("Stage 12 revert должен удалять только owned nft table")
            return 1
        print("Runtime apply/revert Stage 12 OK; проверки не вызывают sudo/root/nft")
        return 0
    finally:
        shutil.rmtree(project.parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
