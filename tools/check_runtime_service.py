#!/usr/bin/env python3
"""Проверка Stage 13 service plans без root и без реального systemctl."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))


def _copy_project() -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="zap2-stage13-check-"))
    target = temp_root / "project"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc")
    shutil.copytree(ROOT, target, ignore=ignore)
    return target


def main() -> int:
    from zap2_gui.adapters.runtime_service import (
        ServiceCommandResult,
        create_service_plan,
        execute_service_plan,
        prepare_service_plan,
    )
    from zap2_gui.adapters.runtime_state import confirm_runtime_plan

    project = _copy_project()
    service_dir = project.parent / "fake-systemd"
    try:
        install_plan = create_service_plan(project, action="install", profile_id="default", service_dir=service_dir)
        payload = install_plan.to_payload()
        if payload["safety"].get("defaultWorkflow") is not False:
            print("Stage 13 service mode не должен становиться default workflow")
            return 1
        if payload["safety"].get("separateFromSessionMode") is not True:
            print("Stage 13 service mode должен быть отделён от session mode")
            return 1
        if payload["safety"].get("mutatesFirewallWhenExecutedByOwner") is not False:
            print("Stage 13 service plans не должны мутировать firewall")
            return 1
        if payload["execution"].get("automaticChecksMayExecute") is not False:
            print("Stage 13 service plans не должны исполняться автоматическими проверками")
            return 1
        command_text = "\n".join(" ".join(command.argv) for command in install_plan.commands)
        forbidden = ["curl", "wget", "install_easy", "iptables", "nft add"]
        bad = [word for word in forbidden if word in command_text]
        if bad:
            print("Stage 13 service plan содержит запрещённые фрагменты:", ", ".join(bad))
            return 1
        if "systemctl daemon-reload" not in command_text:
            print("Install plan должен содержать systemctl daemon-reload как явную service-команду")
            return 1
        if "ExecStart=" not in install_plan.unit_content or "@" not in install_plan.unit_content:
            print("Systemd unit должен описывать ExecStart nfqws2 @args-file")
            return 1

        prepared = prepare_service_plan(project, action="install", profile_id="default", service_dir=service_dir)
        confirm_runtime_plan(project, prepared.plan_id)
        calls: list[tuple[str, ...]] = []

        def fake_runner(argv: tuple[str, ...]) -> ServiceCommandResult:
            calls.append(argv)
            return ServiceCommandResult(argv=argv, returncode=0)

        result = execute_service_plan(
            project,
            action="install",
            profile_id="default",
            confirm_plan_id=prepared.plan_id,
            service_dir=service_dir,
            runner=fake_runner,
            allow_without_root=True,
        )
        if result.state != "installed" or calls != [("systemctl", "daemon-reload")]:
            print("Fake install должен записать unit/args и вызвать только daemon-reload")
            return 1
        if not result.unit_path.exists():
            print("Fake install должен создать unit-файл во временной service-dir")
            return 1

        remove = prepare_service_plan(project, action="remove", profile_id="default", service_dir=service_dir)
        confirm_runtime_plan(project, remove.plan_id)
        remove_result = execute_service_plan(
            project,
            action="remove",
            profile_id="default",
            confirm_plan_id=remove.plan_id,
            service_dir=service_dir,
            runner=fake_runner,
            allow_without_root=True,
        )
        if remove_result.state != "removed" or result.unit_path.exists():
            print("Fake remove должен удалить только owned unit-файл")
            return 1
        state = json.loads(remove_result.state_path.read_text(encoding="utf-8"))
        if state.get("marker") != "zap2-runtime-service-v1" or state.get("managesServiceNow") is not True:
            print("Stage 13 service state должен иметь marker и managesServiceNow=true")
            return 1
        print("Runtime service plans Stage 13 OK; проверки не вызывают sudo/root/systemctl")
        return 0
    finally:
        shutil.rmtree(project.parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
