from __future__ import annotations

import argparse

import pytest

from zap2_gui.app import build_parser, main
from zap2_gui.adapters.action_dispatcher import dispatcher_validation_errors
from zap2_gui.adapters.legacy_cli import (
    LEGACY_SELECTOR_DESTS,
    STATIC_MIGRATED_SELECTOR_MAP,
    migrated_legacy_selectors,
    resolve_cli_action,
)
from zap2_gui.models.action_catalog import (
    ACTION_CONTRACT_BY_ID,
    action_contract_ids,
    gui_runtime_action_contracts,
    validation_errors,
)


def _parse(*argv: str) -> argparse.Namespace:
    return build_parser().parse_args(list(argv))


def test_p04c_contract_catalog_and_dispatcher_are_closed() -> None:
    assert len(action_contract_ids()) == 28
    assert not validation_errors()
    assert not dispatcher_validation_errors()
    assert set(STATIC_MIGRATED_SELECTOR_MAP.values()) <= set(ACTION_CONTRACT_BY_ID)


def test_legacy_runtime_plan_translates_to_same_contract() -> None:
    resolution = resolve_cli_action(_parse("--runtime-plan", "status"))
    assert resolution.canonical_action_id == "runtime.plan.status"
    assert resolution.legacy_selector == "runtime_plan"
    assert resolution.migrated is True


def test_canonical_action_selector_resolves_without_legacy_alias() -> None:
    resolution = resolve_cli_action(_parse("--action", "default.workflow.status"))
    assert resolution.canonical_action_id == "default.workflow.status"
    assert resolution.legacy_selector is None
    assert resolution.active_selectors == ("action",)


def test_contradictory_migrated_legacy_selectors_fail_before_dispatch() -> None:
    with pytest.raises(ValueError, match="Contradictory action selectors"):
        resolve_cli_action(_parse("--runtime-plan", "status", "--default-status"))


def test_contradictory_unmigrated_legacy_selectors_also_fail() -> None:
    with pytest.raises(ValueError, match="Contradictory action selectors"):
        resolve_cli_action(_parse("--list-presets", "--list-strategies"))


def test_canonical_plus_legacy_selector_is_rejected_even_if_equivalent() -> None:
    with pytest.raises(ValueError, match="Contradictory action selectors"):
        resolve_cli_action(_parse("--action", "default.workflow.status", "--default-status"))


def test_cli_conflict_returns_two_without_running_a_handler(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--default-start", "--default-stop"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "Contradictory action selectors" in captured.err
    assert captured.out == ""


def test_canonical_and_legacy_runtime_plan_have_identical_output(capsys: pytest.CaptureFixture[str]) -> None:
    canonical_rc = main(["--action", "runtime.plan.status", "--profile", "default"])
    canonical = capsys.readouterr()
    legacy_rc = main(["--runtime-plan", "status", "--profile", "default"])
    legacy = capsys.readouterr()
    assert canonical_rc == legacy_rc == 0
    assert canonical.err == legacy.err == ""
    assert canonical.out == legacy.out
    assert "normalized execution plan:" in canonical.out


def test_single_unmigrated_selector_remains_legacy_compatible(capsys: pytest.CaptureFixture[str]) -> None:
    resolution = resolve_cli_action(_parse("--list-presets"))
    assert resolution.legacy_only is True
    assert resolution.canonical_action_id is None
    rc = main(["--list-presets"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err == ""
    assert captured.out.strip()


def test_gui_projection_comes_from_same_contract_catalog() -> None:
    projected = gui_runtime_action_contracts()
    assert tuple(contract.action_id for contract in projected) == (
        "default.workflow.start",
        "default.workflow.status",
        "default.workflow.stop",
    )
    assert all(contract in ACTION_CONTRACT_BY_ID.values() for contract in projected)


def test_global_legacy_selector_inventory_is_unique_and_has_migrated_subset() -> None:
    assert len(LEGACY_SELECTOR_DESTS) == 117
    assert len(set(LEGACY_SELECTOR_DESTS)) == len(LEGACY_SELECTOR_DESTS)
    assert set(migrated_legacy_selectors()) <= set(LEGACY_SELECTOR_DESTS)
