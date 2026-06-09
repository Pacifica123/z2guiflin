from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.adapters.runtime_apply import create_runtime_apply_plan
from zap2_gui.adapters.runtime_nft_state import runtime_nft_state_to_text
from zap2_gui.adapters.workspace_profiles import load_strategy_catalog, select_workspace_strategy, workspace_strategy_to_text
from zap2_gui.app import main

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))
    return project


def test_stage7n_diagnostic_strategy_is_registered_with_capture_policy() -> None:
    catalog = load_strategy_catalog(ROOT)
    strategy = catalog.by_id()["community-discord-pretls-diagnostic-pktdebug"]

    assert strategy.is_plan_only is True
    assert strategy.capture_policy is not None
    assert strategy.capture_policy["kind"] == "desktop-early-flow-v1"
    assert strategy.capture_policy["tcpOutPorts"] == ["443", "5222"]
    assert strategy.capture_policy["queueInputSynAck"] is True
    assert strategy.capture_policy["queueInputFinRst"] is True
    assert "162.159.128.233" in strategy.capture_policy["edgeIps"]
    assert "--lua-desync=pktdebug" in strategy.runtime_args
    assert "capture policy: desktop-early-flow-v1" in workspace_strategy_to_text("community-discord-pretls-diagnostic-pktdebug", ROOT)


def test_stage7n_capture_policy_drives_nft_ports_edges_and_counters(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    select_workspace_strategy(project, "community-discord-pretls-diagnostic-pktdebug", profile_id="default")

    plan = create_runtime_apply_plan(project, action="apply", profile_id="default")
    joined = "\n".join(" ".join(command.argv) for command in plan.commands)

    assert plan.queued_tcp_ports == ("443", "5222")
    assert plan.queued_udp_ports == ()
    assert "162.159.128.233" in plan.queued_edge_ips
    assert plan.capture_policy and plan.capture_policy["kind"] == "desktop-early-flow-v1"
    assert plan.queue_input_syn_ack is True
    assert plan.queue_input_fin_rst is True
    assert "counter queue num" in joined
    assert "ip daddr" in joined
    assert "ip saddr" in joined
    assert "tcp-in-synack" in joined
    assert "tcp-in-fin-rst" in joined
    assert "5222" in joined
    payload = plan.to_payload()
    assert payload["nftCountersEnabled"] is True
    assert payload["capturePolicy"]["kind"] == "desktop-early-flow-v1"


def test_stage7n_runtime_nft_state_is_read_only_text(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    select_workspace_strategy(project, "community-discord-pretls-diagnostic-pktdebug", profile_id="default")

    text = runtime_nft_state_to_text(project, profile_id="default")

    assert "Runtime nft/NFQUEUE state snapshot" in text
    assert "community-discord-pretls-diagnostic-pktdebug" in text
    assert "capture policy: desktop-early-flow-v1" in text
    assert "sudo nft list table inet zap2_default -a" in text
    assert "read-only: yes" in text
    assert "executes now: no" in text


def test_stage7n_cli_exposes_runtime_nft_state_without_execution(capsys) -> None:
    assert main(["--runtime-nft-state"]) == 0
    output = capsys.readouterr().out
    assert "Runtime nft/NFQUEUE state snapshot" in output
    assert "manual counter check" in output


def test_stage7n_docs_explain_pretls_diagnostic_branch() -> None:
    docs = (ROOT / "docs" / "DISCORD_PRETLS_OBSERVABILITY.md").read_text(encoding="utf-8")
    strategy = json.loads((ROOT / "strategies" / "community-discord-pretls-diagnostic-pktdebug.json").read_text(encoding="utf-8"))

    assert "SYN-SENT" in docs
    assert "capturePolicy" in docs
    assert "nft counters" in docs
    assert strategy["capturePolicy"]["dns53ForIpcache"] == "diagnostic-only"
