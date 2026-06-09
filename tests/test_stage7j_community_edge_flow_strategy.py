from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.adapters.runtime_apply import create_runtime_apply_plan
from zap2_gui.adapters.workspace_profiles import load_strategy_catalog, select_workspace_strategy

ROOT = Path(__file__).resolve().parents[1]


def test_stage7j_community_edge_flow_strategy_is_catalogued() -> None:
    catalog = load_strategy_catalog(ROOT)
    strategies = catalog.by_id()

    assert "community-discord-youtube-edge-flow" in strategies
    strategy = strategies["community-discord-youtube-edge-flow"]
    args = "\n".join(strategy.runtime_args)

    assert strategy.is_plan_only is True
    assert "--lua-init=@core/zapret2/lua/custom_funcs.lua" in strategy.runtime_args
    assert "--ipcache-hostname=1" in strategy.runtime_args
    assert "--ipset-ip=162.159.128.233" in args
    assert "--lua-desync=wssize:wsize=1:scale=6" in strategy.runtime_args
    assert "--lua-desync=syndata:blob=fake_default_tls" in strategy.runtime_args
    assert "hostfakesplit_multi:hosts=google.com,vimeo.com" in args
    assert "--filter-udp=443" in strategy.runtime_args
    assert strategy.source_preset and strategy.source_preset["windowsOptionsExecuted"] is False


def test_stage7j_custom_funcs_shim_defines_hostfakesplit_multi() -> None:
    source = (ROOT / "core" / "zapret2" / "lua" / "custom_funcs.lua").read_text(encoding="utf-8")

    assert "function hostfakesplit_multi" in source
    assert "hostfakesplit(ctx, desync)" in source
    assert "zap2_first_host" in source


def test_stage7j_runtime_apply_plan_queues_community_strategy_ports(tmp_path: Path) -> None:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))

    select_workspace_strategy(project, "community-discord-youtube-edge-flow", profile_id="default")
    plan = create_runtime_apply_plan(project, action="apply", profile_id="default")

    assert plan.strategy_id == "community-discord-youtube-edge-flow"
    assert "443" in plan.queued_tcp_ports
    assert "80" in plan.queued_tcp_ports
    assert "1080" in plan.queued_tcp_ports
    assert plan.queued_udp_ports == ("443",)
    joined = "\n".join(" ".join(command.argv) for command in plan.commands)
    assert "tcp dport" in joined
    assert "udp dport" in joined


def test_stage7j_imported_reference_documents_windows_boundary() -> None:
    metadata = json.loads((ROOT / "strategies" / "imported" / "community-discord-youtube-edge-flow.json").read_text(encoding="utf-8"))
    source = (ROOT / "strategies" / "imported" / "community-discord-youtube-edge-flow.txt").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "WINDOWS_COMMUNITY_PRESET_PORTING.md").read_text(encoding="utf-8")

    assert metadata["windowsOptionsExecuted"] is False
    assert "--wf-tcp-out=80,443-65535" in source
    assert "updates.discord.com" in source
    assert "WinDivert `--wf-*` options are omitted" in docs
