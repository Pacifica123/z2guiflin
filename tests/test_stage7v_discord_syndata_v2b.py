from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.adapters.runtime_apply import create_runtime_apply_plan
from zap2_gui.adapters.workspace_profiles import (
    load_strategy_catalog,
    select_workspace_strategy,
    workspace_strategy_to_text,
)

ROOT = Path(__file__).resolve().parents[1]


def test_stage7v_discord_syndata_v2b_is_registered_with_discordapp_hosts() -> None:
    catalog = load_strategy_catalog(ROOT)
    strategies = catalog.by_id()

    assert "community-discord-syndata-edge-flow-v2b" in strategies
    strategy = strategies["community-discord-syndata-edge-flow-v2b"]
    args = "\n".join(strategy.runtime_args)

    assert strategy.is_plan_only is True
    assert "--payload=empty" in strategy.runtime_args
    assert "--out-range=<s1" in strategy.runtime_args
    assert "--out-range=s1<d1" in strategy.runtime_args
    assert "discordapp.com" in args
    assert "www.discordapp.com" in args
    assert "--hostlist-domains=updates.discord.com,discord.com,discordapp.com,www.discordapp.com" in strategy.runtime_args
    assert "discord.com,discordapp.com,www.discordapp.com,gateway.discord.gg" in args
    assert "youtube.com,www.youtube.com" in args
    assert strategy.diagnostic_hints is not None
    assert strategy.diagnostic_hints["observedDiscordUrl"] == "https://discordapp.com/app"


def test_stage7v_show_strategy_exposes_phase_ladder_and_hostlist_check() -> None:
    text = workspace_strategy_to_text("community-discord-syndata-edge-flow-v2b", ROOT)

    assert "diagnostic hints:" in text
    assert "observed Discord URL: https://discordapp.com/app" in text
    assert "required hostlist hosts: discordapp.com, www.discordapp.com" in text
    assert "required hosts present in runtime args: yes" in text
    assert "SYN-SENT -> ESTAB -> TLS ClientHello -> TLS ServerHello -> HTTP/" in text
    assert "phase-zero helped TCP" in text


def test_stage7v_runtime_apply_queues_v2b_ports(tmp_path: Path) -> None:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))

    select_workspace_strategy(project, "community-discord-syndata-edge-flow-v2b", profile_id="default")
    plan = create_runtime_apply_plan(project, action="apply", profile_id="default")

    assert plan.strategy_id == "community-discord-syndata-edge-flow-v2b"
    assert "443" in plan.queued_tcp_ports
    assert "5222" in plan.queued_tcp_ports
    assert "8443" in plan.queued_tcp_ports
    assert plan.queued_udp_ports == ("443",)


def test_stage7v_documents_v2b_owner_phase_shift() -> None:
    strategy = json.loads((ROOT / "strategies" / "community-discord-syndata-edge-flow-v2b.json").read_text(encoding="utf-8"))
    doc = (ROOT / "docs" / "DISCORD_SYN_DATA_EDGE_FLOW_V2B.md").read_text(encoding="utf-8")
    results = (ROOT / "docs" / "DISCORD_COMMUNITY_EDGE_FLOW_RESULTS.md").read_text(encoding="utf-8")

    assert strategy["diagnosticHints"]["observedDiscordHost"] == "discordapp.com"
    assert "https://discordapp.com/app" in doc
    assert "SYN-SENT -> ESTAB -> TLS ClientHello -> TLS ServerHello -> HTTP/" in doc
    assert "community-discord-syndata-edge-flow-v2b" in results
    assert "ERR_TIMED_OUT" in results
