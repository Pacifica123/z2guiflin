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
from zap2_gui.adapters.runtime_queue import resolve_nfqueue_num
from zap2_gui.adapters.runtime_state import confirm_runtime_plan

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc")
    shutil.copytree(ROOT, target, ignore=ignore)
    return target

class FakeNftRunner:
    def __init__(self, calls: list[tuple[str, ...]]):
        self.calls = calls
        self.exists = False
        self.table_text = ""

    def __call__(self, argv: tuple[str, ...]) -> RuntimeCommandResult:
        self.calls.append(argv)
        if argv[:4] == ("nft", "list", "table", "inet"):
            if not self.exists:
                return RuntimeCommandResult(argv=argv, returncode=1, stderr="Error: No such file or directory")
            return RuntimeCommandResult(argv=argv, returncode=0, stdout=self.table_text)
        if argv[:3] == ("nft", "--check", "-f"):
            return RuntimeCommandResult(argv=argv, returncode=0)
        if argv[:2] == ("nft", "-f"):
            text = Path(argv[2]).read_text(encoding="utf-8")
            if text.lstrip().startswith("delete table"):
                self.exists = False; self.table_text = ""
            else:
                self.exists = True; self.table_text = text
            return RuntimeCommandResult(argv=argv, returncode=0)
        return RuntimeCommandResult(argv=argv, returncode=0)


def test_runtime_apply_plan_is_owner_confirmed_nft_plan():
    plan = create_runtime_apply_plan(action="apply", profile_id="default")

    assert plan.plan_id == "runtime-default-manual-local-apply-owner-rules-plan"
    assert plan.profile_id == "default"
    assert plan.strategy_id == "manual-local"
    assert plan.nft_table.startswith("zap2_u")
    assert plan.nft_table.endswith("_default")
    assert plan.owner_key in plan.owner_marker
    assert plan.nfqueue_num == resolve_nfqueue_num(profile_id="default")
    assert 200 <= plan.nfqueue_num <= 599
    assert plan.requires_sudo is True
    assert plan.mutates_firewall is True
    payload = plan.to_payload()
    assert payload["safety"]["containsRemoteBootstrap"] is False
    assert payload["safety"]["containsUpstreamInstallerScript"] is False
    assert payload["safety"]["automaticChecksMayExecute"] is False
    assert payload["execution"]["executesNow"] is False
    assert plan.queued_tcp_ports == ("80", "443")
    assert plan.queued_udp_ports == ()
    assert plan.desync_mark == "0x40000000"
    assert plan.owner_uid >= 0
    all_argv = "\n".join(" ".join(command.argv) for command in plan.commands)
    assert f"nft add table inet {plan.nft_table}" in all_argv
    assert plan.owner_marker in all_argv
    assert f"queue num {plan.nfqueue_num} bypass" in all_argv
    assert "udp dport" not in all_argv
    assert f"meta skuid {plan.owner_uid}" in all_argv
    assert "meta mark & 0x40000000 == 0" in all_argv
    assert "ct original packets 1-8" in all_argv
    assert "curl" not in all_argv
    assert "wget" not in all_argv
    assert "install_easy" not in all_argv


def test_runtime_revert_plan_deletes_only_owned_table():
    plan = create_runtime_apply_plan(action="revert", profile_id="default")

    assert plan.plan_id == "runtime-default-manual-local-revert-owner-rules-plan"
    assert len(plan.commands) == 1
    assert plan.commands[0].argv == ("nft", "delete", "table", "inet", plan.nft_table)
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

    fake_runner = FakeNftRunner(calls)

    result = execute_runtime_owner_rules(
        project,
        action="apply",
        profile_id="default",
        confirm_plan_id=prepared.plan_id,
        runner=fake_runner,
        allow_without_root=True,
    )

    assert result.state == "applied"
    assert len(calls) == 3
    assert result.state_path.exists()
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["marker"] == "zap2-runtime-apply-v1"
    assert state["state"] == "applied"
    assert state["nftTable"].startswith("zap2_u")
    assert state["ownerKey"]
    assert state["ownerMarker"].startswith("zap2-owner:")
    assert state["transactionPath"]
    assert state["queuedTcpPorts"] == ["80", "443"]
    assert state["queuedUdpPorts"] == []
    assert state["desyncMark"] == "0x40000000"
    assert state["managesServiceNow"] is False
    assert state["containsRemoteBootstrap"] is False
    assert "owner-rules-apply-applied" in result.log_path.read_text(encoding="utf-8")


def test_execute_apply_uses_saved_owner_rules_after_sudo_identity_drift(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    monkeypatch.setenv("SUDO_UID", "1234")
    prepared = prepare_runtime_owner_rules_plan(project, action="apply", profile_id="default")
    confirm_runtime_plan(project, prepared.plan_id)
    saved = json.loads(prepared.plan_path.read_text(encoding="utf-8"))
    assert saved["ownerUid"] == 1234

    monkeypatch.setenv("SUDO_UID", "0")
    calls: list[tuple[str, ...]] = []

    fake_runner = FakeNftRunner(calls)

    result = execute_runtime_owner_rules(
        project,
        action="apply",
        profile_id="default",
        confirm_plan_id=prepared.plan_id,
        runner=fake_runner,
        allow_without_root=True,
    )

    assert result.state == "applied"
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    transaction = (project / state["transactionPath"]).read_text(encoding="utf-8")
    assert "meta skuid 1234" in transaction
    assert "meta skuid 0" not in transaction
    assert state["ownerUid"] == 1234


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
