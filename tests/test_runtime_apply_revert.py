import json
import shutil
from pathlib import Path

import pytest

from zap2_gui.adapters.runtime_apply import (
    RuntimeCommandResult,
    create_runtime_apply_plan,
    execute_runtime_owner_rules,
    prepare_runtime_owner_rules_plan,
    runtime_apply_plan_to_text,
)
from zap2_gui.adapters.runtime_state import confirm_runtime_plan

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc")
    shutil.copytree(ROOT, target, ignore=ignore)
    return target


def test_runtime_apply_plan_is_owner_confirmed_nft_plan():
    plan = create_runtime_apply_plan(action="apply", profile_id="default")

    assert plan.plan_id == "runtime-default-manual-local-apply-owner-rules-plan"
    assert plan.profile_id == "default"
    assert plan.strategy_id == "manual-local"
    assert plan.nft_table == "zap2_default"
    assert plan.nfqueue_num == 200
    assert plan.requires_sudo is True
    assert plan.mutates_firewall is True
    payload = plan.to_payload()
    assert payload["safety"]["containsRemoteBootstrap"] is False
    assert payload["safety"]["containsUpstreamInstallerScript"] is False
    assert payload["safety"]["automaticChecksMayExecute"] is False
    assert payload["execution"]["executesNow"] is False
    all_argv = "\n".join(" ".join(command.argv) for command in plan.commands)
    assert "nft add table inet zap2_default" in all_argv
    assert "queue num 200 bypass" in all_argv
    assert "curl" not in all_argv
    assert "wget" not in all_argv
    assert "install_easy" not in all_argv


def test_runtime_revert_plan_deletes_only_owned_table():
    plan = create_runtime_apply_plan(action="revert", profile_id="default")

    assert plan.plan_id == "runtime-default-manual-local-revert-owner-rules-plan"
    assert len(plan.commands) == 1
    assert plan.commands[0].argv == ("nft", "delete", "table", "inet", "zap2_default")
    assert plan.commands[0].ignore_missing_on_revert is True
    assert "чужие" in "\n".join(plan.rollback_notes)


def test_runtime_apply_plan_text_exposes_boundary():
    text = runtime_apply_plan_to_text(action="apply", profile_id="default")

    assert "Runtime apply plan" in text
    assert "engine: nftables" in text
    assert "requires owner confirmation: yes" in text
    assert "requires sudo when executed by owner: yes" in text
    assert "contains remote bootstrap: no" in text
    assert "contains upstream installer script: no" in text
    assert "automatic checks may execute: no" in text
    assert "executes now: no" in text


def test_prepare_confirm_and_execute_apply_with_fake_runner(tmp_path):
    project = _copy_project(tmp_path)
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

    assert result.state == "applied"
    assert len(calls) == 4
    assert result.state_path.exists()
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["marker"] == "zap2-runtime-apply-v1"
    assert state["state"] == "applied"
    assert state["nftTable"] == "zap2_default"
    assert state["managesServiceNow"] is False
    assert state["containsRemoteBootstrap"] is False
    assert "owner-rules-apply-applied" in result.log_path.read_text(encoding="utf-8")


def test_execute_apply_requires_confirmation(tmp_path):
    project = _copy_project(tmp_path)
    prepared = prepare_runtime_owner_rules_plan(project, action="apply", profile_id="default")

    with pytest.raises(ValueError, match="Confirmation"):
        execute_runtime_owner_rules(
            project,
            action="apply",
            profile_id="default",
            confirm_plan_id=prepared.plan_id,
            runner=lambda argv: RuntimeCommandResult(argv=argv, returncode=0),
            allow_without_root=True,
        )


def test_revert_treats_missing_owned_table_as_safe(tmp_path):
    project = _copy_project(tmp_path)
    prepared = prepare_runtime_owner_rules_plan(project, action="revert", profile_id="default")
    confirm_runtime_plan(project, prepared.plan_id)

    def fake_runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
        return RuntimeCommandResult(argv=argv, returncode=1, stderr="Error: No such file or directory")

    result = execute_runtime_owner_rules(
        project,
        action="revert",
        profile_id="default",
        confirm_plan_id=prepared.plan_id,
        runner=fake_runner,
        allow_without_root=True,
    )

    assert result.state == "reverted"
    assert "already missing" in result.message
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["state"] == "reverted"
