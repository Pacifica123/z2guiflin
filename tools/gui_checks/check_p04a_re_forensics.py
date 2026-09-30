#!/usr/bin/env python3
"""P04a frozen re-forensics / decision-experiment gate.

No handler is executed.  The gate measures three P04 dependencies against the
post-P03f tree: representation fidelity, legacy CLI ambiguity and S-INSTALL
outside-checkout resource assumptions.  Expected evidence is frozen in
runtime/p04/p04a-frozen-evidence.json so later implementation cannot silently
rewrite the criteria that justified it.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gui"))

from zap2_gui.app import build_parser  # noqa: E402
from zap2_gui.adapters.workspace_profiles import load_strategy_catalog  # noqa: E402
from zap2_gui.models.preset import parse_preset_args  # noqa: E402

BASELINE_PATH = ROOT / "runtime/p04/p04a-frozen-evidence.json"
INPUTS = (
    "gui/zap2_gui/app.py",
    "gui/zap2_gui/adapters/workspace_profiles.py",
    "gui/zap2_gui/models/preset.py",
    "gui/zap2_gui/project_paths.py",
    "pyproject.toml",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _arg_attrs(expr: ast.AST) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(expr):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "args"
        ):
            result.add(node.attr)
    return result


def _app_ast_metrics() -> dict[str, Any]:
    path = ROOT / "gui/zap2_gui/app.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    build = functions["build_parser"]
    main = functions["main"]

    add_argument_calls = 0
    option_strings: list[str] = []
    for node in ast.walk(build):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
            names = [
                arg.value
                for arg in node.args
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("-")
            ]
            if names:
                add_argument_calls += 1
                option_strings.extend(names)

    top_level_dispatch: list[tuple[int, tuple[str, ...]]] = []
    for node in main.body:
        if isinstance(node, ast.If):
            attrs = tuple(sorted(_arg_attrs(node.test)))
            if attrs:
                top_level_dispatch.append((node.lineno, attrs))
    selector_destinations = sorted({item for _, attrs in top_level_dispatch for item in attrs})

    parser = build_parser()
    contradiction_accepted = True
    contradiction_error = ""
    try:
        parsed = parser.parse_args(["--runtime-plan", "status", "--default-status"])
        contradiction_values = {
            "runtime_plan": getattr(parsed, "runtime_plan", None),
            "default_status": bool(getattr(parsed, "default_status", False)),
        }
    except SystemExit as exc:  # argparse rejects the conflict only if grammar changes.
        contradiction_accepted = False
        contradiction_error = f"SystemExit({exc.code})"
        contradiction_values = {}

    branch_lines: dict[str, int] = {}
    for line, attrs in top_level_dispatch:
        for attr in attrs:
            branch_lines.setdefault(attr, line)

    return {
        "addArgumentCalls": add_argument_calls,
        "optionStringCount": len(option_strings),
        "topLevelDispatchBranches": len(top_level_dispatch),
        "selectorDestinationCount": len(selector_destinations),
        "representativeContradiction": {
            "argv": ["--runtime-plan", "status", "--default-status"],
            "acceptedByArgparse": contradiction_accepted,
            "parsedValues": contradiction_values,
            "parseError": contradiction_error,
            "runtimePlanBranchLine": branch_lines.get("runtime_plan"),
            "defaultStatusBranchLine": branch_lines.get("default_status"),
            "firstMatchDispatchWouldPrefer": (
                "runtime_plan"
                if branch_lines.get("runtime_plan", 10**9) < branch_lines.get("default_status", 10**9)
                else "default_status"
            ),
        },
        "decision": "explicit contradiction validation is required before any legacy handler; canonical typed CLI shape remains evidence-driven",
    }


def _representation_metrics() -> dict[str, Any]:
    catalog = load_strategy_catalog(ROOT)
    exact = 0
    duplicates = 0
    comments = 0
    preset_paths = 0
    failures: list[str] = []
    for strategy in catalog.strategies:
        if not strategy.preset_path:
            failures.append(f"{strategy.strategy_id}: missing presetPath")
            continue
        preset_paths += 1
        path = ROOT / strategy.preset_path
        raw_lines = path.read_text(encoding="utf-8").splitlines()
        comments += sum(1 for line in raw_lines if line.lstrip().startswith("#"))
        argv = tuple(line.strip() for line in raw_lines if line.strip() and not line.lstrip().startswith("#"))
        parsed = parse_preset_args(
            argv,
            preset_id=strategy.strategy_id,
            title=strategy.title,
            source_path=strategy.preset_path,
        )
        if parsed.to_runtime_args() == strategy.runtime_args == argv:
            exact += 1
        else:
            failures.append(f"{strategy.strategy_id}: source->norm->render mismatch")
        raw_json = json.loads((ROOT / "strategies" / f"{strategy.strategy_id}.json").read_text(encoding="utf-8"))
        if raw_json.get("presetPath") and "runtimeArgs" in raw_json:
            duplicates += 1

    return {
        "strategyCount": len(catalog.strategies),
        "presetPathCount": preset_paths,
        "exactExecutionRoundTrips": exact,
        "strategyJsonWithPresetPathAndRuntimeArgs": duplicates,
        "commentLinesNotInExecutionArgv": comments,
        "failures": failures,
        "classification": {
            "comments": "information-loss only under current execution materializer",
            "order": "execution-significant and preserved exactly",
            "runtimeArgsDuplicate": "duplicate execution representation guarded by equality today; cannot remain an independent authority in final P04",
        },
        "decision": "preserve many authoring/import forms, but materialize one immutable execution Plan; canonical authoring format remains unresolved by P04a",
    }


def _install_metrics() -> dict[str, Any]:
    project_paths = ROOT / "gui/zap2_gui/project_paths.py"
    text = project_paths.read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    repository_relative_rule = "Path(__file__).resolve().parents[2]" in text
    explicit_package_data = "[tool.setuptools.package-data]" in pyproject or "include-package-data" in pyproject

    # Model the current default rule after a normal site-packages install: the
    # module lives below site-packages/zap2_gui, so parents[2] is an installation
    # prefix, not this repository.  Current pyproject installs only Python packages
    # from gui/ and declares no project resource bundle.
    outside_checkout_ready = not repository_relative_rule and explicit_package_data
    return {
        "defaultLayoutIsRepositoryRelative": repository_relative_rule,
        "projectResourcePackageDataDeclared": explicit_package_data,
        "outsideCheckoutDefaultLayoutReady": outside_checkout_ready,
        "decision": "S-INSTALL falsifies repository-relative resource discovery; resource-location/install contract must be resolved before P04 freezes Plan/ActionContract projections",
    }


def collect_evidence() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "patch": "P04a",
        "inputSha256": {relative: _sha256(ROOT / relative) for relative in INPUTS},
        "representation": _representation_metrics(),
        "cli": _app_ast_metrics(),
        "sInstall": _install_metrics(),
        "assumptionsDelta": {
            "confirmed": [
                "P03 target-core semantics are present in the current tree",
                "preset execution order round-trips exactly across the shipping corpus",
            ],
            "falsified": [
                "outside-checkout resource discovery is not established",
                "legacy argparse grammar does not reject representative contradictory action selectors",
            ],
            "deferred": [
                "TXT vs structured authoring authority",
                "typed subcommands vs compatibility grammar as the canonical CLI surface",
            ],
        },
        "recompiledDag": [
            "P04a: freeze post-P03f evidence + v0.7 sync + ontology/contract foundation",
            "P04b: resource-location contract + normalized immutable Plan materializer + runtimeContext/preset aliases",
            "P04c: executable ActionContract dispatcher + legacy CLI translator/conflict gate + GUI projection",
            "P04d: migration/coverage/lint/roundtrip acceptance -> v0.8 candidate",
            "P05 waits for P04d",
        ],
    }


def _diff(expected: Any, actual: Any, prefix: str = "") -> list[str]:
    errors: list[str] = []
    if type(expected) is not type(actual):
        return [f"{prefix or '<root>'}: type {type(actual).__name__} != {type(expected).__name__}"]
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            here = f"{prefix}.{key}" if prefix else key
            if key not in expected:
                errors.append(f"{here}: unexpected")
            elif key not in actual:
                errors.append(f"{here}: missing")
            else:
                errors.extend(_diff(expected[key], actual[key], here))
    elif isinstance(expected, list):
        if expected != actual:
            errors.append(f"{prefix}: {actual!r} != {expected!r}")
    elif expected != actual:
        errors.append(f"{prefix}: {actual!r} != {expected!r}")
    return errors


def main() -> int:
    actual = collect_evidence()
    if not BASELINE_PATH.is_file():
        print("P04a re-forensics: FAIL")
        print(f"- frozen evidence missing: {BASELINE_PATH.relative_to(ROOT)}")
        return 1
    expected = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    errors = _diff(expected, actual)
    if errors:
        print("P04a re-forensics: FAIL")
        print("- frozen evidence changed; semantic amendment/re-forensics required before changing acceptance criteria")
        for error in errors[:30]:
            print(f"- {error}")
        if len(errors) > 30:
            print(f"- ... {len(errors) - 30} more")
        return 1

    rep = actual["representation"]
    cli = actual["cli"]
    sinstall = actual["sInstall"]
    print("P04a re-forensics: PASS")
    print(f"REP corpus: {rep['exactExecutionRoundTrips']}/{rep['strategyCount']} exact execution round-trips")
    print(f"REP duplicate guarded representations: {rep['strategyJsonWithPresetPathAndRuntimeArgs']}")
    print(f"CLI: {cli['optionStringCount']} option strings; {cli['selectorDestinationCount']} top-level selector destinations")
    print(f"CLI representative contradiction accepted: {'yes' if cli['representativeContradiction']['acceptedByArgparse'] else 'no'}")
    print(f"S-INSTALL outside-checkout default layout ready: {'yes' if sinstall['outsideCheckoutDefaultLayoutReady'] else 'no'}")
    print("criteria frozen: runtime/p04/p04a-frozen-evidence.json")
    print("mutates runtime/network/system: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
