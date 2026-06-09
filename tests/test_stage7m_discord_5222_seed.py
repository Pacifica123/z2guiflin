from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.adapters.runtime_apply import create_runtime_apply_plan
from zap2_gui.adapters.workspace_profiles import load_strategy_catalog, select_workspace_strategy

ROOT = Path(__file__).resolve().parents[1]


def test_stage7m_discord_5222_minimal_strategy_is_registered() -> None:
    catalog = load_strategy_catalog(ROOT)
    strategies = catalog.by_id()

    assert "community-discord-hostfakesplit-5222-minimal" in strategies
    strategy = strategies["community-discord-hostfakesplit-5222-minimal"]
    args = "\n".join(strategy.runtime_args)

    assert strategy.is_plan_only is True
    assert "--lua-init=@core/zapret2/lua/custom_funcs.lua" in strategy.runtime_args
    assert "--ipcache-hostname=1" in strategy.runtime_args
    assert "--filter-tcp=80,443,1080,2053,2083,2087,2096,5222,8443" in strategy.runtime_args
    assert "hostfakesplit_multi:hosts=google.com,vimeo.com" in args
    assert "youtube.com" not in args
    assert "--filter-l7=stun,discord" not in strategy.runtime_args
    assert strategy.source_preset and strategy.source_preset["windowsOptionsExecuted"] is False


def test_stage7m_existing_community_discord_profiles_include_5222_hint() -> None:
    for filename in (
        "strategies/community-discord-youtube-edge-flow.json",
        "strategies/community-discord-syndata-edge-flow-v2.json",
    ):
        data = json.loads((ROOT / filename).read_text(encoding="utf-8"))
        args = data["runtimeArgs"]
        assert "--filter-tcp=80,443,1080,2053,2083,2087,2096,5222,8443" in args


def test_stage7m_runtime_apply_queues_5222_for_minimal_strategy(tmp_path: Path) -> None:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))

    select_workspace_strategy(project, "community-discord-hostfakesplit-5222-minimal", profile_id="default")
    plan = create_runtime_apply_plan(project, action="apply", profile_id="default")

    assert plan.strategy_id == "community-discord-hostfakesplit-5222-minimal"
    assert "5222" in plan.queued_tcp_ports
    assert "443" in plan.queued_tcp_ports
    assert "8443" in plan.queued_tcp_ports
    assert plan.queued_udp_ports == ()
    joined = "\n".join(" ".join(command.argv) for command in plan.commands)
    assert "tcp dport" in joined
    assert "5222" in joined


def test_stage7m_imported_discord_reference_preserves_windows_5222_hint() -> None:
    metadata = json.loads((ROOT / "strategies" / "imported" / "community-discord-hostfakesplit-5222.json").read_text(encoding="utf-8"))
    source = (ROOT / "strategies" / "imported" / "community-discord-hostfakesplit-5222.txt").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "DISCORD_COMMUNITY_5222_NOTES.md").read_text(encoding="utf-8")

    assert metadata["windowsOptionsExecuted"] is False
    assert "--wf-tcp-out=80,443,1080,2053,2083,2087,2096,5222,8443" in source
    assert "community-discord-hostfakesplit-5222-minimal" in docs
    assert "Stage 8" in docs
