import json
import shutil
from pathlib import Path

import pytest

from zap2_gui.adapters.runtime_state import (
    confirm_runtime_plan,
    prepare_runtime_plan,
    runtime_log_to_text,
    runtime_store_paths,
)

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc")
    shutil.copytree(ROOT, target, ignore=ignore)
    return target


def test_prepare_runtime_plan_creates_workspace_state_only(tmp_path):
    project = _copy_project(tmp_path)

    prepared = prepare_runtime_plan(project, action="start", profile_id="default")
    paths = runtime_store_paths(project)

    assert prepared.plan_id == "runtime-default-manual-local-start-plan"
    assert len(prepared.plan_hash) == 64
    assert prepared.plan_path.exists()
    assert prepared.rollback_path.exists()
    assert prepared.log_path.exists()
    assert paths.sessions_dir.exists()
    assert paths.confirmations_dir.exists()

    saved = json.loads(prepared.plan_path.read_text(encoding="utf-8"))
    assert saved["planHash"] == prepared.plan_hash
    assert saved["confirmed"] is False
    assert saved["execution"]["executesNow"] is False
    assert saved["execution"]["mutatesServicesOrFirewallNow"] is False
    assert saved["execution"]["automaticChecksMayExecute"] is False

    rollback = prepared.rollback_path.read_text(encoding="utf-8")
    assert prepared.plan_hash in rollback
    assert "Stage 10 не исполняет" in rollback


def test_confirm_runtime_plan_is_bound_to_plan_hash(tmp_path):
    project = _copy_project(tmp_path)
    prepared = prepare_runtime_plan(project, action="start", profile_id="default")

    confirmation = confirm_runtime_plan(project, prepared.plan_id)

    assert confirmation.plan_id == prepared.plan_id
    assert confirmation.plan_hash == prepared.plan_hash
    assert confirmation.confirmation_path.exists()
    data = json.loads(confirmation.confirmation_path.read_text(encoding="utf-8"))
    assert data["confirmedByOwner"] is True
    assert data["expiresWhenPlanChanges"] is True
    assert data["allowsAutomaticReuse"] is False

    log_text = runtime_log_to_text(project, profile_id="default")
    assert "planned" in log_text
    assert "confirmed" in log_text
    assert "executes now: no" in log_text


def test_confirmation_rejects_tampered_plan_hash(tmp_path):
    project = _copy_project(tmp_path)
    prepared = prepare_runtime_plan(project, action="start", profile_id="default")

    saved = json.loads(prepared.plan_path.read_text(encoding="utf-8"))
    saved["binaryRelativePath"] = "core/zapret2/tampered"
    prepared.plan_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="hash"):
        confirm_runtime_plan(project, prepared.plan_id)


def test_runtime_log_reports_missing_log_without_creating_state(tmp_path):
    project = _copy_project(tmp_path)
    text = runtime_log_to_text(project, profile_id="default")

    assert "entries: 0" in text
    assert "log file отсутствует" in text
    assert not (project / ".zap2").exists()
