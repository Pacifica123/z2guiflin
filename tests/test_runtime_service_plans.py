import json
import shutil
from pathlib import Path

import pytest

from zap2_gui.adapters.runtime_service import (
    SERVICE_MARKER,
    ServiceCommandResult,
    create_service_plan,
    execute_service_plan,
    prepare_service_plan,
)
from zap2_gui.adapters.runtime_state import confirm_runtime_plan

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    ignore = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".zap2", "*.pyc")
    shutil.copytree(ROOT, target, ignore=ignore)
    return target


def test_create_service_plans_are_separate_from_session_and_firewall(tmp_path):
    project = _copy_project(tmp_path)
    service_dir = tmp_path / "systemd"

    for action in ("install", "start", "stop", "remove"):
        plan = create_service_plan(project, action=action, profile_id="default", service_dir=service_dir)
        payload = plan.to_payload()
        assert payload["marker"] == SERVICE_MARKER
        assert payload["safety"]["separateFromSessionMode"] is True
        assert payload["safety"]["defaultWorkflow"] is False
        assert payload["safety"]["mutatesFirewallWhenExecutedByOwner"] is False
        assert payload["safety"]["containsRemoteBootstrap"] is False
        assert payload["safety"]["containsUpstreamInstallerScript"] is False
        assert payload["execution"]["automaticChecksMayExecute"] is False
        assert plan.service_name == "zap2-default.service"

    start_plan = create_service_plan(project, action="start", profile_id="default", service_dir=service_dir)
    assert start_plan.can_execute_now is False
    assert start_plan.commands[0].argv == ("systemctl", "start", "zap2-default.service")


def test_prepare_service_plan_uses_runtime_confirmation_gate(tmp_path):
    project = _copy_project(tmp_path)
    service_dir = tmp_path / "systemd"

    prepared = prepare_service_plan(project, action="install", profile_id="default", service_dir=service_dir)
    confirmation = confirm_runtime_plan(project, prepared.plan_id)

    assert prepared.plan_id == "runtime-default-manual-local-service-install-plan"
    assert len(prepared.plan_hash) == 64
    assert confirmation.plan_hash == prepared.plan_hash
    saved = json.loads(prepared.plan_path.read_text(encoding="utf-8"))
    assert saved["confirmed"] is True
    assert saved["safety"]["mutatesServiceWhenExecutedByOwner"] is True
    assert saved["execution"]["guardedExecutionAvailable"] is True
    assert "service remove plan" in prepared.rollback_path.read_text(encoding="utf-8")


def test_execute_service_install_with_fake_runner_and_temp_service_dir(tmp_path):
    project = _copy_project(tmp_path)
    service_dir = tmp_path / "systemd"
    prepared = prepare_service_plan(project, action="install", profile_id="default", service_dir=service_dir)
    confirm_runtime_plan(project, prepared.plan_id)
    calls: list[tuple[str, ...]] = []

    def fake_runner(argv: tuple[str, ...]) -> ServiceCommandResult:
        calls.append(argv)
        return ServiceCommandResult(argv=argv, returncode=0)

    result = execute_service_plan(
        project,
        action="install",
        profile_id="default",
        confirm_plan_id=prepared.plan_id,
        service_dir=service_dir,
        runner=fake_runner,
        allow_without_root=True,
    )

    assert result.state == "installed"
    assert calls == [("systemctl", "daemon-reload")]
    assert result.unit_path.exists()
    assert "ExecStart=" in result.unit_path.read_text(encoding="utf-8")
    assert "zap2-default.service" in result.service_name
    assert (project / ".zap2/runtime/sessions/default.service.nfqws2.args").exists()


def test_execute_service_remove_removes_only_owned_unit_with_fake_runner(tmp_path):
    project = _copy_project(tmp_path)
    service_dir = tmp_path / "systemd"
    install = prepare_service_plan(project, action="install", profile_id="default", service_dir=service_dir)
    confirm_runtime_plan(project, install.plan_id)

    def ok_runner(argv: tuple[str, ...]) -> ServiceCommandResult:
        return ServiceCommandResult(argv=argv, returncode=0)

    execute_service_plan(
        project,
        action="install",
        profile_id="default",
        confirm_plan_id=install.plan_id,
        service_dir=service_dir,
        runner=ok_runner,
        allow_without_root=True,
    )
    unit_path = service_dir / "zap2-default.service"
    assert unit_path.exists()

    remove = prepare_service_plan(project, action="remove", profile_id="default", service_dir=service_dir)
    confirm_runtime_plan(project, remove.plan_id)
    calls: list[tuple[str, ...]] = []

    def fake_runner(argv: tuple[str, ...]) -> ServiceCommandResult:
        calls.append(argv)
        return ServiceCommandResult(argv=argv, returncode=0)

    result = execute_service_plan(
        project,
        action="remove",
        profile_id="default",
        confirm_plan_id=remove.plan_id,
        service_dir=service_dir,
        runner=fake_runner,
        allow_without_root=True,
    )

    assert result.state == "removed"
    assert not unit_path.exists()
    assert ("systemctl", "stop", "zap2-default.service") in calls
    assert ("systemctl", "disable", "zap2-default.service") in calls
    assert ("systemctl", "daemon-reload") in calls


def test_service_start_stop_execution_is_rejected(tmp_path):
    project = _copy_project(tmp_path)
    with pytest.raises(ValueError, match="install/remove"):
        execute_service_plan(project, action="start", profile_id="default", confirm_plan_id="anything", allow_without_root=True)  # type: ignore[arg-type]
