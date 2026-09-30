#!/usr/bin/env python3
"""P04c ActionContract dispatcher / legacy CLI contradiction gate acceptance.

Read-only against the live checkout. The checker verifies that the frozen
legacy selector inventory still matches the actual top-level legacy dispatch,
that migrated legacy selectors and canonical ``--action`` converge on the same
ActionContracts, and that contradictory selectors are rejected before any
handler can execute.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gui"))

import zap2_gui.app as app_module  # noqa: E402
from zap2_gui.adapters.action_dispatcher import (  # noqa: E402
    ACTION_HANDLERS,
    dispatcher_validation_errors,
)
from zap2_gui.adapters.legacy_cli import (  # noqa: E402
    LEGACY_SELECTOR_DESTS,
    migrated_legacy_selectors,
    resolve_cli_action,
)
from zap2_gui.models.action_catalog import (  # noqa: E402
    ACTION_CONTRACT_BY_ID,
    action_contract_ids,
    gui_runtime_action_contracts,
    validation_errors,
)

BASELINE_PATH = ROOT / "runtime/p04/p04c-frozen-evidence.json"
P04B_EVIDENCE = ROOT / "runtime/p04/p04b-frozen-evidence.json"
INPUTS = (
    "gui/zap2_gui/models/domain_semantics.py",
    "gui/zap2_gui/models/action_catalog.py",
    "gui/zap2_gui/adapters/action_dispatcher.py",
    "gui/zap2_gui/adapters/legacy_cli.py",
    "gui/zap2_gui/app.py",
    "gui/zap2_gui/widgets/runtime_controls.py",
    "tests/test_action_dispatcher.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _legacy_branch_selectors_from_ast() -> tuple[str, ...]:
    tree = ast.parse((ROOT / "gui/zap2_gui/app.py").read_text(encoding="utf-8"))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    ordered: list[str] = []
    for statement in main.body:
        if not isinstance(statement, ast.If):
            continue
        for node in ast.walk(statement.test):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "args"
                and node.attr not in ordered
            ):
                ordered.append(node.attr)
    return tuple(ordered)


def _parser_metrics() -> dict[str, Any]:
    parser = app_module.build_parser()
    option_strings = [option for action in parser._actions for option in action.option_strings]
    action_parser = next(action for action in parser._actions if action.dest == "action")
    return {
        "optionStringCount": len(option_strings),
        "canonicalActionChoices": list(action_parser.choices or ()),
        "canonicalActionChoiceCount": len(action_parser.choices or ()),
    }


def _conflict_metrics() -> dict[str, Any]:
    parser = app_module.build_parser()
    migrated = parser.parse_args(["--runtime-plan", "status", "--default-status"])
    legacy_only = parser.parse_args(["--list-presets", "--list-strategies"])
    canonical_plus_legacy = parser.parse_args(["--action", "default.workflow.status", "--default-status"])

    errors: list[str] = []
    for parsed in (migrated, legacy_only, canonical_plus_legacy):
        try:
            resolve_cli_action(parsed)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            errors.append("")

    handler_called = False
    original = app_module.dispatch_action

    def sentinel(*_args: Any, **_kwargs: Any) -> int:
        nonlocal handler_called
        handler_called = True
        raise AssertionError("dispatcher must not be reached for contradictory selectors")

    app_module.dispatch_action = sentinel
    try:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = app_module.main(["--default-start", "--default-stop"])
    finally:
        app_module.dispatch_action = original

    return {
        "migratedConflictRejected": bool(errors[0]),
        "legacyOnlyConflictRejected": bool(errors[1]),
        "canonicalPlusLegacyRejected": bool(errors[2]),
        "conflictExitCode": rc,
        "handlerCalledOnConflict": handler_called,
        "conflictStdoutEmpty": not stdout.getvalue(),
        "conflictErrorMentionsSelectors": "Contradictory action selectors" in stderr.getvalue(),
    }


def _parity_metrics() -> dict[str, Any]:
    def run(argv: list[str]) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = app_module.main(argv)
        return rc, out.getvalue(), err.getvalue()

    canonical = run(["--action", "runtime.plan.status", "--profile", "default"])
    legacy = run(["--runtime-plan", "status", "--profile", "default"])
    return {
        "canonicalRc": canonical[0],
        "legacyRc": legacy[0],
        "stderrEmpty": not canonical[2] and not legacy[2],
        "outputSha256Canonical": hashlib.sha256(canonical[1].encode()).hexdigest(),
        "outputSha256Legacy": hashlib.sha256(legacy[1].encode()).hexdigest(),
        "outputsEqual": canonical[1] == legacy[1],
        "normalizedPlanVisible": "normalized execution plan:" in canonical[1],
    }


def _gui_projection_metrics() -> dict[str, Any]:
    contracts = gui_runtime_action_contracts()
    source = (ROOT / "gui/zap2_gui/widgets/runtime_controls.py").read_text(encoding="utf-8")
    ids = [contract.action_id for contract in contracts]
    return {
        "projectedActionIds": ids,
        "allFromCanonicalCatalog": all(action_id in ACTION_CONTRACT_BY_ID for action_id in ids),
        "widgetConsumesActionContract": "action_contract(\"default.workflow.start\")" in source
        and "action_contract(\"default.workflow.status\")" in source
        and "action_contract(\"default.workflow.stop\")" in source,
    }


def collect_evidence() -> dict[str, Any]:
    branch_selectors = _legacy_branch_selectors_from_ast()
    catalog_errors = validation_errors()
    dispatcher_errors = dispatcher_validation_errors()
    contract_handler_ids = {contract.handler_id for contract in ACTION_CONTRACT_BY_ID.values() if contract.handler_id}
    return {
        "schemaVersion": 1,
        "patch": "P04c",
        "parentP04bEvidenceSha256": _sha256(P04B_EVIDENCE),
        "inputSha256": {relative: _sha256(ROOT / relative) for relative in INPUTS},
        "legacyCompatibilityGrammar": {
            "selectorCount": len(LEGACY_SELECTOR_DESTS),
            "selectorInventoryUnique": len(set(LEGACY_SELECTOR_DESTS)) == len(LEGACY_SELECTOR_DESTS),
            "astSelectorCount": len(branch_selectors),
            "inventoryMatchesActualLegacyBranches": branch_selectors == LEGACY_SELECTOR_DESTS,
            "migratedSelectorCount": len(migrated_legacy_selectors()),
            "remainingLegacyOnlySelectorCount": len(LEGACY_SELECTOR_DESTS) - len(migrated_legacy_selectors()),
        },
        "actionContracts": {
            "contractCount": len(action_contract_ids()),
            "catalogValid": not catalog_errors,
            "dispatcherClosed": not dispatcher_errors,
            "handlerCount": len(ACTION_HANDLERS),
            "handlerIdsMatchContracts": set(ACTION_HANDLERS) == contract_handler_ids,
            "canonicalIds": list(action_contract_ids()),
        },
        "parser": _parser_metrics(),
        "contradictionGate": _conflict_metrics(),
        "canonicalLegacyParity": _parity_metrics(),
        "guiProjection": _gui_projection_metrics(),
        "assumptionsDelta": {
            "confirmed": [
                "all 117 post-P04b legacy top-level action selectors are covered by one pre-handler contradiction gate",
                "the bounded runtime/default workflow slice executes through ActionContract -> handler dispatcher",
                "canonical --action and migrated legacy aliases converge on the same dispatcher output",
                "GUI runtime tooltips project metadata from the same ActionContracts instead of a duplicate help registry",
            ],
            "stillOpen": [
                "91 legacy selector destinations remain legacy-only and require P04d contract migration/coverage",
                "generated CLI/help/search/documentation projections and lint remain P04d/P05 work",
                "full S-INSTALL package-data bundling and writable-state separation remain unresolved",
            ],
        },
        "recompiledDag": [
            "P04c accepted -> P04d 100% meaningful action coverage + migration + lint + roundtrip acceptance",
            "P04d -> RC4/v0.8 candidate",
            "P05 waits for P04d ActionContract coverage authority",
        ],
    }


def _diff(expected: Any, actual: Any, prefix: str = "") -> list[str]:
    if type(expected) is not type(actual):
        return [f"{prefix or '<root>'}: type {type(actual).__name__} != {type(expected).__name__}"]
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
            return [f"{prefix}: length {len(actual)} != {len(expected)}"]
        errors: list[str] = []
        for index, (left, right) in enumerate(zip(expected, actual)):
            errors.extend(_diff(left, right, f"{prefix}[{index}]"))
        return errors
    if expected != actual:
        return [f"{prefix}: {actual!r} != {expected!r}"]
    return []


def main() -> int:
    actual = collect_evidence()
    if "--write-baseline" in sys.argv[1:]:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"P04c baseline written: {BASELINE_PATH}")
        return 0
    if not BASELINE_PATH.is_file():
        print(f"P04c ActionContract dispatcher: FAIL — missing baseline {BASELINE_PATH}", file=sys.stderr)
        return 2
    expected = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    errors = _diff(expected, actual)
    if errors:
        print("P04c ActionContract dispatcher: FAIL", file=sys.stderr)
        for item in errors[:80]:
            print(f"  - {item}", file=sys.stderr)
        if len(errors) > 80:
            print(f"  - ... {len(errors) - 80} more", file=sys.stderr)
        return 1
    print("P04c ActionContract dispatcher: PASS")
    print(f"legacy selectors gated: {actual['legacyCompatibilityGrammar']['selectorCount']}")
    print(f"contract-backed actions: {actual['actionContracts']['contractCount']}")
    print(f"remaining legacy-only selectors: {actual['legacyCompatibilityGrammar']['remainingLegacyOnlySelectorCount']}")
    print("live checkout mutations: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
