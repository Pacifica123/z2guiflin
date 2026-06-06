#!/usr/bin/env python3
"""Read-only проверка Stage 9 runtime plan generator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))


def _run(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "zap2_gui.app", *args],
        cwd=ROOT,
        env={"PYTHONPATH": "gui"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        print(result.stdout)
        raise SystemExit(result.returncode)
    return result.stdout


def main() -> int:
    from zap2_gui.adapters.runtime_plan_generator import create_runtime_plan
    from zap2_gui.models.runtime_plan import validate_runtime_plan_contract

    expected_sudo = {"start": True, "stop": True, "status": False}
    for action in ("start", "stop", "status"):
        plan = create_runtime_plan(ROOT, action=action, profile_id="default")
        if plan.profile.profile_id != "default" or plan.strategy.strategy_id != "manual-local":
            print("runtime plan должен строиться из default/manual-local")
            return 1
        if plan.binary_relative_path != "core/zapret2/nfq2/nfqws2":
            print(f"неожиданный binary path: {plan.binary_relative_path}")
            return 1
        if [hostlist.path for hostlist in plan.hostlists] != ["profiles/hostlists/default.hosts"]:
            print("runtime plan должен показывать default.hosts")
            return 1
        if not plan.required_artifacts or plan.required_artifacts[0].relative_path != "nfq2/nfqws2":
            print("runtime plan должен включать required artifact nfq2/nfqws2")
            return 1
        if plan.requires_sudo_for_apply is not expected_sudo[action]:
            print(f"неожиданный requires_sudo_for_apply для {action}")
            return 1
        issues = validate_runtime_plan_contract(plan.contract)
        errors = [issue.message for issue in issues if issue.severity == "error"]
        if errors:
            print("generated runtime plan не прошёл contract validation:")
            for error in errors:
                print(f" - {error}")
            return 1
        text = _run("--runtime-plan", action, "--profile", "default")
        required_fragments = [
            f"Runtime plan для action: {action}",
            "profile: default",
            "strategy: manual-local",
            "build target: nfqws2",
            "binary: core/zapret2/nfq2/nfqws2",
            "profiles/hostlists/default.hosts",
            "required artifacts:",
            "session files:",
            "log files:",
            "apply steps:",
            "rollback steps:",
            "requires owner confirmation: yes",
            "automatic checks may execute: no",
            "executes now: no",
            "bootstrap mixed in: no",
        ]
        missing = [fragment for fragment in required_fragments if fragment not in text]
        if missing:
            print(f"CLI output для {action} не содержит обязательные фрагменты:")
            for fragment in missing:
                print(f" - {fragment}")
            return 1

    invalid = subprocess.run(
        [sys.executable, "-m", "zap2_gui.app", "--runtime-plan", "start", "--profile", "missing"],
        cwd=ROOT,
        env={"PYTHONPATH": "gui"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if invalid.returncode == 0:
        print("unknown profile должен завершаться ошибкой")
        return 1

    print("Runtime plan generator Stage 9 OK; start/stop/status остаются plan-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
