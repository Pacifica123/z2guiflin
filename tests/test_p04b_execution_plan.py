from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from zap2_gui.adapters.execution_plan import (
    materialize_execution_plan,
    materialize_execution_plan_from_args,
)
from zap2_gui.adapters.runtime_plan_generator import create_runtime_plan
from zap2_gui.adapters.runtime_state import generated_runtime_plan_to_payload
from zap2_gui.adapters.workspace_profiles import (
    load_strategy_catalog,
    load_workspace_catalog,
    select_workspace_preset,
)
from zap2_gui.project_paths import (
    RESOURCE_ROOT_ENV,
    ResourceLocationError,
    discover_layout,
    discover_resource_location,
    normalize_resource_relative_path,
)

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path, name: str = "project") -> Path:
    target = tmp_path / name
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", ".pytest_cache", "*.pyc"),
    )
    return target


def test_resource_location_is_explicit_and_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    explicit = discover_resource_location(ROOT)
    assert explicit.root == ROOT.resolve()
    assert explicit.origin == "explicit"
    assert explicit.outside_checkout_contract is True

    monkeypatch.setenv(RESOURCE_ROOT_ENV, str(ROOT))
    env_location = discover_resource_location(environ={RESOURCE_ROOT_ENV: str(ROOT)})
    assert env_location.root == ROOT.resolve()
    assert env_location.origin == "environment"
    assert discover_layout().root == ROOT.resolve()

    with pytest.raises(ValueError, match="leaves"):
        normalize_resource_relative_path("../escape")
    with pytest.raises(ResourceLocationError):
        discover_resource_location(environ={RESOURCE_ROOT_ENV: str(tmp_path / "missing")})


def test_plan_hash_is_location_independent(tmp_path: Path) -> None:
    first = _copy_project(tmp_path, "first")
    second = _copy_project(tmp_path, "second")
    first_plan = materialize_execution_plan(first, "default").plan
    second_plan = materialize_execution_plan(second, "default").plan
    assert first_plan.plan_hash == second_plan.plan_hash
    assert first_plan.to_payload() == second_plan.to_payload()
    assert str(first) not in json.dumps(first_plan.to_payload())
    assert str(second) not in json.dumps(second_plan.to_payload())


def test_all_shipping_presets_materialize_same_plan_from_legacy_projection() -> None:
    catalog = load_workspace_catalog(ROOT)
    context = catalog.runtime_context_by_id()["default"]
    strategies = load_strategy_catalog(ROOT)
    raw_catalog = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in (ROOT / "strategies").glob("*.json")
        if path.name != "catalog.json"
    }

    compared = 0
    for preset in strategies.strategies:
        legacy = tuple(str(item) for item in raw_catalog[preset.preset_id].get("runtimeArgs", []))
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
        assert compatibility.plan_hash == canonical.plan_hash
        compared += 1
    assert compared == 17


def test_legacy_runtime_args_drift_cannot_change_execution_plan(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    baseline = materialize_execution_plan(project, "default").plan
    strategy_path = project / "strategies" / "manual-local.json"
    data = json.loads(strategy_path.read_text(encoding="utf-8"))
    data["runtimeArgs"] = ["--filter-tcp=1", "--lua-desync=send"]
    strategy_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    catalog = load_strategy_catalog(project)
    manual = catalog.by_id()["manual-local"]
    assert manual.runtime_args == baseline.runtime_args
    assert manual.compatibility_warnings
    after = materialize_execution_plan(project, "default")
    assert after.plan.plan_hash == baseline.plan_hash
    assert after.compatibility_warnings


def test_runtime_context_preset_state_aliases_materialize_same_plan(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    selection_path = project / ".zap2" / "strategies" / "default.active-strategy.json"
    selection_path.parent.mkdir(parents=True, exist_ok=True)

    legacy = {
        "schemaVersion": 1,
        "profileId": "default",
        "strategyId": "reference-zapret2-generic-tls-fake",
        "previousStrategyId": "manual-local",
        "selectedAt": "2026-09-30T00:00:00Z",
        "reason": "test",
    }
    selection_path.write_text(json.dumps(legacy), encoding="utf-8")
    legacy_hash = materialize_execution_plan(project, "default").plan.plan_hash

    canonical = {
        "schemaVersion": 1,
        "runtimeContextId": "default",
        "presetId": "reference-zapret2-generic-tls-fake",
        "previousPresetId": "manual-local",
        "selectedAt": "2026-09-30T00:00:00Z",
        "reason": "test",
    }
    selection_path.write_text(json.dumps(canonical), encoding="utf-8")
    canonical_hash = materialize_execution_plan(project, "default").plan.plan_hash
    assert legacy_hash == canonical_hash

    result = select_workspace_preset(project, "manual-local", "default", "test")
    stored = json.loads(result.path.read_text(encoding="utf-8"))
    assert stored["runtimeContextId"] == stored["profileId"] == "default"
    assert stored["presetId"] == stored["strategyId"] == "manual-local"


def test_conflicting_legacy_and_canonical_selection_fails_closed(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    path = project / ".zap2" / "strategies" / "default.active-strategy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "runtimeContextId": "default",
                "profileId": "other",
                "presetId": "manual-local",
                "strategyId": "manual-local",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Conflicting compatibility fields"):
        load_workspace_catalog(project)


def test_runtime_plan_payload_embeds_canonical_execution_plan() -> None:
    plan = create_runtime_plan(ROOT, "start", "default")
    payload = generated_runtime_plan_to_payload(plan, ROOT)
    normalized = payload["normalizedExecutionPlan"]
    assert payload["runtimeContextId"] == payload["profileId"] == "default"
    assert payload["presetId"] == payload["strategyId"] == "manual-local"
    assert normalized["planHash"] == plan.execution_plan.plan_hash
    assert tuple(normalized["runtimeArgs"]) == plan.execution_plan.runtime_args
    assert payload["strategyRuntimeArgs"] == normalized["runtimeArgs"]
