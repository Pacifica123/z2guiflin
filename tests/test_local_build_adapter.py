from __future__ import annotations

from pathlib import Path
import sys

import pytest

from zap2_gui.adapters.gui_state import load_gui_shell_state
from zap2_gui.adapters.local_build import create_local_build_plan, inspect_artifacts, supported_build_targets
from zap2_gui.app import describe_project, main

ROOT = Path(__file__).resolve().parents[1]


def test_local_build_targets_are_derived_from_build_map() -> None:
    assert supported_build_targets() == ("all", "nfqws2", "ip2net", "mdig", "clean")


def test_local_build_plan_for_all_is_plan_only_and_unprivileged() -> None:
    plan = create_local_build_plan(ROOT, target="all")

    assert plan.target == "all"
    assert plan.automatic_checks_may_execute is False
    assert plan.may_require_sudo is False
    assert plan.may_mutate_services_or_firewall is False
    assert len(plan.commands) == 1
    assert plan.commands[0].cwd == ROOT
    assert plan.commands[0].argv == (sys.executable, str(ROOT / "tools/core_generation_build.py"), "all")
    assert plan.commands[0].requires_sudo is False
    assert {artifact.relative_path for artifact in plan.expected_artifacts} == {
        "nfq2/nfqws2",
        "ip2net/ip2net",
        "mdig/mdig",
    }
    assert "libnetfilter_queue" in plan.required_libraries_hint


def test_local_build_plan_for_single_unit_uses_unit_makefile_directory() -> None:
    plan = create_local_build_plan(ROOT, target="ip2net")

    assert plan.commands[0].cwd == ROOT
    assert plan.commands[0].argv == (sys.executable, str(ROOT / "tools/core_generation_build.py"), "ip2net")
    assert [artifact.relative_path for artifact in plan.expected_artifacts] == ["ip2net/ip2net"]
    assert "sudo" not in " ".join(plan.commands[0].argv)


def test_local_build_plan_rejects_unknown_target() -> None:
    with pytest.raises(ValueError):
        create_local_build_plan(ROOT, target="install")


def test_artifact_inspection_is_read_only() -> None:
    plan = create_local_build_plan(ROOT, target="mdig")
    statuses = inspect_artifacts(plan)

    assert len(statuses) == 1
    assert statuses[0].artifact.relative_path == "mdig/mdig"
    assert isinstance(statuses[0].exists, bool)


def test_gui_shell_state_exposes_default_build_plan() -> None:
    state = load_gui_shell_state(ROOT)

    assert state.local_build_plan.target == "all"
    assert [artifact.unit_name for artifact in state.local_build_plan.expected_artifacts] == [
        "nfqws2",
        "ip2net",
        "mdig",
    ]


def test_entrypoint_can_print_build_plan_without_running_make() -> None:
    assert main(["--build-plan", "--build-target", "nfqws2"]) == 0
    assert "local build adapter: plan-only" in describe_project()
