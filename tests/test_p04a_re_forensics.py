from __future__ import annotations

import importlib.util
import json
import hashlib
from pathlib import Path

from zap2_gui import DEVELOPMENT_LINE, PRODUCT_LABEL, __version__
from zap2_gui.adapters.workspace_profiles import load_strategy_catalog, load_workspace_profile
from zap2_gui.models.domain_semantics import (
    ActionContract,
    CANONICAL_ACTION_VERBS,
    CANONICAL_DOMAIN_NOUNS,
)

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "runtime/p04/p04a-frozen-evidence.json"


def test_p03f_acceptance_promotes_product_baseline_before_p04() -> None:
    assert PRODUCT_LABEL == "v0.7"
    assert __version__ == "0.7.0"
    assert DEVELOPMENT_LINE == "P04b immutable execution Plan foundation toward v0.8"
    status = (ROOT / "docs/PROJECT_STATUS.md").read_text(encoding="utf-8")
    versioning = (ROOT / "docs/VERSIONING.md").read_text(encoding="utf-8")
    assert "READY_FOR_USE_WITHIN_P03" in status
    assert "v0.7" in versioning
    assert "P04a" in versioning
    assert "P04b" in versioning


def test_p04_ontology_names_core_domain_concepts() -> None:
    for noun in (
        "runtimeContext",
        "preset",
        "trafficProfile",
        "desyncAction",
        "tunnelConnection",
        "Plan",
        "probe",
        "Evidence",
        "Verdict",
        "Capability",
    ):
        assert noun in CANONICAL_DOMAIN_NOUNS
    for verb in ("plan", "confirm", "apply", "revert", "start", "stop", "probe", "launch"):
        assert verb in CANONICAL_ACTION_VERBS


def test_action_contract_rejects_metadata_only_visible_or_unsafe_mutation() -> None:
    metadata_only = ActionContract(
        action_id="runtime.start",
        label="Start runtime",
        effect="start",
        short_help="Start one confirmed runtime plan.",
        handler_id=None,
    )
    assert "visible ActionContract requires handler_id" in metadata_only.validation_errors()

    unsafe_direct = ActionContract(
        action_id="runtime.start",
        label="Start runtime",
        effect="start",
        short_help="Start one confirmed runtime plan.",
        handler_id="runtime.default.start",
        safe_invoke=True,
    )
    assert any("safeInvoke" in item for item in unsafe_direct.validation_errors())

    inspect = ActionContract(
        action_id="runtime.status",
        label="Runtime status",
        effect="inspect",
        short_help="Inspect local runtime state.",
        handler_id="runtime.status",
        safe_invoke=True,
    )
    assert inspect.is_valid


def test_runtime_context_and_preset_aliases_are_boundary_only() -> None:
    context = load_workspace_profile(ROOT, "default")
    assert context.runtime_context_id == context.profile_id == "default"
    assert context.preset_id == context.strategy_id
    strategy = load_strategy_catalog(ROOT).by_id()[context.strategy_id]
    assert strategy.preset_id == strategy.strategy_id


def test_frozen_p04a_decision_evidence_is_preserved_as_p04b_parent() -> None:
    frozen_bytes = BASELINE.read_bytes()
    frozen = json.loads(frozen_bytes.decode("utf-8"))
    p04b = json.loads((ROOT / "runtime/p04/p04b-frozen-evidence.json").read_text(encoding="utf-8"))
    assert p04b["parentP04aEvidenceSha256"] == hashlib.sha256(frozen_bytes).hexdigest()
    assert frozen["representation"]["exactExecutionRoundTrips"] == frozen["representation"]["strategyCount"] == 18
    assert frozen["representation"]["strategyJsonWithPresetPathAndRuntimeArgs"] > 0
    contradiction = frozen["cli"]["representativeContradiction"]
    assert contradiction["acceptedByArgparse"] is True
    assert contradiction["firstMatchDispatchWouldPrefer"] == "runtime_plan"
    assert frozen["sInstall"]["outsideCheckoutDefaultLayoutReady"] is False


def test_p04_recompiled_dag_keeps_p05_waiting() -> None:
    frozen = json.loads(BASELINE.read_text(encoding="utf-8"))
    dag = "\n".join(frozen["recompiledDag"])
    assert "P04b" in dag and "P04c" in dag and "P04d" in dag
    assert "P05 waits for P04d" in dag


def test_p04_docs_do_not_claim_full_p04_or_v08_acceptance() -> None:
    text = (ROOT / "docs/P04_REFORENSICS.md").read_text(encoding="utf-8")
    assert "P04a" in text
    assert "READY_FOR_USE_WITHIN_P04A" in text
    assert "P04b" in text and "P04c" in text and "P04d" in text
    assert "не" in text.lower() and "v0.8" in text
