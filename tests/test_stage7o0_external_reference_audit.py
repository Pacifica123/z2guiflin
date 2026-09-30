from __future__ import annotations

import json
from pathlib import Path

from zap2_gui.adapters.external_reference_audit import (
    external_reference_audit_to_text,
    load_external_reference_audit,
)
from zap2_gui.app import main

ROOT = Path(__file__).resolve().parents[1]


def test_stage7o0_reference_audit_is_reference_only() -> None:
    audit = load_external_reference_audit(ROOT)

    assert audit.stage == "v0.4-alpha_stage7o0"
    assert audit.safe_for_reference_only is True
    assert audit.external_scripts_execute is False
    assert audit.mutates_firewall_or_services is False
    assert len(audit.sources) >= 7
    assert any(source.source_id == "kartavkun-linux-main" for source in audit.sources)
    assert any(source.source_id == "zapret2-gui-windows" for source in audit.sources)


def test_stage7o0_reference_audit_records_broad_capture_lessons() -> None:
    audit = load_external_reference_audit(ROOT)
    findings = "\n".join(audit.cross_source_findings)
    kartavkun = {source.source_id: source for source in audit.sources}["kartavkun-linux-main"]
    vernette = {source.source_id: source for source in audit.sources}["zapret2-vernette-docker"]

    assert "Working references are strategy packs plus capture envelopes" in findings
    assert "50000-65535" in kartavkun.udp_ports
    assert "tcp out/in=20/10" == vernette.packet_window.split("; ")[0]
    assert not kartavkun.owner_scoped
    assert not kartavkun.edge_ip_scoped


def test_stage7o0_reference_audit_candidate_families_are_promoted_by_stage7o1() -> None:
    audit = load_external_reference_audit(ROOT)
    candidate_ids = {candidate.candidate_id for candidate in audit.candidate_families}
    catalog = json.loads((ROOT / "strategies" / "catalog.json").read_text(encoding="utf-8"))
    strategy_files = "\n".join(catalog["strategyFiles"])

    assert "reference-zapret2-generic-tls-fake" in candidate_ids
    assert "reference-linux-general-multisplit-like" in candidate_ids
    assert "reference-zapret2-generic-tls-fake" in strategy_files
    assert "reference-linux-general-multisplit-like" in strategy_files
    assert catalog["defaultStrategyId"] == "manual-local"

def test_stage7o0_external_reference_audit_cli(capsys) -> None:
    assert main(["--external-reference-audit"]) == 0
    output = capsys.readouterr().out

    assert "External working reference audit" in output
    assert "executes external scripts now: no" in output
    assert "mutates services/firewall now: no" in output
    assert "zapret2-vernette-docker" in output
    assert "reference-flowseal-simple-fake-like" in output


def test_stage7o0_docs_and_snippets_exist() -> None:
    assert (ROOT / "docs" / "history" / "stages" / "EXTERNAL_REFERENCE_AUDIT.md").is_file()
    snippets = sorted((ROOT / "references" / "external" / "snippets").glob("*.txt"))
    assert len(snippets) >= 4
    assert all(path.read_text(encoding="utf-8").strip() for path in snippets)
