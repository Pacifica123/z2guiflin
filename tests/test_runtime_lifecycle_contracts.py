from __future__ import annotations

import json
from pathlib import Path

from zap2_gui.adapters.runtime_contracts import (
    load_runtime_contract_catalog,
    runtime_contracts_to_text,
    validate_runtime_contract_catalog,
    validate_runtime_contracts_to_text,
)
from zap2_gui.app import describe_project, main
from zap2_gui.models.lifecycle import PLAN_SECTION_KINDS, default_lifecycle_boundary
from zap2_gui.models.runtime_plan import validate_runtime_plan_contract

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_schema_files_are_present_and_contract_focused() -> None:
    schema_dir = ROOT / "runtime/schemas"
    plan_schema = json.loads((schema_dir / "runtime-plan.schema.json").read_text(encoding="utf-8"))
    event_schema = json.loads((schema_dir / "runtime-event.schema.json").read_text(encoding="utf-8"))
    confirmation_schema = json.loads((schema_dir / "confirmation.schema.json").read_text(encoding="utf-8"))

    assert "sections" in plan_schema["required"]
    assert "rollbackNotes" in plan_schema["required"]
    assert "planId" in event_schema["required"]
    assert "planHash" in confirmation_schema["required"]


def test_default_lifecycle_boundary_is_plan_only() -> None:
    boundary = default_lifecycle_boundary()

    assert boundary.is_stage8_plan_only is True
    assert boundary.automatic_checks_may_execute is False
    assert boundary.bootstrap_mixed_in is False
    assert boundary.may_start_processes is False
    assert boundary.may_mutate_services_or_firewall is False


def test_runtime_contract_catalog_validates_without_execution() -> None:
    issues = validate_runtime_contract_catalog(ROOT)
    errors = [issue for issue in issues if issue.severity == "error"]

    assert errors == []


def test_manual_local_start_contract_covers_lifecycle_sections() -> None:
    catalog = load_runtime_contract_catalog(ROOT)
    plan = catalog.plan_contracts[0]
    issues = validate_runtime_plan_contract(plan)

    assert [issue for issue in issues if issue.severity == "error"] == []
    assert set(plan.section_kinds) == set(PLAN_SECTION_KINDS)
    assert plan.is_stage8_contract_only is True
    assert plan.safety.requires_owner_confirmation is True
    assert plan.safety.contains_remote_bootstrap is False
    assert plan.safety.contains_upstream_installer_script is False
    assert len(plan.rollback_notes) >= 1


def test_runtime_event_and_confirmation_refer_to_existing_plan() -> None:
    catalog = load_runtime_contract_catalog(ROOT)
    plan_ids = {plan.plan_id for plan in catalog.plan_contracts}

    assert {event.plan_id for event in catalog.event_contracts} <= plan_ids
    assert {confirmation.plan_id for confirmation in catalog.confirmation_contracts} <= plan_ids
    assert all(not confirmation.allows_automatic_reuse for confirmation in catalog.confirmation_contracts)
    assert all(confirmation.expires_when_plan_changes for confirmation in catalog.confirmation_contracts)


def test_runtime_contract_cli_is_read_only() -> None:
    assert main(["--runtime-contracts"]) == 0
    assert main(["--validate-runtime-contracts"]) == 0
    assert "runtime lifecycle contracts: OK" in describe_project()
    assert "automatic checks may execute plans: no" in runtime_contracts_to_text(ROOT)
    assert "execution: disabled in Stage 8" in validate_runtime_contracts_to_text(ROOT)
