#!/usr/bin/env python3
"""Deterministic v0.8 promotion + P05 handoff evidence gate.

The P04d frozen evidence is historical pre-owner-acceptance evidence and is never
rewritten here.  This gate binds the separate owner receipt to the accepted P04
closure, proves the product metadata transition to v0.8, and freezes only the
facts required to start P05.  It performs no network/root/runtime mutation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gui"))

from zap2_gui import DEVELOPMENT_LINE, PRODUCT_LABEL, __version__  # noqa: E402
from zap2_gui.adapters.legacy_cli import LEGACY_SELECTOR_DESTS, remaining_legacy_only_selectors  # noqa: E402
from zap2_gui.adapters.action_dispatcher import ACTION_HANDLERS, dispatcher_validation_errors  # noqa: E402
from zap2_gui.models.action_catalog import ACTION_CONTRACTS, action_projection_rows, validation_errors  # noqa: E402
from zap2_gui.models.network_evidence import CapabilityVerdict, EvidenceGraph  # noqa: E402
from zap2_gui.adapters.runtime_kernel import RuntimeKernelStatus  # noqa: E402

EVIDENCE_PATH = ROOT / "runtime/p04/v08-release-evidence.json"
OWNER_RECEIPT_PATH = ROOT / "runtime/p04/p04d-owner-acceptance-receipt.json"
P04D_EVIDENCE_PATH = ROOT / "runtime/p04/p04d-frozen-evidence.json"

SEMANTIC_FILES = (
    "gui/zap2_gui/adapters/action_dispatcher.py",
    "gui/zap2_gui/adapters/legacy_cli.py",
    "gui/zap2_gui/models/action_catalog.py",
    "gui/zap2_gui/models/action_bindings.py",
    "gui/zap2_gui/models/action_bindings_generated.py",
    "gui/zap2_gui/widgets/runtime_controls.py",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_actual() -> dict[str, Any]:
    owner = json.loads(OWNER_RECEIPT_PATH.read_text(encoding="utf-8"))
    p04d = json.loads(P04D_EVIDENCE_PATH.read_text(encoding="utf-8"))
    rows = action_projection_rows()
    projection_keys = sorted(rows[0]) if rows else []

    def count_present(attr: str) -> int:
        count = 0
        for contract in ACTION_CONTRACTS:
            value = getattr(contract, attr)
            if isinstance(value, tuple):
                present = bool(value)
            elif isinstance(value, bool):
                present = value
            else:
                present = value not in (None, "")
            count += int(present)
        return count

    p04d_semantic_inputs = p04d.get("inputSha256", {})
    semantic_hashes = {name: _sha(ROOT / name) for name in SEMANTIC_FILES}
    unchanged_from_rc4 = {
        name: semantic_hashes[name] == p04d_semantic_inputs.get(name)
        for name in SEMANTIC_FILES
    }

    return {
        "schemaVersion": 1,
        "transition": {
            "from": "0.8.0rc4",
            "to": __version__,
            "productLabel": PRODUCT_LABEL,
            "developmentLine": DEVELOPMENT_LINE,
            "ownerP04dAcceptance": owner.get("result") == "PASS" and owner.get("readiness") == "READY_FOR_USE_WITHIN_P04D",
            "ownerReceiptSha256": _sha(OWNER_RECEIPT_PATH),
            "parentP04dEvidenceSha256": _sha(P04D_EVIDENCE_PATH),
        },
        "p04Closure": {
            "selectorCount": len(LEGACY_SELECTOR_DESTS),
            "remainingLegacyOnly": len(remaining_legacy_only_selectors()),
            "actionContractCount": len(ACTION_CONTRACTS),
            "handlerCount": len(ACTION_HANDLERS),
            "catalogValid": not validation_errors(),
            "dispatcherClosed": not dispatcher_validation_errors(),
            "p04dPairParity": bool(p04d.get("executionParity", {}).get("allPairsEqual")),
            "generatedMetadataStable": bool(p04d.get("generatedMetadata", {}).get("generatedMetadataMatchesGenerator")),
            "semanticFilesUnchangedFromRc4": unchanged_from_rc4,
        },
        "p05Dependencies": {
            "actionProjectionRows": len(rows),
            "evidenceGraphAvailable": EvidenceGraph is not None,
            "capabilityVerdictAvailable": CapabilityVerdict is not None,
            "runtimeKernelStatusAvailable": RuntimeKernelStatus is not None,
            "runtimeKernelHasNextAction": any(name in RuntimeKernelStatus.__dataclass_fields__ for name in ("next_safe_action", "next_action")),
        },
        "p05StartingPoint": {
            "projectionKeys": projection_keys,
            "keywordsCovered": count_present("keywords"),
            "conceptLinksCovered": count_present("concept_links"),
            "aliasesCovered": count_present("aliases"),
            "capabilityLinksCovered": count_present("capability"),
            "locationCovered": count_present("location"),
            "focusTargetCovered": count_present("focus_target"),
            "deepHelpCovered": count_present("deep_help"),
            "safeInvokeCount": count_present("safe_invoke"),
            "globalActionSearchImplemented": False,
            "decision": "P05 search/help/health must be a deterministic projection from ActionContract + typed evidence/state; no third semantic registry",
        },
        "assumptionsDelta": {
            "confirmed": [
                "P04 product transition is owner-accepted and eligible for v0.8 promotion",
                "ActionContract is stable enough to be the projection authority for P05",
                "P01 typed network evidence and P02 runtime next-action state exist for health projection",
            ],
            "new": [
                "P05 needs richer projection metadata/focus/help coverage before global UX can claim completeness",
                "page-local preset search must remain distinct from future global action/concept search",
            ],
            "deferred": [
                "full S-INSTALL package-data bundle and writable-state separation remain P06/productization scope",
            ],
        },
        "recompiledDag": [
            "v0.8 accepted P04 closure -> P05 discoverability/help/unified health UX",
            "P05 accepted -> re-forensics -> RC5/version transition candidate",
            "P06 docs/release/productization remains after P05",
            "P07 v1 qualification remains final planned qualification node",
        ],
    }


def _diff(expected: Any, actual: Any, prefix: str = "") -> list[str]:
    if type(expected) is not type(actual):
        return [f"{prefix or '<root>'}: type {type(expected).__name__} != {type(actual).__name__}"]
    if isinstance(expected, dict):
        errors: list[str] = []
        for key in sorted(set(expected) | set(actual)):
            here = f"{prefix}.{key}" if prefix else key
            if key not in expected:
                errors.append(f"{here}: unexpected")
            elif key not in actual:
                errors.append(f"{here}: missing")
            else:
                errors.extend(_diff(expected[key], actual[key], here))
        return errors
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [f"{prefix}: length {len(expected)} != {len(actual)}"]
        errors: list[str] = []
        for index, (left, right) in enumerate(zip(expected, actual)):
            errors.extend(_diff(left, right, f"{prefix}[{index}]"))
        return errors
    return [] if expected == actual else [f"{prefix}: {expected!r} != {actual!r}"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="freeze current deterministic release evidence")
    args = parser.parse_args()
    actual = _build_actual()

    if args.write:
        EVIDENCE_PATH.write_text(json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"v0.8 release evidence written: {EVIDENCE_PATH}")
        return 0

    if not EVIDENCE_PATH.exists():
        print(f"v0.8 release evidence missing: {EVIDENCE_PATH}", file=sys.stderr)
        return 1
    expected = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    errors = _diff(expected, actual)
    if errors:
        print("v0.8 release / P05 handoff evidence mismatch:", file=sys.stderr)
        for item in errors[:100]:
            print(f"  - {item}", file=sys.stderr)
        return 1

    transition = actual["transition"]
    closure = actual["p04Closure"]
    deps = actual["p05Dependencies"]
    if transition["to"] != "0.8.0" or transition["productLabel"] != "v0.8":
        print("final v0.8 product metadata not promoted", file=sys.stderr)
        return 1
    if not transition["ownerP04dAcceptance"]:
        print("owner P04d acceptance receipt is not PASS", file=sys.stderr)
        return 1
    if closure["selectorCount"] != 117 or closure["remainingLegacyOnly"] != 0 or closure["actionContractCount"] != 119 or closure["handlerCount"] != 119:
        print("P04 closure inventory changed", file=sys.stderr)
        return 1
    if not closure["catalogValid"] or not closure["dispatcherClosed"] or not closure["p04dPairParity"] or not closure["generatedMetadataStable"]:
        print("P04 deterministic closure predicates are not all true", file=sys.stderr)
        return 1
    if not all(closure["semanticFilesUnchangedFromRc4"].values()):
        print("promotion patch changed P04 semantic authority files", file=sys.stderr)
        return 1
    if not all((deps["evidenceGraphAvailable"], deps["capabilityVerdictAvailable"], deps["runtimeKernelStatusAvailable"], deps["runtimeKernelHasNextAction"])):
        print("P05 typed-evidence/runtime-state prerequisites are missing", file=sys.stderr)
        return 1

    print("v0.8 release / P05 handoff: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
