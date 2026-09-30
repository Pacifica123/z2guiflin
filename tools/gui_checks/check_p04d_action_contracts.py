#!/usr/bin/env python3
"""P04d ActionContract closure / generated projection / roundtrip acceptance."""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
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
    _materialize_compat_selector,
    dispatcher_validation_errors,
)
from zap2_gui.adapters.legacy_cli import (  # noqa: E402
    LEGACY_SELECTOR_DESTS,
    STATIC_MIGRATED_SELECTOR_MAP,
    active_legacy_selectors,
    migrated_legacy_selectors,
    remaining_legacy_only_selectors,
    resolve_cli_action,
)
from zap2_gui.models.action_bindings import GENERATED_LEGACY_ACTION_BINDINGS  # noqa: E402
from zap2_gui.models.action_catalog import (  # noqa: E402
    ACTION_CONTRACT_BY_ID,
    action_contract_ids,
    action_projection_rows,
    gui_runtime_action_contracts,
    validation_errors,
)

BASELINE_PATH = ROOT / "runtime/p04/p04d-frozen-evidence.json"
P04C_EVIDENCE = ROOT / "runtime/p04/p04c-frozen-evidence.json"
INPUTS = (
    "gui/zap2_gui/models/action_bindings_generated.py",
    "gui/zap2_gui/models/action_bindings.py",
    "gui/zap2_gui/models/action_catalog.py",
    "gui/zap2_gui/adapters/action_dispatcher.py",
    "gui/zap2_gui/adapters/legacy_cli.py",
    "gui/zap2_gui/app.py",
    "gui/zap2_gui/widgets/runtime_controls.py",
    "meta_tools/generate_p04d_action_bindings.py",
    "tests/test_action_dispatcher.py",
    "tests/test_p04d_action_contract_closure.py",
    "docs/history/stages/P04D_ACTION_CONTRACT_CLOSURE.md",
    "tools/gui_checks/check_p04d_action_contracts.py",
    "tools/gui_checks/check_p04d_regression.py",
    "tools/gui_checks/check_project_tree.py",
    "meta_tools/hyperpatch_acceptance.sh",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selector_attrs(function_name: str) -> tuple[str, ...]:
    tree = ast.parse((ROOT / "gui/zap2_gui/app.py").read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function_name)
    ordered: list[str] = []
    for statement in fn.body:
        if not isinstance(statement, ast.If):
            continue
        for node in ast.walk(statement.test):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "args"
                and node.attr in LEGACY_SELECTOR_DESTS
                and node.attr not in ordered
            ):
                ordered.append(node.attr)
    return tuple(ordered)


def _parser_metrics() -> dict[str, Any]:
    parser = app_module.build_parser()
    option_strings = [option for action in parser._actions for option in action.option_strings]
    action_parser = next(action for action in parser._actions if action.dest == "action")
    operand_parser = next(action for action in parser._actions if action.dest == "operand")
    return {
        "optionStringCount": len(option_strings),
        "canonicalActionChoiceCount": len(action_parser.choices or ()),
        "canonicalActionChoices": list(action_parser.choices or ()),
        "operandIsRepeatable": operand_parser.__class__.__name__ == "_AppendAction",
    }


def _generator_metrics() -> dict[str, Any]:
    path = ROOT / "meta_tools/generate_p04d_action_bindings.py"
    spec = importlib.util.spec_from_file_location("p04d_binding_generator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rendered = module.render()
    actual = (ROOT / "gui/zap2_gui/models/action_bindings_generated.py").read_text(encoding="utf-8")
    return {
        "generatedBindingCount": len(GENERATED_LEGACY_ACTION_BINDINGS),
        "generatedMetadataMatchesGenerator": rendered == actual,
        "generatedMetadataSha256": hashlib.sha256(actual.encode()).hexdigest(),
    }


def _sample_operands(binding: Any) -> list[str]:
    if binding.operand_arity == 0:
        return []
    if binding.choices:
        return [binding.choices[0] for _ in range(binding.operand_arity)]
    return [f"sample-{index + 1}" for index in range(binding.operand_arity)]


def _roundtrip_metrics() -> dict[str, Any]:
    parser = app_module.build_parser()
    failures: list[str] = []
    cases = 0

    for binding in GENERATED_LEGACY_ACTION_BINDINGS:
        operands = _sample_operands(binding)
        legacy_argv = [binding.option_strings[0], *operands]
        canonical_argv = ["--action", binding.action_id]
        for operand in operands:
            canonical_argv.extend(["--operand", operand])
        legacy_args = parser.parse_args(legacy_argv)
        canonical_args = parser.parse_args(canonical_argv)
        legacy_resolution = resolve_cli_action(legacy_args)
        canonical_resolution = resolve_cli_action(canonical_args)
        materialized = _materialize_compat_selector(binding, canonical_args)
        cases += 1
        if legacy_resolution.canonical_action_id != binding.action_id:
            failures.append(f"legacy:{binding.selector}")
        if canonical_resolution.canonical_action_id != binding.action_id:
            failures.append(f"canonical:{binding.action_id}")
        if active_legacy_selectors(materialized) != (binding.selector,):
            failures.append(f"materialized-active:{binding.selector}")
        if getattr(materialized, binding.selector) != getattr(legacy_args, binding.selector):
            failures.append(f"materialized-value:{binding.selector}")

    by_dest = {action.dest: action for action in parser._actions}
    for selector, action_id in STATIC_MIGRATED_SELECTOR_MAP.items():
        action = by_dest[selector]
        args = parser.parse_args([action.option_strings[0]])
        cases += 1
        if resolve_cli_action(args).canonical_action_id != action_id:
            failures.append(f"curated:{selector}")
    for verb in ("start", "stop", "status"):
        cases += 1
        if resolve_cli_action(parser.parse_args(["--runtime-plan", verb])).canonical_action_id != f"runtime.plan.{verb}":
            failures.append(f"runtime-plan:{verb}")

    return {
        "roundtripCaseCount": cases,
        "expectedCaseCount": len(action_contract_ids()),
        "failures": failures,
        "allRoundtripsPass": not failures and cases == len(action_contract_ids()),
    }


def _run(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = app_module.main(argv)
    return rc, out.getvalue(), err.getvalue()


def _normalize_project_output(text: str) -> str:
    """Remove checkout location from frozen output evidence without changing parity semantics."""
    return text.replace(str(ROOT), "<PROJECT_ROOT>").replace(sys.executable, "<PYTHON>")


def _execution_parity_metrics() -> dict[str, Any]:
    pairs = (
        (["--runtime-plan", "status", "--profile", "default"], ["--action", "runtime.plan.status", "--profile", "default"]),
        (["--list-presets"], ["--action", "preset.list"]),
        (["--show-preset", "manual-local"], ["--action", "preset.show", "--operand", "manual-local"]),
        (["--build-plan", "--build-target", "nfqws2"], ["--action", "build.plan", "--build-target", "nfqws2"]),
        (["--har-plan"], ["--action", "har.plan"]),
    )
    results: list[dict[str, Any]] = []
    for legacy_argv, canonical_argv in pairs:
        legacy = _run(list(legacy_argv))
        canonical = _run(list(canonical_argv))
        results.append(
            {
                "legacy": legacy_argv,
                "canonical": canonical_argv,
                "legacyRc": legacy[0],
                "canonicalRc": canonical[0],
                "outputsEqual": legacy[1] == canonical[1],
                "stderrEqual": legacy[2] == canonical[2],
                "normalizedOutputSha256": hashlib.sha256(_normalize_project_output(canonical[1]).encode()).hexdigest(),
                "normalizedStderrSha256": hashlib.sha256(_normalize_project_output(canonical[2]).encode()).hexdigest(),
            }
        )
    return {
        "pairCount": len(results),
        "allPairsEqual": all(
            item["legacyRc"] == item["canonicalRc"] and item["outputsEqual"] and item["stderrEqual"]
            for item in results
        ),
        "pairs": results,
    }


def _contradiction_metrics() -> dict[str, Any]:
    cases = (
        ["--runtime-plan", "status", "--default-status"],
        ["--list-presets", "--list-strategies"],
        ["--action", "preset.list", "--list-presets"],
    )
    results = [_run(list(case)) for case in cases]
    operand_without_action = _run(["--operand", "x"])
    return {
        "caseCount": len(cases),
        "allRejectedWithTwo": all(item[0] == 2 for item in results),
        "allStdoutEmpty": all(not item[1] for item in results),
        "allMentionContradiction": all("Contradictory action selectors" in item[2] for item in results),
        "operandWithoutActionRejected": operand_without_action[0] == 2 and "--operand requires canonical --action" in operand_without_action[2],
    }


def _projection_metrics() -> dict[str, Any]:
    rows = action_projection_rows()
    runtime_gui = gui_runtime_action_contracts()
    serialized = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    widget_source = (ROOT / "gui/zap2_gui/widgets/runtime_controls.py").read_text(encoding="utf-8")
    return {
        "rowCount": len(rows),
        "uniqueActionIds": len({row["actionId"] for row in rows}),
        "catalogMatchesProjection": {row["actionId"] for row in rows} == set(ACTION_CONTRACT_BY_ID),
        "projectionSha256": hashlib.sha256(serialized.encode()).hexdigest(),
        "runtimeGuiProjectedIds": [contract.action_id for contract in runtime_gui],
        "runtimeWidgetConsumesContracts": all(
            f'action_contract("{action_id}")' in widget_source
            for action_id in ("default.workflow.start", "default.workflow.status", "default.workflow.stop")
        ),
    }


def collect_evidence() -> dict[str, Any]:
    main_selectors = _selector_attrs("main")
    compat_selectors = _selector_attrs("dispatch_legacy_compat")
    contract_handler_ids = {contract.handler_id for contract in ACTION_CONTRACT_BY_ID.values() if contract.handler_id}
    return {
        "schemaVersion": 1,
        "patch": "P04d",
        "parentP04cEvidenceSha256": _sha256(P04C_EVIDENCE),
        "inputSha256": {relative: _sha256(ROOT / relative) for relative in INPUTS},
        "legacyCompatibilityGrammar": {
            "selectorCount": len(LEGACY_SELECTOR_DESTS),
            "migratedSelectorCount": len(migrated_legacy_selectors()),
            "remainingLegacyOnlySelectorCount": len(remaining_legacy_only_selectors()),
            "mainLegacySelectorBranchCount": len(main_selectors),
            "compatibilityBodySelectorCount": len(compat_selectors),
            "compatibilityInventoryMatches": compat_selectors == LEGACY_SELECTOR_DESTS,
        },
        "actionContracts": {
            "contractCount": len(action_contract_ids()),
            "handlerCount": len(ACTION_HANDLERS),
            "generatedContractCount": len(GENERATED_LEGACY_ACTION_BINDINGS),
            "catalogValid": not validation_errors(),
            "dispatcherClosed": not dispatcher_validation_errors(),
            "handlerIdsMatchContracts": set(ACTION_HANDLERS) == contract_handler_ids,
        },
        "parser": _parser_metrics(),
        "generatedMetadata": _generator_metrics(),
        "roundtrip": _roundtrip_metrics(),
        "executionParity": _execution_parity_metrics(),
        "contradictionGate": _contradiction_metrics(),
        "projection": _projection_metrics(),
        "assumptionsDelta": {
            "confirmed": [
                "all 117 historical top-level action selectors resolve to canonical ActionContracts before execution",
                "main() no longer contains first-match legacy action dispatch",
                "119 canonical actions are closed over 119 executable dispatcher handlers",
                "generated compatibility metadata is reproducible from the frozen parser surface",
                "canonical and legacy action forms roundtrip across every contract and representative execution outputs are identical",
            ],
            "stillOpen": [
                "full S-INSTALL package-data bundling and writable-state separation remain unresolved",
                "P05 may build richer search/help UX on the now-stable ActionContract projection",
                "owner acceptance is still required before promoting the RC4 candidate to accepted v0.8",
            ],
        },
        "recompiledDag": [
            "P04d accepted -> RC4 ActionContract closure complete / v0.8 candidate eligible for promotion",
            "accepted RC4/v0.8 -> P05 search/help/capability projection work",
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
        print(f"P04d baseline written: {BASELINE_PATH}")
        return 0
    if not BASELINE_PATH.is_file():
        print(f"P04d ActionContract closure: FAIL — missing baseline {BASELINE_PATH}", file=sys.stderr)
        return 2
    expected = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    errors = _diff(expected, actual)
    if errors:
        print("P04d ActionContract closure: FAIL", file=sys.stderr)
        for item in errors[:100]:
            print(f"  - {item}", file=sys.stderr)
        if len(errors) > 100:
            print(f"  - ... {len(errors) - 100} more", file=sys.stderr)
        return 1
    print("P04d ActionContract closure: PASS")
    print(f"legacy selectors contract-backed: {actual['legacyCompatibilityGrammar']['migratedSelectorCount']}/{actual['legacyCompatibilityGrammar']['selectorCount']}")
    print(f"canonical actions / handlers: {actual['actionContracts']['contractCount']}/{actual['actionContracts']['handlerCount']}")
    print(f"roundtrip cases: {actual['roundtrip']['roundtripCaseCount']}")
    print("live checkout mutations: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
