#!/usr/bin/env python3
"""Проверка Stage 11 session runner без запуска реального процесса в devctl."""

from __future__ import annotations

import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))


def _copy_project() -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="zap2-stage11-check-"))
    target = temp_root / "project"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc")
    shutil.copytree(ROOT, target, ignore=ignore)
    return target


def _install_fake_nfqws2(project: Path) -> None:
    binary = project / "core" / "zapret2" / "nfq2" / "nfqws2"
    binary.write_text("#!/bin/sh\nsleep 60\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main() -> int:
    from zap2_gui.adapters.runtime_session import (
        SESSION_MARKER,
        build_runtime_session_config,
        runtime_session_status,
        stop_runtime_session,
    )
    from zap2_gui.adapters.runtime_state import confirm_runtime_plan, prepare_runtime_plan

    adapter_text = (ROOT / "gui/zap2_gui/adapters/runtime_session.py").read_text(encoding="utf-8")
    app_text = (ROOT / "gui/zap2_gui/app.py").read_text(encoding="utf-8")
    for symbol in ("start_runtime_session", "stop_runtime_session", "runtime_session_status", "build_runtime_session_config"):
        if symbol not in adapter_text:
            print(f"runtime_session adapter не содержит {symbol}")
            return 1
    for cli_flag in ("--runtime-session-start", "--runtime-session-status", "--runtime-session-stop"):
        if cli_flag not in app_text:
            print(f"app.py не содержит CLI flag {cli_flag}")
            return 1
    for fragment in ("systemctl", "iptables", "nft ", "install_easy", "curl", "wget"):
        if fragment in adapter_text:
            print(f"runtime_session adapter содержит запрещённый fragment: {fragment}")
            return 1
    if SESSION_MARKER != "zap2-runtime-session-v1":
        print("SESSION_MARKER должен быть стабильным owned marker")
        return 1

    project = _copy_project()
    try:
        status = runtime_session_status(project, profile_id="default")
        if status.state != "not-started":
            print("чистый workspace должен иметь статус not-started")
            return 1
        stopped = stop_runtime_session(project, profile_id="default")
        if stopped.state != "not-started" or "stops only recorded pid: yes" not in stopped.to_text():
            print("stop без session должен быть безопасным no-op")
            return 1

        _install_fake_nfqws2(project)
        prepared = prepare_runtime_plan(project, action="start", profile_id="default")
        confirmation = confirm_runtime_plan(project, prepared.plan_id)
        config = build_runtime_session_config(project, profile_id="default")
        if config.plan_hash != confirmation.plan_hash:
            print("session config должен быть связан с confirmed planHash")
            return 1
        if config.binary_path.name != "nfqws2" or not config.binary_path.exists():
            print("session config должен указывать на локальный nfqws2 binary")
            return 1
        text = config.to_text()
        hostlist_args = [arg for arg in config.runtime_args if arg.startswith("--hostlist=")]
        if not hostlist_args or not hostlist_args[0].startswith("--hostlist=.zap2/runtime/session-inputs/"):
            print("session config должен использовать runtime hostlist copy с относительным путём")
            return 1
        if not config.hostlist_input_paths or not config.hostlist_input_paths[0].exists():
            print("runtime hostlist copy должен существовать до запуска nfqws2")
            return 1
        if str(project / "profiles" / "hostlists" / "default.hosts") in "\n".join(config.runtime_args):
            print("session args не должны передавать исходный абсолютный hostlist path")
            return 1

        for fragment in (
            "requires confirmed start plan: yes",
            "mutates firewall/services: no",
            "service mode: no",
            "args file:",
            "session inputs dir:",
            "runtime hostlist inputs:",
            "pidfile:",
        ):
            if fragment not in text:
                print(f"session config не содержит обязательный фрагмент: {fragment}")
                return 1

        print("Runtime session inputs OK; config/guards проверены без запуска реального nfqws2")
        return 0
    finally:
        shutil.rmtree(project.parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
