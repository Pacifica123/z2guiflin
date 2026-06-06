#!/usr/bin/env python3
"""Read-only проверка workspace-профилей и стратегий Stage 7."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))

from zap2_gui.adapters.workspace_profiles import (  # noqa: E402
    load_workspace_catalog,
    validate_workspace_catalog,
    workspace_profiles_to_text,
    workspace_strategies_to_text,
)


def main() -> int:
    issues = validate_workspace_catalog(ROOT)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        print("Ошибки workspace-профилей/стратегий:")
        for issue in errors:
            print(f" - {issue.message}")
        return 1

    catalog = load_workspace_catalog(ROOT)
    if catalog.default_profile_id != "default":
        print("Default workspace profile должен быть default")
        return 1
    if catalog.default_strategy_id != "manual-local":
        print("Default strategy должна быть manual-local")
        return 1
    if [profile.profile_id for profile in catalog.profiles] != ["default"]:
        print("Stage 7 должен иметь ровно один активный профиль default")
        return 1
    if {strategy.strategy_id for strategy in catalog.strategies} != {"manual-local", "read-only-diagnostics"}:
        print("Stage 7 strategy catalog должен содержать manual-local и read-only-diagnostics")
        return 1

    profiles_text = workspace_profiles_to_text(ROOT)
    strategies_text = workspace_strategies_to_text(ROOT)
    if "default" not in profiles_text or "manual-local" not in strategies_text:
        print("CLI formatter не показывает default/manual-local")
        return 1

    print("Workspace profiles/strategies OK: read-only, plan-only, linked to build targets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
