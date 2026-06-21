from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.adapters.runtime_session import build_runtime_session_config
from zap2_gui.adapters.runtime_state import confirm_runtime_plan, prepare_runtime_plan
from zap2_gui.adapters.workspace_profiles import (
    load_strategy_catalog,
    select_workspace_strategy,
    workspace_strategy_to_text,
)

ROOT = Path(__file__).resolve().parents[1]
V2C_IDS = (
    "community-discord-syndata-edge-flow-v2c-send-only",
    "community-discord-syndata-edge-flow-v2c-fixed-sni",
    "community-discord-syndata-edge-flow-v2c-no-md5",
    "community-discord-syndata-edge-flow-v2c-host-first",
)


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(
        ROOT,
        project,
        ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"),
    )
    binary = project / "core" / "zapret2" / "nfq2" / "nfqws2"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    return project


def test_stage7w_v2c_matrix_strategies_are_registered() -> None:
    catalog = load_strategy_catalog(ROOT)
    strategies = catalog.by_id()

    for strategy_id in V2C_IDS:
        assert strategy_id in strategies
        strategy = strategies[strategy_id]
        args = "\n".join(strategy.runtime_args)
        assert strategy.is_plan_only is True
        assert "discordapp.com" in args
        assert "www.discordapp.com" in args
        assert "youtube.com,www.youtube.com" in args
        assert strategy.diagnostic_hints is not None
        assert strategy.diagnostic_hints["observedDiscordUrl"] == "https://discordapp.com/app"
        assert strategy.diagnostic_hints["matrixVariant"]


def test_stage7w_v2c_variants_have_distinct_phase_zero_shapes() -> None:
    strategies = load_strategy_catalog(ROOT).by_id()
    send_only = "\n".join(strategies["community-discord-syndata-edge-flow-v2c-send-only"].runtime_args)
    fixed_sni = "\n".join(strategies["community-discord-syndata-edge-flow-v2c-fixed-sni"].runtime_args)
    no_md5 = "\n".join(strategies["community-discord-syndata-edge-flow-v2c-no-md5"].runtime_args)
    host_first = list(strategies["community-discord-syndata-edge-flow-v2c-host-first"].runtime_args)

    assert "--lua-desync=syndata:blob=fake_default_tls:tls_mod=rnd,dupsid,rndsni" not in send_only
    assert "--lua-desync=send:tcp_md5:repeats=2" in send_only

    assert "--lua-desync=syndata:blob=fake_default_tls:tls_mod=rnd,dupsid,sni=google.com" in fixed_sni
    assert "--lua-desync=syndata:blob=fake_default_tls:tls_mod=rnd,dupsid,rndsni" not in fixed_sni

    assert "tcp_md5" not in no_md5
    assert "--lua-desync=send:repeats=2" in no_md5

    first_host = next(i for i, item in enumerate(host_first) if item.startswith("--hostlist-domains=updates.discord.com"))
    first_ipset = next(i for i, item in enumerate(host_first) if item.startswith("--ipset-ip=162.159"))
    assert first_host < first_ipset


def test_stage7w_show_strategy_reports_matrix_variant() -> None:
    text = workspace_strategy_to_text("community-discord-syndata-edge-flow-v2c-host-first", ROOT)

    assert "diagnostic hints:" in text
    assert "observed Discord URL: https://discordapp.com/app" in text
    assert "required hosts present in runtime args: yes" in text
    assert "matrix variant: host-first" in text
    assert "SYN-SENT -> ESTAB -> TLS ClientHello -> TLS ServerHello -> HTTP/" in text


def test_stage7w_generated_session_args_use_selected_v2c_variant(tmp_path: Path, monkeypatch) -> None:
    project = _copy_project(tmp_path)
    monkeypatch.setenv("ZAP2_PUBLIC_RUNTIME_INPUTS_DIR", str(tmp_path / "public-inputs"))

    select_workspace_strategy(project, "community-discord-syndata-edge-flow-v2c-no-md5", profile_id="default")
    prepared = prepare_runtime_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, prepared.plan_id)

    config = build_runtime_session_config(project, profile_id="default")
    args = "\n".join(config.runtime_args)

    assert prepared.strategy_id == "community-discord-syndata-edge-flow-v2c-no-md5"
    assert "discordapp.com" in args
    assert "www.discordapp.com" in args
    assert "tcp_md5" not in args
    assert "--lua-desync=syndata:blob=fake_default_tls:tls_mod=rnd,dupsid,rndsni" in args


def test_stage7w_docs_name_all_matrix_variants() -> None:
    doc = (ROOT / "docs" / "DISCORD_SYN_DATA_EDGE_FLOW_V2C_MATRIX.md").read_text(encoding="utf-8")
    results = (ROOT / "docs" / "DISCORD_COMMUNITY_EDGE_FLOW_RESULTS.md").read_text(encoding="utf-8")
    catalog = json.loads((ROOT / "strategies" / "catalog.json").read_text(encoding="utf-8"))

    for strategy_id in V2C_IDS:
        assert f"strategies/{strategy_id}.json" in catalog["strategyFiles"]
        assert strategy_id in doc
        assert strategy_id in results
