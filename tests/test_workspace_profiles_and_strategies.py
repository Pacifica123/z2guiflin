from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from zap2_gui.adapters.gui_state import load_gui_shell_state
from zap2_gui.adapters.workspace_profiles import (
    load_strategy_catalog,
    load_workspace_catalog,
    load_workspace_profile,
    validate_workspace_catalog,
    workspace_profile_to_text,
    workspace_profiles_to_text,
    workspace_strategies_to_text,
    workspace_strategy_to_text,
    select_workspace_strategy,
)
from zap2_gui.app import describe_project, main
from zap2_gui.adapters.runtime_plan_generator import create_runtime_plan
from zap2_gui.models.navigation import default_navigation_sections

ROOT = Path(__file__).resolve().parents[1]


def test_workspace_profile_files_are_stage7_read_only_data() -> None:
    profile = json.loads((ROOT / "profiles/default.json").read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "strategies/catalog.json").read_text(encoding="utf-8"))

    assert profile["schemaVersion"] == 1
    assert profile["id"] == "default"
    assert profile["strategyId"] == "manual-local"
    assert profile["buildTarget"] == "nfqws2"
    assert profile["safety"]["readOnlyInChecks"] is True
    assert profile["safety"]["mayUseSudo"] is False
    assert profile["safety"]["mayMutateServicesOrFirewall"] is False

    assert catalog["defaultStrategyId"] == "manual-local"
    assert catalog["safety"]["automaticChecksMayExecuteStrategies"] is False
    assert catalog["safety"]["strategiesArePlansOnly"] is True


def test_workspace_catalog_loads_profiles_and_strategies() -> None:
    catalog = load_workspace_catalog(ROOT)

    assert catalog.default_profile_id == "default"
    assert catalog.default_strategy_id == "manual-local"
    assert [profile.profile_id for profile in catalog.profiles] == ["default"]
    assert {strategy.strategy_id for strategy in catalog.strategies} == {
        "manual-local",
        "read-only-diagnostics",
        "community-discord-youtube-edge-flow",
    }

    default_profile = catalog.profile_by_id()["default"]
    assert default_profile.strategy_id == "manual-local"
    assert default_profile.build_target == "nfqws2"
    assert default_profile.is_read_only_stage7 is True
    assert default_profile.hostlists[0].path == "profiles/hostlists/default.hosts"

    manual_strategy = catalog.strategy_by_id()["manual-local"]
    assert manual_strategy.philosophy == "toolbox/apothecary"
    assert manual_strategy.is_plan_only is True
    assert manual_strategy.capabilities.uses_local_build_plan is True


def test_strategy_catalog_refuses_execution_in_checks() -> None:
    strategy_catalog = load_strategy_catalog(ROOT)

    assert strategy_catalog.automatic_checks_may_execute_strategies is False
    assert strategy_catalog.strategies_are_plans_only is True
    assert all(strategy.is_plan_only for strategy in strategy_catalog.strategies)
    assert validate_workspace_catalog(ROOT) == ()


def test_workspace_profile_cli_formatters_are_read_only_text() -> None:
    profiles_text = workspace_profiles_to_text(ROOT)
    profile_text = workspace_profile_to_text("default", ROOT)
    strategies_text = workspace_strategies_to_text(ROOT)
    strategy_text = workspace_strategy_to_text("manual-local", ROOT)

    assert "Workspace profiles:" in profiles_text
    assert "default" in profiles_text
    assert "read-only checks: yes" in profile_text
    assert "Workspace strategies:" in strategies_text
    assert "manual-local" in strategies_text
    assert "executes automatically: no" in strategy_text
    assert "requires sudo at Stage 7: no" in strategy_text


def test_workspace_profile_rejects_unknown_profile_or_strategy() -> None:
    with pytest.raises(ValueError):
        load_workspace_profile(ROOT, "missing")
    with pytest.raises(ValueError):
        workspace_strategy_to_text("missing", ROOT)


def test_navigation_marks_strategies_as_profiles_backed() -> None:
    sections = {section.key: section for section in default_navigation_sections()}

    assert sections["strategies"].ready_state == "profiles-backed"
    assert "Workspace-профили" in sections["strategies"].purpose


def test_gui_shell_state_exposes_workspace_catalog() -> None:
    state = load_gui_shell_state(ROOT)

    assert state.workspace_catalog.default_profile_id == "default"
    assert state.workspace_catalog.default_strategy_id == "manual-local"
    assert state.workspace_catalog.profile_by_id()["default"].build_target == "nfqws2"


def test_entrypoint_can_print_profiles_and_strategies_without_execution() -> None:
    assert main(["--list-profiles"]) == 0
    assert main(["--show-profile", "default"]) == 0
    assert main(["--list-strategies"]) == 0
    assert main(["--show-strategy", "manual-local"]) == 0
    assert "workspace profiles: 1; strategies: 3" in describe_project()



def _copy_project_for_strategy_tests(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))
    return project


def test_strategy_selection_overrides_default_profile_for_next_plans(tmp_path: Path) -> None:
    project = _copy_project_for_strategy_tests(tmp_path)

    result = select_workspace_strategy(project, strategy_id="read-only-diagnostics", profile_id="default")
    catalog = load_workspace_catalog(project)
    plan = create_runtime_plan(project, action="start", profile_id="default")

    assert "Strategy selection: saved" in result.to_text()
    assert catalog.active_selection is not None
    assert catalog.profile_by_id()["default"].strategy_id == "read-only-diagnostics"
    assert catalog.default_strategy_id == "read-only-diagnostics"
    assert plan.strategy.strategy_id == "read-only-diagnostics"
    assert "read-only-diagnostics" in plan.plan_id


def test_strategies_widget_is_a_real_selector_not_placeholder() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "strategies.py").read_text(encoding="utf-8")

    assert "QListWidget" in source
    assert "Выбрать для Default" in source
    assert "select_workspace_strategy" in source
