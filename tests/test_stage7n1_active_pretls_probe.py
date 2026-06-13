from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.adapters.runtime_nft_state import runtime_nft_state_to_text, runtime_pretls_probe_to_text
from zap2_gui.adapters.workspace_profiles import select_workspace_strategy
from zap2_gui.app import main

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))
    return project


def _write_active_owner_rules(project: Path) -> None:
    sessions = project / ".zap2" / "runtime" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / "default.owner-rules.json").write_text(
        json.dumps(
            {
                "state": "applied",
                "strategyId": "community-discord-pretls-diagnostic-pktdebug",
                "nftTable": "zap2_default",
                "nfqueueNum": 421,
                "queuedTcpPorts": ["443", "5222"],
                "queuedUdpPorts": [],
                "queuedEdgeIps": ["162.159.128.233"],
                "capturePolicy": {"kind": "desktop-early-flow-v1"},
                "queueInputSynAck": True,
                "queueInputFinRst": True,
                "ownerUid": 1000,
                "ownerUidSource": "current-user",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_stage7n1_runtime_nft_state_prefers_active_owner_rules(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    select_workspace_strategy(project, "manual-local", profile_id="default")
    _write_active_owner_rules(project)

    text = runtime_nft_state_to_text(project, profile_id="default")

    assert "selected strategy: manual-local" in text
    assert "active/applied strategy: community-discord-pretls-diagnostic-pktdebug" in text
    assert "strategy mismatch: yes" in text
    assert "queued edge IPs: 162.159.128.233" in text
    assert "capture policy: desktop-early-flow-v1" in text
    assert "sudo nft -a list table inet zap2_default" in text
    assert "sudo nft list table" not in text


def test_stage7n1_pretls_probe_reports_not_applied_before_start(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    select_workspace_strategy(project, "community-discord-pretls-diagnostic-pktdebug", profile_id="default")

    text = runtime_pretls_probe_to_text(project, profile_id="default")

    assert "Runtime pre-TLS probe checklist" in text
    assert "owner-rules are not applied" in text
    assert "executes now: no" in text


def test_stage7n1_pretls_probe_reports_stale_session_when_rules_are_applied(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    select_workspace_strategy(project, "community-discord-pretls-diagnostic-pktdebug", profile_id="default")
    _write_active_owner_rules(project)

    text = runtime_pretls_probe_to_text(project, profile_id="default")

    assert "nft rules may be applied, but nfqws2 is not running" in text
    assert "queue bypass can hide userspace diagnostics" in text


def test_stage7n1_cli_exposes_pretls_probe(capsys) -> None:
    assert main(["--runtime-pretls-probe"]) == 0
    output = capsys.readouterr().out
    assert "Runtime pre-TLS probe checklist" in output
    assert "read-only: yes" in output
