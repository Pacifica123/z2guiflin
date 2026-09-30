#!/usr/bin/env python3
"""P04b resource-location / immutable Plan / compatibility-migration gate.

The checker is read-only with respect to the live checkout. Mutation experiments
run only in temporary project copies. Expected evidence is frozen in
``runtime/p04/p04b-frozen-evidence.json``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gui"))

from zap2_gui.adapters.execution_plan import (  # noqa: E402
    materialize_execution_plan,
    materialize_execution_plan_from_args,
)
from zap2_gui.adapters.runtime_plan_generator import create_runtime_plan  # noqa: E402
from zap2_gui.adapters.runtime_state import generated_runtime_plan_to_payload  # noqa: E402
from zap2_gui.adapters.workspace_profiles import (  # noqa: E402
    load_strategy_catalog,
    load_workspace_catalog,
)
from zap2_gui.project_paths import (  # noqa: E402
    RESOURCE_ROOT_ENV,
    discover_resource_location,
)

BASELINE_PATH = ROOT / "runtime/p04/p04b-frozen-evidence.json"
P04A_EVIDENCE = ROOT / "runtime/p04/p04a-frozen-evidence.json"
INPUTS = (
    "gui/zap2_gui/project_paths.py",
    "gui/zap2_gui/models/execution_plan.py",
    "gui/zap2_gui/models/strategy.py",
    "gui/zap2_gui/models/runtime_plan.py",
    "gui/zap2_gui/adapters/execution_plan.py",
    "gui/zap2_gui/adapters/workspace_profiles.py",
    "gui/zap2_gui/adapters/runtime_plan_generator.py",
    "gui/zap2_gui/adapters/runtime_state.py",
    "gui/zap2_gui/adapters/runtime_artifacts.py",
    "gui/zap2_gui/adapters/runtime_session.py",
    "gui/zap2_gui/adapters/runtime_apply.py",
    "pyproject.toml",
)
COPY_IGNORE = shutil.ignore_patterns(
    ".git",
    ".zap2",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "*.pyc",
    "*.pyo",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_project(target: Path) -> Path:
    shutil.copytree(ROOT, target, ignore=COPY_IGNORE)
    return target


def _raw_strategy_json() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted((ROOT / "strategies").glob("*.json")):
        if path.name == "catalog.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        result[str(data["id"])] = data
    return result


def _representation_metrics() -> dict[str, Any]:
    catalog = load_workspace_catalog(ROOT)
    context = catalog.runtime_context_by_id()["default"]
    strategies = load_strategy_catalog(ROOT)
    raw = _raw_strategy_json()
    matching_legacy = 0
    legacy_fields = 0
    failures: list[str] = []
    for preset in strategies.strategies:
        data = raw[preset.preset_id]
        legacy = tuple(str(item) for item in data.get("runtimeArgs", []))
        if "runtimeArgs" in data:
            legacy_fields += 1
        if not legacy:
            continue
        canonical = materialize_execution_plan_from_args(
            root=ROOT,
            runtime_context=context,
            preset=preset,
            runtime_args=preset.runtime_args,
            source_kind="presetPath",
            source_path=preset.preset_path,
        ).plan
        compatibility = materialize_execution_plan_from_args(
            root=ROOT,
            runtime_context=context,
            preset=preset,
            runtime_args=legacy,
            source_kind="legacy-runtimeArgs",
        ).plan
        if canonical.plan_hash == compatibility.plan_hash:
            matching_legacy += 1
        else:
            failures.append(preset.preset_id)

    with tempfile.TemporaryDirectory(prefix="zap2-p04b-drift-") as temp:
        project = _copy_project(Path(temp) / "project")
        before = materialize_execution_plan(project, "default").plan.plan_hash
        path = project / "strategies/manual-local.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["runtimeArgs"] = ["--filter-tcp=1", "--lua-desync=send"]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        loaded = load_strategy_catalog(project).by_id()["manual-local"]
        after_materialization = materialize_execution_plan(project, "default")
        drift_ignored = (
            before == after_materialization.plan.plan_hash
            and bool(loaded.compatibility_warnings)
            and bool(after_materialization.compatibility_warnings)
        )

    return {
        "strategyCount": len(strategies.strategies),
        "presetPathCount": sum(bool(item.preset_path) for item in strategies.strategies),
        "legacyRuntimeArgsFieldCount": legacy_fields,
        "legacyProjectionHashMatches": matching_legacy,
        "legacyProjectionFailures": failures,
        "legacyDriftCannotChangePlan": drift_ignored,
        "authority": "presetPath -> normalized immutable Plan; runtimeArgs is compatibility-only metadata when presetPath exists",
    }


def _resource_metrics() -> dict[str, Any]:
    default_location = discover_resource_location()
    explicit_location = discover_resource_location(ROOT)
    env_location = discover_resource_location(environ={RESOURCE_ROOT_ENV: str(ROOT)})
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package_data_declared = "[tool.setuptools.package-data]" in pyproject or "include-package-data" in pyproject
    return {
        "defaultOrigin": default_location.origin,
        "explicitOrigin": explicit_location.origin,
        "environmentOrigin": env_location.origin,
        "allResolveSameRoot": len({default_location.root, explicit_location.root, env_location.root}) == 1,
        "environmentContract": RESOURCE_ROOT_ENV,
        "externalResourceRootContractReady": env_location.outside_checkout_contract,
        "projectResourcePackageDataDeclared": package_data_declared,
        "fullInstalledBundleReady": package_data_declared,
        "writableStateSeparated": False,
        "decision": "P04b establishes an explicit resource-root contract but does not claim final S-INSTALL packaging/state separation",
    }


def _plan_metrics() -> dict[str, Any]:
    default = materialize_execution_plan(ROOT, "default")
    runtime_plan = create_runtime_plan(ROOT, "start", "default")
    payload = generated_runtime_plan_to_payload(runtime_plan, ROOT)
    normalized = payload.get("normalizedExecutionPlan", {})

    with tempfile.TemporaryDirectory(prefix="zap2-p04b-relocate-") as temp:
        base = Path(temp)
        first = _copy_project(base / "first")
        second = _copy_project(base / "second")
        first_plan = materialize_execution_plan(first, "default").plan
        second_plan = materialize_execution_plan(second, "default").plan
        relocation_stable = first_plan.to_payload() == second_plan.to_payload() and first_plan.plan_hash == second_plan.plan_hash

    return {
        "defaultPlanHash": default.plan.plan_hash,
        "defaultRuntimeArgCount": len(default.plan.runtime_args),
        "defaultResourceCount": len(default.plan.resources),
        "defaultResourcesReady": default.plan.resources_ready,
        "locationIndependent": relocation_stable,
        "runtimePlanEmbedsNormalizedPlan": normalized.get("planHash") == runtime_plan.execution_plan.plan_hash,
        "runtimeArgProjectionMatchesPlan": payload.get("strategyRuntimeArgs") == normalized.get("runtimeArgs"),
        "canonicalIdsEmbedded": (
            payload.get("runtimeContextId") == payload.get("profileId") == "default"
            and payload.get("presetId") == payload.get("strategyId") == "manual-local"
        ),
    }


def _alias_metrics() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="zap2-p04b-alias-") as temp:
        project = _copy_project(Path(temp) / "project")
        selection = project / ".zap2/strategies/default.active-strategy.json"
        selection.parent.mkdir(parents=True, exist_ok=True)
        common = {
            "schemaVersion": 1,
            "selectedAt": "2026-09-30T00:00:00Z",
            "reason": "p04b-check",
        }
        legacy = {
            **common,
            "profileId": "default",
            "strategyId": "reference-zapret2-generic-tls-fake",
            "previousStrategyId": "manual-local",
        }
        selection.write_text(json.dumps(legacy), encoding="utf-8")
        legacy_hash = materialize_execution_plan(project, "default").plan.plan_hash
        canonical = {
            **common,
            "runtimeContextId": "default",
            "presetId": "reference-zapret2-generic-tls-fake",
            "previousPresetId": "manual-local",
        }
        selection.write_text(json.dumps(canonical), encoding="utf-8")
        canonical_hash = materialize_execution_plan(project, "default").plan.plan_hash

        conflict = {
            **common,
            "runtimeContextId": "default",
            "profileId": "other",
            "presetId": "manual-local",
            "strategyId": "manual-local",
        }
        selection.write_text(json.dumps(conflict), encoding="utf-8")
        conflict_rejected = False
        try:
            load_workspace_catalog(project)
        except ValueError as exc:
            conflict_rejected = "Conflicting compatibility fields" in str(exc)

    return {
        "legacyAndCanonicalSelectionSamePlanHash": legacy_hash == canonical_hash,
        "conflictingAliasesRejected": conflict_rejected,
        "writerPolicy": "new state writes canonical and legacy aliases with equal values; readers accept either and reject disagreement",
    }


def collect_evidence() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "patch": "P04b",
        "parentP04aEvidenceSha256": _sha256(P04A_EVIDENCE),
        "inputSha256": {relative: _sha256(ROOT / relative) for relative in INPUTS},
        "resourceLocation": _resource_metrics(),
        "representation": _representation_metrics(),
        "normalizedPlan": _plan_metrics(),
        "compatibilityAliases": _alias_metrics(),
        "assumptionsDelta": {
            "confirmed": [
                "resource resolution now has explicit provenance and an external-root contract",
                "equivalent source/legacy projections materialize the same location-independent immutable Plan",
                "legacy runtimeArgs drift cannot alter execution when presetPath exists",
                "runtimeContext/preset aliases preserve Plan hash and conflicting aliases fail closed",
            ],
            "stillOpen": [
                "normal site-packages install does not yet bundle all project resources",
                "writable .zap2 state is not yet separated from the resource tree",
                "legacy CLI contradiction gate and ActionContract dispatcher remain P04c",
            ],
        },
        "recompiledDag": [
            "P04b accepted -> P04c executable ActionContract dispatcher + legacy CLI translator/conflict gate + GUI projection",
            "P04c -> P04d migration/coverage/lint/roundtrip acceptance",
            "P04d -> RC4/v0.8 candidate",
            "P05 waits for P04d",
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
    if not BASELINE_PATH.is_file():
        print(f"P04b execution Plan: FAIL — missing baseline {BASELINE_PATH}", file=sys.stderr)
        return 2
    expected = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    errors = _diff(expected, actual)
    if errors:
        print("P04b execution Plan: FAIL", file=sys.stderr)
        for item in errors[:80]:
            print(f"  - {item}", file=sys.stderr)
        if len(errors) > 80:
            print(f"  - ... {len(errors) - 80} more", file=sys.stderr)
        return 1
    print("P04b execution Plan: PASS")
    print(f"normalized plan hash: {actual['normalizedPlan']['defaultPlanHash']}")
    print(f"shipping presets: {actual['representation']['strategyCount']}")
    print(f"legacy projection hash matches: {actual['representation']['legacyProjectionHashMatches']}")
    print("live checkout mutations: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
