from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.adapters.runtime_apply import create_runtime_apply_plan
from zap2_gui.adapters.workspace_profiles import load_strategy_catalog, select_workspace_strategy, workspace_strategy_to_text

ROOT = Path(__file__).resolve().parents[1]

CANDIDATES = {
    "reference-zapret2-generic-tls-fake",
    "reference-linux-general-multisplit-like",
    "reference-flowseal-simple-fake-like",
}


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))
    return project


def test_stage7o1_reference_candidates_are_registered_and_non_default() -> None:
    catalog = load_strategy_catalog(ROOT)
    ids = {strategy.strategy_id for strategy in catalog.strategies}

    assert CANDIDATES <= ids
    assert catalog.default_strategy_id == "manual-local"
    for strategy_id in CANDIDATES:
        strategy = catalog.by_id()[strategy_id]
        assert strategy.is_plan_only is True
        assert strategy.capture_policy is not None
        assert strategy.capture_policy["kind"] == "external-reference-first-data-v1"
        assert strategy.capture_policy["ownerUidScoped"] is True
        assert strategy.capture_policy["edgeIps"] == []
        assert strategy.capture_policy["udpOutPorts"] == []
        assert "external" in strategy.source_preset["id"]


def test_stage7o1_reference_general_hostlist_is_curated_data_only() -> None:
    hostlist = ROOT / "profiles" / "hostlists" / "reference-general.hosts"
    text = hostlist.read_text(encoding="utf-8")

    assert "discord.com" in text
    assert "updates.discord.com" in text
    assert "cloudflare-ech.com" in text
    assert "youtube.com" in text
    assert "install" not in hostlist.name.lower()


def test_stage7o1_capture_policy_broadens_tcp_without_edge_ip_scope(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    select_workspace_strategy(project, "reference-linux-general-multisplit-like", profile_id="default")

    plan = create_runtime_apply_plan(project, action="apply", profile_id="default")
    joined = "\n".join(" ".join(command.argv) for command in plan.commands)

    assert plan.capture_policy and plan.capture_policy["kind"] == "external-reference-first-data-v1"
    assert plan.queued_edge_ips == ()
    assert plan.queued_udp_ports == ()
    assert plan.queued_tcp_ports == ("80", "443", "2053", "2083", "2087", "2096", "8443")
    assert "ip daddr" not in joined
    assert "tcp dport { 80, 443, 2053, 2083, 2087, 2096, 8443 }" in joined
    assert "counter queue num" in joined
    assert "tcp-in-synack" in joined


def test_stage7o1_candidate_texts_explain_reference_lane() -> None:
    text = workspace_strategy_to_text("reference-flowseal-simple-fake-like", ROOT)
    docs = (ROOT / "docs" / "history" / "stages" / "EXTERNAL_REFERENCE_CANDIDATE_STRATEGIES.md").read_text(encoding="utf-8")
    audit = json.loads((ROOT / "references" / "external" / "stage7o0_external_reference_audit.json").read_text(encoding="utf-8"))

    assert "reference-flowseal-simple-fake-like" in text
    assert "capture policy: external-reference-first-data-v1" in text
    assert "UDP/STUN/game filter: отложены" in docs
    stages = {item["id"]: item["stage"] for item in audit["candidateFamilies"]}
    assert stages["reference-zapret2-generic-tls-fake"] == "stage7o1-owner-selectable-candidate"
    assert stages["reference-discord-urgent-sni-later"] == "deferred-after-compatibility-proof"


def test_stage7o1_guided_probe_accepts_external_reference_capture_policy() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "adapters" / "discord_pretls_guided_probe.py").read_text(encoding="utf-8")

    assert "external-reference-first-data-v1" in source
