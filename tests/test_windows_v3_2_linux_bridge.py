from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.adapters.runtime_apply import create_runtime_apply_plan
from zap2_gui.adapters.runtime_session import build_runtime_session_config
from zap2_gui.adapters.runtime_state import confirm_runtime_plan, prepare_runtime_plan
from zap2_gui.adapters.workspace_profiles import load_workspace_catalog, select_workspace_strategy

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    ignore = shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache")
    shutil.copytree(ROOT, project, ignore=ignore)
    return project


def _make_fake_binary(project: Path) -> None:
    binary = project / "core/zapret2/nfq2/nfqws2"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/usr/bin/env sh\nsleep 30\n", encoding="utf-8")
    binary.chmod(0o755)


def test_windows_all_tcp_udp_v3_2_bridge_registered() -> None:
    catalog = json.loads((ROOT / "strategies" / "catalog.json").read_text(encoding="utf-8"))
    assert "strategies/windows-all-tcp-udp-v3-2-linux-bridge.json" in catalog["strategyFiles"]

    strategy = load_workspace_catalog(ROOT).strategy_by_id()["windows-all-tcp-udp-v3-2-linux-bridge"]
    assert "--wf-tcp-out=80,443-65535" in (ROOT / "strategies/imported/windows-all-tcp-udp-v3-2.txt").read_text(encoding="utf-8")
    assert not any(arg.startswith("--wf-") for arg in strategy.runtime_args)
    assert not any("custom_diag.lua" in arg or "zapret-multishake.lua" in arg for arg in strategy.runtime_args)
    assert "--blob=tls_google:@core/zapret2/files/fake/tls_clienthello_www_google_com.bin" in strategy.runtime_args
    assert strategy.capture_policy is not None
    assert strategy.capture_policy["tcpOutPorts"] == ["80", "443-65535"]
    assert strategy.capture_policy["udpOutPorts"] == ["443-65535"]


def test_windows_v3_2_apply_plan_uses_wide_owner_ports(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    select_workspace_strategy(project, strategy_id="windows-all-tcp-udp-v3-2-linux-bridge")

    plan = create_runtime_apply_plan(project, action="apply", profile_id="default")
    assert plan.queued_tcp_ports == ("80", "443-65535")
    assert plan.queued_udp_ports == ("443-65535",)
    nft_text = "\n".join(" ".join(command.argv) for command in plan.commands)
    assert "tcp dport { 80, 443-65535 }" in nft_text
    assert "udp dport { 443-65535 }" in nft_text


def test_runtime_session_copies_blob_inputs_for_windows_v3_2_bridge(tmp_path: Path, monkeypatch) -> None:
    project = _copy_project(tmp_path)
    _make_fake_binary(project)
    select_workspace_strategy(project, strategy_id="windows-all-tcp-udp-v3-2-linux-bridge")
    prepare_runtime_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, "runtime-default-windows-all-tcp-udp-v3-2-linux-bridge-start-plan")

    monkeypatch.delenv("ZAP2_RUNTIME_DEBUG", raising=False)
    config = build_runtime_session_config(project, profile_id="default")
    assert len(config.blob_input_paths) == 2
    assert all(path.is_file() for path in config.blob_input_paths)
    blob_args = [arg for arg in config.runtime_args if arg.startswith("--blob=")]
    assert len(blob_args) == 2
    assert all("/zap2-runtime-inputs" in arg for arg in blob_args)
    assert not any("@core/zapret2/files/fake/" in arg for arg in blob_args)
