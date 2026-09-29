#!/usr/bin/env python3
"""Explicit owner-host recovery for one previous Zap2 workspace runtime.

The script deliberately imports code from the *current* accepted project but
operates on runtime state belonging to the explicitly supplied old workspace.
It never scans arbitrary workspaces and never signals a PID without the normal
runtime_session identity checks.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

CURRENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CURRENT_ROOT / "gui"))

from zap2_gui.adapters.privileged_executor import execute_bounded_default_workflow, privileged_executor_status
from zap2_gui.adapters.runtime_default import default_workflow_status, prepare_default_workflow_plan
from zap2_gui.adapters.runtime_state import confirm_runtime_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recover one explicit previous Zap2 workspace runtime")
    parser.add_argument("--root", required=True, help="absolute path to the previous UTS/project root")
    parser.add_argument("--profile", default="default")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if os.geteuid() == 0:
        raise SystemExit("recovery must run as the owner user, not through sudo/root")
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir() or not (root / "run.sh").is_file() or not (root / "gui").is_dir():
        raise SystemExit(f"target is not a Zap2 project root: {root}")

    print("Explicit previous-workspace runtime recovery")
    print(f"target root: {root}")
    print(f"profile: {args.profile}")

    helper = privileged_executor_status(root)
    print(helper.to_text())
    if not helper.ready:
        raise SystemExit("target workspace helper provenance is not ready; recovery refused")

    before = default_workflow_status(root, args.profile)
    print("\nBefore recovery:")
    print(before.to_text())

    plan = prepare_default_workflow_plan(root, action="stop", profile_id=args.profile)
    print("\nPrepared recovery stop plan:")
    print(plan.to_text())
    confirmation = confirm_runtime_plan(root, plan_id=plan.plan_id)
    print("\nRecovery confirmation:")
    print(confirmation.to_text())

    result = execute_bounded_default_workflow(
        root,
        action="stop",
        profile_id=args.profile,
        confirm_plan_id=plan.plan_id,
    )
    print("\nRecovery execution:")
    print(result.to_text())

    after = default_workflow_status(root, args.profile)
    print("\nAfter recovery:")
    print(after.to_text())
    if result.state != "stopped" or after.workflow_state != "stopped":
        raise SystemExit("previous workspace recovery did not reach stopped state")
    print("PREVIOUS WORKSPACE RECOVERY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
