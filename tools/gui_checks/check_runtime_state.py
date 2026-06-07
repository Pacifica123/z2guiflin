#!/usr/bin/env python3
"""Проверка Stage 10 runtime state/log/confirmation gate без исполнения планов."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gui"))


def _copy_project() -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix="zap2-stage10-check-"))
    target = temp_root / "project"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc")
    shutil.copytree(ROOT, target, ignore=ignore)
    return target


def main() -> int:
    from zap2_gui.adapters.runtime_state import (
        confirm_runtime_plan,
        prepare_runtime_plan,
        runtime_log_to_text,
        runtime_store_paths,
    )

    project = _copy_project()
    try:
        prepared = prepare_runtime_plan(project, action="start", profile_id="default")
        prepare_text = prepared.to_text()
        required_prepare = [
            "Prepared runtime plan: runtime-default-manual-local-start-plan",
            "plan hash:",
            "confirmation required: yes",
            "executes now: no",
            "mutates services/firewall now: no",
        ]
        missing = [fragment for fragment in required_prepare if fragment not in prepare_text]
        if missing:
            print("prepare_runtime_plan не содержит обязательные фрагменты:")
            for fragment in missing:
                print(f" - {fragment}")
            return 1

        paths = runtime_store_paths(project)
        expected_paths = [
            paths.plans_dir / "runtime-default-manual-local-start-plan.json",
            paths.rollback_dir / "runtime-default-manual-local-start-plan.md",
            paths.logs_dir / "default.runtime.jsonl",
        ]
        missing_paths = [path for path in expected_paths if not path.exists()]
        if missing_paths:
            print("Stage 10 не создал expected workspace state files:")
            for path in missing_paths:
                print(f" - {path}")
            return 1

        saved = json.loads(expected_paths[0].read_text(encoding="utf-8"))
        if saved.get("confirmed") is not False or not saved.get("planHash"):
            print("Prepared plan должен иметь planHash и confirmed=false")
            return 1
        if saved.get("execution", {}).get("executesNow") is not False:
            print("Prepared plan не должен исполняться")
            return 1

        confirmation = confirm_runtime_plan(project, "runtime-default-manual-local-start-plan")
        confirm_text = confirmation.to_text()
        if "Runtime confirmation:" not in confirm_text or "allows automatic reuse: no" not in confirm_text:
            print("confirm_runtime_plan не показывает одноразовое confirmation")
            return 1
        confirmation_path = paths.confirmations_dir / "runtime-default-manual-local-start-plan.confirmation.json"
        confirmation_data = json.loads(confirmation_path.read_text(encoding="utf-8"))
        if confirmation_data.get("planHash") != saved.get("planHash"):
            print("Confirmation должен быть связан с сохранённым planHash")
            return 1
        if confirmation_data.get("allowsAutomaticReuse") is not False or confirmation_data.get("expiresWhenPlanChanges") is not True:
            print("Confirmation должен быть одноразовым и истекать при изменении plan")
            return 1

        log_text = runtime_log_to_text(project, profile_id="default")
        if "planned" not in log_text or "confirmed" not in log_text or "executes now: no" not in log_text:
            print("runtime_log_to_text должен показывать planned/confirmed events без исполнения")
            return 1

        print("Runtime state Stage 10 OK; .zap2/runtime создаётся только в workspace-копии и не исполняет plans")
        return 0
    finally:
        shutil.rmtree(project.parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
