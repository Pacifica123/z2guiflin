from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from zap2_gui.adapters.core_generation import (
    COMPAT_RECEIPT_RELATIVE_PATH,
    OVERLAY_RELATIVE_PATH,
    P03_ARCHIVE_SHA256,
    P03_UPSTREAM_COMMIT,
    P03_UPSTREAM_VERSION,
    generation_identity_errors,
    sha256_file,
    source_transform_digest,
    shipping_corpus_digest,
    upstream_tree_files,
)
from zap2_gui.adapters.core_provenance import verify_core_bundle, write_core_build_receipt
from zap2_gui.adapters.runtime_apply import RuntimeCommandResult
from zap2_gui.adapters.runtime_default import execute_default_workflow, prepare_default_workflow_plan
from zap2_gui.adapters.runtime_state import confirm_runtime_plan

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns(".git", ".zap2", ".pytest_cache", "__pycache__", "*.pyc"))
    return target


def _fake_binary(project: Path, payload: bytes = b"#!/bin/sh\nexit 0\n") -> Path:
    path = project / "core/zapret2/nfq2/nfqws2"
    path.write_bytes(payload)
    path.chmod(0o755)
    return path


def test_p03_exact_candidate_identity_and_filtered_tree() -> None:
    manifest = json.loads((ROOT / "core/zapret2/UPSTREAM_IMPORT.json").read_text(encoding="utf-8"))
    assert manifest["upstreamCommit"] == P03_UPSTREAM_COMMIT
    assert manifest["upstreamVersion"] == P03_UPSTREAM_VERSION
    assert manifest["sourceArchiveSha256"] == P03_ARCHIVE_SHA256
    assert manifest["filterPolicyVersion"] == "zap2-p03-filter-v1"
    assert manifest["importedFileCount"] == 244
    assert len(upstream_tree_files(ROOT)) == 244
    assert not generation_identity_errors(ROOT)


def test_p03_overlay_is_explicit_and_outside_upstream_tree() -> None:
    assert not (ROOT / "core/zapret2/lua/custom_funcs.lua").exists()
    overlay = ROOT / OVERLAY_RELATIVE_PATH
    assert overlay.is_file()
    source = overlay.read_text(encoding="utf-8")
    assert "function hostfakesplit_multi" in source
    assert "local previous_host = desync.arg.host" in source
    assert "desync.arg.host = previous_host" in source
    assert "function hostfakesplit" in (ROOT / "core/zapret2/lua/zapret-antidpi.lua").read_text(encoding="utf-8")
    overlay_manifest = json.loads((ROOT / "core/overlays/zapret2/OVERLAY_MANIFEST.json").read_text(encoding="utf-8"))
    assert overlay_manifest["classification"] == "GENERATION_OVERLAY_SET"
    assert overlay_manifest["luaCompat"] == 6
    assert overlay_manifest["files"][0]["classification"] == "LOCAL_OVERLAY"
    assert len(overlay_manifest["sourceTransforms"]) == 1
    transform = overlay_manifest["sourceTransforms"][0]
    assert transform["classification"] == "SOURCE_TRANSFORM_OVERLAY"
    base = ROOT / "core/zapret2" / transform["targetPath"]
    effective = ROOT / transform["overlayPath"]
    assert sha256_file(base) == transform["baseSha256"]
    assert sha256_file(effective) == transform["effectiveSha256"]
    assert source_transform_digest(ROOT)
    base_text = base.read_text(encoding="utf-8")
    effective_text = effective.read_text(encoding="utf-8")
    assert base_text.index("droproot(params.uid") < base_text.index("nfq_init(&h, &qh, &cbdata)")
    assert effective_text.index("nfq_init(&h, &qh, &cbdata)") < effective_text.index("droproot(params.uid")


def test_p03_shipping_corpus_is_fully_classified() -> None:
    receipt = json.loads((ROOT / COMPAT_RECEIPT_RELATIVE_PATH).read_text(encoding="utf-8"))
    assert receipt["candidateCorpusSha256"] == shipping_corpus_digest(ROOT)
    assert receipt["shippingStrategyCount"] == 18
    assert len(receipt["strategies"]) == 18
    assert receipt["classificationCounts"] == {
        "equivalent": 9,
        "equivalent-local-overlay-relocation": 9,
        "changed-transformable": 0,
        "changed-unsupported": 0,
        "unknown": 0,
    }
    assert receipt["legacyNormalizedSemanticCorpusSha256"] == receipt["candidateNormalizedSemanticCorpusSha256"]
    assert receipt["targetedFixtures"]["sendDelay"]["delayArgumentCount"] == 0
    assert receipt["targetedFixtures"]["writableSpelling"]["result"] == "NOT_EXERCISED"
    assert len(receipt["targetedFixtures"]["hostfakesplitMulti"]["dependentShippingStrategies"]) == 9


def test_p03_generation_receipt_binds_overlay_compat_receipt_and_binary(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    binary = _fake_binary(project)
    write_core_build_receipt(project, [binary], "nfqws2")
    assert verify_core_bundle(project, binary).state == "verified"

    overlay = project / OVERLAY_RELATIVE_PATH
    overlay.write_text(overlay.read_text(encoding="utf-8") + "\n-- tamper\n", encoding="utf-8")
    status = verify_core_bundle(project, binary)
    assert status.state == "mismatch"
    assert "MIXED_GENERATION" in status.message


def test_p03_generation_receipt_rejects_source_transform_tamper(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    binary = _fake_binary(project)
    write_core_build_receipt(project, [binary], "nfqws2")
    manifest = json.loads((project / "core/overlays/zapret2/OVERLAY_MANIFEST.json").read_text(encoding="utf-8"))
    transform = manifest["sourceTransforms"][0]
    overlay = project / transform["overlayPath"]
    overlay.write_text(overlay.read_text(encoding="utf-8") + "\n/* tamper */\n", encoding="utf-8")
    status = verify_core_bundle(project, binary)
    assert status.state == "mismatch"
    assert "MIXED_GENERATION" in status.message


def test_p03_generation_receipt_rejects_compatibility_receipt_tamper(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    binary = _fake_binary(project)
    write_core_build_receipt(project, [binary], "nfqws2")
    receipt_path = project / COMPAT_RECEIPT_RELATIVE_PATH
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["acceptanceNote"] = "tampered"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status = verify_core_bundle(project, binary)
    assert status.state == "mismatch"
    assert "MIXED_GENERATION" in status.message


def test_p03_generation_receipt_rejects_binary_tamper(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    binary = _fake_binary(project)
    write_core_build_receipt(project, [binary], "nfqws2")
    binary.write_bytes(binary.read_bytes() + b"#tamper\n")
    binary.chmod(0o755)
    status = verify_core_bundle(project, binary)
    assert status.state == "mismatch"
    assert "binary" in status.message


def test_p03_missing_generation_receipt_is_not_runtime_ready(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    binary = _fake_binary(project)
    status = verify_core_bundle(project, binary)
    assert status.state == "unknown"
    assert status.runtime_ready is False
    assert "clean build" in status.message


def test_p03_default_start_rejects_unreceipted_generation_before_nft_apply(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    _fake_binary(project)
    plan = prepare_default_workflow_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, plan.plan_id)
    calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
        calls.append(argv)
        return RuntimeCommandResult(argv=argv, returncode=0)

    with pytest.raises(ValueError, match="core generation gate"):
        execute_default_workflow(
            project,
            action="start",
            profile_id="default",
            confirm_plan_id=plan.plan_id,
            apply_runner=runner,
            allow_without_root=True,
        )
    assert not any(call[:2] == ("nft", "-f") for call in calls)
