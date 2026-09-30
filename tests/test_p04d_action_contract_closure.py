from __future__ import annotations

import ast
from pathlib import Path

from zap2_gui.app import build_parser
from zap2_gui.adapters.action_dispatcher import _materialize_compat_selector
from zap2_gui.adapters.legacy_cli import (
    LEGACY_SELECTOR_DESTS,
    STATIC_MIGRATED_SELECTOR_MAP,
    active_legacy_selectors,
    migrated_legacy_selectors,
    remaining_legacy_only_selectors,
    resolve_cli_action,
)
from zap2_gui.models.action_bindings import GENERATED_LEGACY_ACTION_BINDINGS
from zap2_gui.models.action_catalog import ACTION_CONTRACT_BY_ID, action_contract_ids, action_projection_rows

ROOT = Path(__file__).resolve().parents[1]


def _sample_operands(binding) -> list[str]:
    if binding.operand_arity == 0:
        return []
    if binding.choices:
        return [binding.choices[0] for _ in range(binding.operand_arity)]
    return [f"sample-{index + 1}" for index in range(binding.operand_arity)]


def test_all_legacy_selector_destinations_are_contract_backed() -> None:
    assert len(LEGACY_SELECTOR_DESTS) == 117
    assert set(migrated_legacy_selectors()) == set(LEGACY_SELECTOR_DESTS)
    assert remaining_legacy_only_selectors() == ()
    assert len(action_contract_ids()) == 119


def test_every_generated_binding_roundtrips_legacy_and_canonical_parse() -> None:
    parser = build_parser()
    assert len(GENERATED_LEGACY_ACTION_BINDINGS) == 91
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
        assert legacy_resolution.canonical_action_id == binding.action_id
        assert canonical_resolution.canonical_action_id == binding.action_id

        materialized = _materialize_compat_selector(binding, canonical_args)
        assert active_legacy_selectors(materialized) == (binding.selector,)
        assert getattr(materialized, binding.selector) == getattr(legacy_args, binding.selector)


def test_curated_legacy_aliases_and_runtime_plan_are_closed() -> None:
    parser = build_parser()
    by_dest = {action.dest: action for action in parser._actions}
    for selector, action_id in STATIC_MIGRATED_SELECTOR_MAP.items():
        action = by_dest[selector]
        assert action.nargs == 0
        args = parser.parse_args([action.option_strings[0]])
        assert resolve_cli_action(args).canonical_action_id == action_id
    for verb in ("start", "stop", "status"):
        args = parser.parse_args(["--runtime-plan", verb])
        assert resolve_cli_action(args).canonical_action_id == f"runtime.plan.{verb}"


def test_main_no_longer_contains_legacy_first_match_dispatch() -> None:
    tree = ast.parse((ROOT / "gui/zap2_gui/app.py").read_text(encoding="utf-8"))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    attrs = {
        node.attr
        for node in ast.walk(main)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "args"
    }
    assert not (attrs & set(LEGACY_SELECTOR_DESTS))


def test_action_projection_is_generated_from_closed_catalog() -> None:
    rows = action_projection_rows()
    assert len(rows) == 119
    assert len({row["actionId"] for row in rows}) == 119
    assert {row["actionId"] for row in rows} == set(ACTION_CONTRACT_BY_ID)
    assert all(row["label"] and row["shortHelp"] for row in rows)
