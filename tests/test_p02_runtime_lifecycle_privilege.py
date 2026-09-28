from __future__ import annotations

import json
import os
import runpy
import shutil
from pathlib import Path

import pytest

from zap2_gui.adapters.core_provenance import write_core_build_receipt
from zap2_gui.adapters.gui_privilege import (
    build_gui_privileged_command,
    build_gui_privileged_discord_probe_command,
)
from zap2_gui.adapters.privileged_executor import BoundedNftRunner
from zap2_gui.adapters.runtime_kernel import runtime_kernel_status
from zap2_gui.adapters.runtime_migration import migrate_runtime_session_state
from zap2_gui.adapters.runtime_session import SESSION_MARKER, build_runtime_session_config, runtime_session_status
from zap2_gui.adapters.runtime_state import confirm_runtime_plan, prepare_runtime_plan

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(
        ROOT,
        project,
        ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"),
    )
    return project


def _fake_binary(project: Path) -> Path:
    path = project / "core/zapret2/nfq2/nfqws2"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"#!/bin/sh\nsleep 30\n")
    path.chmod(0o755)
    write_core_build_receipt(project, [path], "nfqws2")
    return path


def test_gui_privilege_preview_never_root_imports_writable_project(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    assert not (project / ".zap2").exists()
    command = build_gui_privileged_command(root=project, action="start")
    assert not (project / ".zap2").exists()
    joined = " ".join(command.argv)
    assert command.argv[:3] == ("sudo", "-A", "--")
    assert "/usr/local/libexec/zap2-runtime-executor" in command.argv
    assert "PYTHONPATH" not in joined
    assert "zap2_gui.app" not in joined
    assert "env" not in command.argv
    assert str(project) not in joined


def test_privileged_discord_probe_does_not_expand_p02_root_surface(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    command = build_gui_privileged_discord_probe_command(root=project, wait_seconds=30)
    assert command.argv == ("P02-STAGED", "discord-pretls-guided-probe", "no-root-execution")
    assert not command.env_overrides


def test_bounded_nft_runner_rejects_arbitrary_argv_before_sudo(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    runner = BoundedNftRunner(project)
    with pytest.raises(ValueError, match="rejected argv"):
        runner(("sh", "-c", "id"))
    with pytest.raises(ValueError, match="rejected argv"):
        runner(("nft", "delete", "table", "inet", "foreign"))


def test_helper_finite_action_and_request_hash_contract() -> None:
    helper = runpy.run_path(str(ROOT / "tools/privileged/zap2-runtime-executor"), run_name="p02_helper_test")
    ExecutorError = helper["ExecutorError"]
    stable_json = helper["stable_json"]
    sha256_bytes = helper["sha256_bytes"]
    parse_request = helper["parse_request"]
    execute = helper["execute"]

    body = {"schemaVersion": 1, "protocol": "zap2-privilege-plan/v1", "actionId": "unknown.action", "payload": {}}
    request_hash = sha256_bytes(stable_json(body).encode("utf-8"))
    wire = dict(body, requestHash=request_hash)
    action, payload, calculated = parse_request((stable_json(wire) + "\n").encode(), request_hash)
    assert calculated == request_hash and action == "unknown.action" and payload == {}
    with pytest.raises(ExecutorError, match="unsupported finite actionId"):
        execute(action, payload)
    with pytest.raises(ExecutorError, match="request hash mismatch"):
        parse_request((stable_json(wire) + "\n").encode(), "0" * 64)


def test_start_plan_binds_runtime_file_bytes_and_detects_post_confirm_mutation(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    _fake_binary(project)
    prepared = prepare_runtime_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, prepared.plan_id)
    # P02 privileged path does not copy to public /tmp during preflight.
    config = build_runtime_session_config(project, "default", prepare_public_inputs=False)
    assert config.public_session_inputs_dir is None

    lua = project / "core/zapret2/lua/zapret-lib.lua"
    lua.write_bytes(lua.read_bytes() + b"\n-- p02 mutation test\n")
    with pytest.raises(ValueError, match="plan|hash|измен"):
        build_runtime_session_config(project, "default", prepare_public_inputs=False)


def test_read_only_status_requires_explicit_legacy_migration(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    binary = project / "legacy-sleep"
    shutil.copyfile("/bin/sleep", binary)
    binary.chmod(0o755)
    sessions = project / ".zap2/runtime/sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    session = sessions / "default.session.json"
    pidfile = sessions / "default.pid"
    import subprocess
    proc = subprocess.Popen([str(binary), "30"])
    try:
        pidfile.write_text(str(proc.pid), encoding="utf-8")
        legacy = {
            "schemaVersion": 1, "marker": SESSION_MARKER, "state": "running", "profileId": "default",
            "rootPath": str(project), "sessionPath": str(session), "pid": proc.pid,
            "binaryPath": str(binary), "argv": [str(binary), "30"], "pidfilePath": str(pidfile),
            "planId": "legacy", "planHash": "legacy",
        }
        session.write_text(json.dumps(legacy), encoding="utf-8")
        before = session.read_bytes()
        assert runtime_session_status(project).state == "migration-required"
        assert session.read_bytes() == before
        receipt = migrate_runtime_session_state(project)
        assert receipt.state == "migrated"
        assert receipt.backup_path and receipt.backup_path.read_bytes() == before
        assert runtime_session_status(project).state == "running"
        data = json.loads(session.read_text(encoding="utf-8"))
        assert data["schemaVersion"] == 2
        assert data["processIdentity"]["procStartTime"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_newer_runtime_schema_is_refused(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    sessions = project / ".zap2/runtime/sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    path = sessions / "default.session.json"
    path.write_text(json.dumps({"schemaVersion": 999, "marker": SESSION_MARKER, "profileId": "default", "state": "stopped", "pid": 0, "rootPath": str(project), "sessionPath": str(path), "binaryPath": str(project / 'x')}), encoding="utf-8")
    with pytest.raises(ValueError, match="newer"):
        migrate_runtime_session_state(project)


def test_runtime_status_and_reconcile_do_not_create_runtime_state(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    runtime_root = project / ".zap2"
    assert not runtime_root.exists()

    def missing_runner(argv: tuple[str, ...]):
        from zap2_gui.adapters.runtime_apply import RuntimeCommandResult
        return RuntimeCommandResult(argv, 1, stderr="No such table")

    from zap2_gui.adapters.runtime_apply import reconcile_runtime_owner_rules

    reconciled = reconcile_runtime_owner_rules(project, runner=missing_runner)
    assert reconciled.state == "clean"
    assert not runtime_root.exists()

    status = runtime_kernel_status(project, nft_runner=missing_runner)
    assert status.ownership_state == "absent"
    assert not runtime_root.exists()

    from zap2_gui.adapters.runtime_default import default_workflow_status

    default_status = default_workflow_status(project)
    assert default_status.workflow_state == "not-started"
    assert not runtime_root.exists()


def test_runtime_kernel_classifies_foreign_conflict_without_deleting(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)

    def foreign_runner(argv: tuple[str, ...]):
        from zap2_gui.adapters.runtime_apply import RuntimeCommandResult
        if argv[:4] == ("nft", "list", "table", "inet"):
            return RuntimeCommandResult(argv, 0, stdout="table inet something { comment \"foreign\"; }")
        raise AssertionError(f"status must not mutate: {argv}")

    status = runtime_kernel_status(project, nft_runner=foreign_runner)
    assert status.ownership_state == "foreign-conflict"
    assert "do not delete" in status.next_safe_action


def test_helper_source_is_stdlib_standalone_and_no_project_import() -> None:
    text = (ROOT / "tools/privileged/zap2-runtime-executor").read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/python3 -I")
    assert "import zap2_gui" not in text
    assert "PYTHONPATH" in text  # explicitly rejected by the helper
    assert "shell=True" not in text


def test_helper_rejects_forged_confirmed_plan_with_arbitrary_executable(tmp_path: Path) -> None:
    helper = runpy.run_path(str(ROOT / "tools/privileged/zap2-runtime-executor"), run_name="p02_helper_forged_plan")
    ExecutorError = helper["ExecutorError"]
    plan_hash = helper["plan_hash"]
    action_nfqws_start = helper["action_nfqws_start"]

    root = tmp_path / "workspace"
    root.mkdir()
    evil = root / "evil"
    evil.write_text("#!/bin/sh\nid\n", encoding="utf-8")
    evil.chmod(0o755)
    plan = {
        "schemaVersion": 1,
        "stage": "v0.3-alpha_stage_10",
        "planId": "forged",
        "action": "start",
        "profileId": "default",
        "strategyId": "manual-local",
        "buildTarget": "nfqws2",
        "binaryRelativePath": "evil",
        "hostlists": [],
        "strategyRuntimeArgs": [],
        "contract": {
            "action": "start", "profileId": "default", "strategyId": "manual-local",
            "safety": {"requiresOwnerConfirmation": True, "mayManageServiceWhenExecutedByOwner": False},
        },
        "runtimeArtifacts": {
            "schemaVersion": 1,
            "binary": {"kind": "nfqws2-binary", "path": "evil", "state": "ready", "sha256": "0" * 64},
            "inputs": [],
            "owner": {"uid": os.getuid(), "gid": os.getgid()},
            "queue": {"profileId": "default", "qnum": 478, "source": "owner-workspace-hash"},
        },
    }
    plan["planHash"] = plan_hash(plan)
    confirmation = {"planId": "forged", "planHash": plan["planHash"], "confirmedByOwner": True}
    with pytest.raises(ExecutorError, match="arbitrary executable|non-canonical executable"):
        action_nfqws_start({"rootPath": str(root), "plan": plan, "confirmation": confirmation})


def test_helper_openat_reader_rejects_symlink_components(tmp_path: Path) -> None:
    helper = runpy.run_path(str(ROOT / "tools/privileged/zap2-runtime-executor"), run_name="p02_helper_symlink")
    ExecutorError = helper["ExecutorError"]
    read_workspace_source_once = helper["read_workspace_source_once"]

    root = tmp_path / "workspace"
    real = root / "real"
    real.mkdir(parents=True)
    (real / "input.txt").write_text("safe", encoding="utf-8")
    (root / "link").symlink_to(real, target_is_directory=True)
    with pytest.raises(ExecutorError, match="unsafe|symlink|cannot open"):
        read_workspace_source_once(root, "link/input.txt")


def test_plan_preparation_rejects_symlink_runtime_input(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    _fake_binary(project)
    lua = project / "core/zapret2/lua/zapret-lib.lua"
    original = tmp_path / "outside.lua"
    original.write_bytes(lua.read_bytes())
    lua.unlink()
    lua.symlink_to(original)
    with pytest.raises(ValueError, match="symlink|leaves workspace"):
        prepare_runtime_plan(project, action="start", profile_id="default")
