from __future__ import annotations

import argparse

import pytest

from zap2_gui.app import build_parser, main
from zap2_gui.adapters.action_dispatcher import ACTION_HANDLERS, dispatcher_validation_errors
from zap2_gui.adapters.legacy_cli import (
    LEGACY_SELECTOR_DESTS,
    migrated_legacy_selectors,
    remaining_legacy_only_selectors,
    resolve_cli_action,
)
from zap2_gui.models.action_bindings import GENERATED_LEGACY_ACTION_BINDINGS
from zap2_gui.models.action_catalog import (
    ACTION_CONTRACT_BY_ID,
    action_contract_ids,
    action_projection_rows,
    gui_runtime_action_contracts,
    validation_errors,
)


def _parse(*argv: str) -> argparse.Namespace:
    return build_parser().parse_args(list(argv))


def test_p04d_contract_catalog_and_dispatcher_are_closed() -> None:
    assert len(action_contract_ids()) == 119
    assert len(ACTION_HANDLERS) == 119
    assert not validation_errors()
    assert not dispatcher_validation_errors()
    assert set(ACTION_HANDLERS) == {contract.handler_id for contract in ACTION_CONTRACT_BY_ID.values()}


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


def test_contradictory_legacy_selectors_fail_before_dispatch() -> None:
    with pytest.raises(ValueError, match="Contradictory action selectors"):
        resolve_cli_action(_parse("--runtime-plan", "status", "--default-status"))
    with pytest.raises(ValueError, match="Contradictory action selectors"):
        resolve_cli_action(_parse("--list-presets", "--list-strategies"))


def test_canonical_plus_legacy_selector_is_rejected_even_if_equivalent() -> None:
    with pytest.raises(ValueError, match="Contradictory action selectors"):
        resolve_cli_action(_parse("--action", "default.workflow.status", "--default-status"))


def test_operand_requires_canonical_action() -> None:
    with pytest.raises(ValueError, match="--operand requires canonical --action"):
        resolve_cli_action(_parse("--operand", "manual-local"))


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


def test_p04d_generated_zero_operand_action_has_execution_parity(capsys: pytest.CaptureFixture[str]) -> None:
    legacy_rc = main(["--list-presets"])
    legacy = capsys.readouterr()
    canonical_rc = main(["--action", "preset.list"])
    canonical = capsys.readouterr()
    assert legacy_rc == canonical_rc == 0
    assert legacy.err == canonical.err == ""
    assert legacy.out == canonical.out


def test_p04d_generated_operand_action_has_execution_parity(capsys: pytest.CaptureFixture[str]) -> None:
    legacy_rc = main(["--show-preset", "manual-local"])
    legacy = capsys.readouterr()
    canonical_rc = main(["--action", "preset.show", "--operand", "manual-local"])
    canonical = capsys.readouterr()
    assert legacy_rc == canonical_rc == 0
    assert legacy.err == canonical.err == ""
    assert legacy.out == canonical.out


def test_canonical_operand_arity_fails_closed(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--action", "preset.show"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "requires 1 operand" in captured.err


def test_gui_projection_comes_from_same_contract_catalog() -> None:
    projected = gui_runtime_action_contracts()
    assert tuple(contract.action_id for contract in projected) == (
        "default.workflow.start",
        "default.workflow.status",
        "default.workflow.stop",
    )
    assert all(contract in ACTION_CONTRACT_BY_ID.values() for contract in projected)
    rows = action_projection_rows()
    assert len(rows) == len(ACTION_CONTRACT_BY_ID)
    assert {row["actionId"] for row in rows} == set(ACTION_CONTRACT_BY_ID)


def test_all_historical_selectors_are_contract_backed() -> None:
    assert len(LEGACY_SELECTOR_DESTS) == 117
    assert len(set(LEGACY_SELECTOR_DESTS)) == len(LEGACY_SELECTOR_DESTS)
    assert set(migrated_legacy_selectors()) == set(LEGACY_SELECTOR_DESTS)
    assert remaining_legacy_only_selectors() == ()
    assert len(GENERATED_LEGACY_ACTION_BINDINGS) == 91
