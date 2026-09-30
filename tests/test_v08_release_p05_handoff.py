from __future__ import annotations

import hashlib
import json
from pathlib import Path

from zap2_gui import DEVELOPMENT_LINE, PRODUCT_LABEL, __version__
from zap2_gui.models.action_catalog import ACTION_CONTRACTS, action_projection_rows

ROOT = Path(__file__).resolve().parents[1]


def test_v08_is_final_accepted_product_marker_and_p05_is_next() -> None:
    assert PRODUCT_LABEL == "v0.10 RC6"
    assert __version__ == "0.10.0rc6"
    assert DEVELOPMENT_LINE == "P06 docs and reproducible distribution RC6 candidate"
    assert 'version = "0.10.0rc6"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_owner_p04d_receipt_closes_rc4_without_rewriting_frozen_evidence() -> None:
    receipt_path = ROOT / "runtime/p04/p04d-owner-acceptance-receipt.json"
    evidence_path = ROOT / "runtime/p04/p04d-frozen-evidence.json"
    release = json.loads((ROOT / "runtime/p04/v08-release-evidence.json").read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert receipt["result"] == "PASS"
    assert receipt["readiness"] == "READY_FOR_USE_WITHIN_P04D"
    assert receipt["baseLineage"] == "2fc0a34"
    assert release["transition"]["ownerReceiptSha256"] == hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    assert release["transition"]["parentP04dEvidenceSha256"] == hashlib.sha256(evidence_path.read_bytes()).hexdigest()


def test_p05_handoff_uses_action_contract_projection_not_third_registry() -> None:
    handoff = (ROOT / "docs/history/stages/V08_RELEASE_P05_HANDOFF.md").read_text(encoding="utf-8")
    prep = (ROOT / "docs/history/stages/P05_REFORENSICS.md").read_text(encoding="utf-8")
    assert len(ACTION_CONTRACTS) == 119
    assert len(action_projection_rows()) == 119
    assert "не становится третьим registry" in handoff
    assert "WITHOUT new semantic authority" in prep
    assert "page-local preset search" in handoff
    assert "EvidenceGraph" in prep and "CapabilityVerdict" in prep


def test_release_evidence_records_open_p05_metadata_work_without_claiming_it_implemented() -> None:
    data = json.loads((ROOT / "runtime/p04/v08-release-evidence.json").read_text(encoding="utf-8"))
    start = data["p05StartingPoint"]
    assert start["globalActionSearchImplemented"] is False
    assert start["keywordsCovered"] == 119
    assert start["deepHelpCovered"] == 0
    assert start["focusTargetCovered"] >= 1
    assert data["p04Closure"]["remainingLegacyOnly"] == 0
    assert data["transition"]["to"] == "0.8.0"
