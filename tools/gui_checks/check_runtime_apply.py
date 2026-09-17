#!/usr/bin/env python3
"""Проверка Stage 12 owner-confirmed apply/revert без root и без реального nft."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
    from zap2_gui.adapters.runtime_queue import resolve_nfqueue_num
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
        expected_qnum = resolve_nfqueue_num(project, "default")
        if f"nft add table inet {plan.nft_table}" not in command_text or f"queue num {expected_qnum} bypass" not in command_text:
            print(f"Apply plan должен явно использовать owner-scoped nft table и workspace NFQUEUE {expected_qnum}")
            return 1

        prepared = prepare_runtime_owner_rules_plan(project, action="apply", profile_id="default")
        confirm_runtime_plan(project, prepared.plan_id)
        calls: list[tuple[str, ...]] = []
        table_text = ""

        def fake_runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
            nonlocal table_text
            calls.append(argv)
            if argv[:4] == ("nft", "list", "table", "inet"):
                if not table_text:
                    return RuntimeCommandResult(argv=argv, returncode=1, stderr="Error: No such file or directory")
                return RuntimeCommandResult(argv=argv, returncode=0, stdout=table_text)
            if argv[:3] == ("nft", "--check", "-f"):
                return RuntimeCommandResult(argv=argv, returncode=0)
            if argv[:2] == ("nft", "-f"):
                table_text = Path(argv[2]).read_text(encoding="utf-8")
                return RuntimeCommandResult(argv=argv, returncode=0)
            return RuntimeCommandResult(argv=argv, returncode=0)

        result = execute_runtime_owner_rules(
            project,
            action="apply",
            profile_id="default",
            confirm_plan_id=prepared.plan_id,
            runner=fake_runner,
            allow_without_root=True,
        )
        if result.state != "applied" or len(calls) != 3:
            print("Fake apply runner должен исполнить три nft-команды и вернуть state=applied")
            return 1
        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        if state.get("marker") != "zap2-runtime-apply-v1" or state.get("nftTable") != plan.nft_table:
            print("Stage 12 apply state должен иметь marker и owner-scoped nft table")
            return 1

        revert_plan = create_runtime_apply_plan(project, action="revert", profile_id="default")
        if revert_plan.commands[0].argv != ("nft", "delete", "table", "inet", plan.nft_table):
            print("Stage 12 revert должен удалять только owner-scoped nft table")
            return 1
        print("Runtime apply/revert Stage 12 OK; проверки не вызывают sudo/root/nft")
        return 0
    finally:
        shutil.rmtree(project.parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
