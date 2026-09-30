from __future__ import annotations

import json
import os
import runpy
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from zap2_gui.adapters.core_provenance import write_core_build_receipt
from zap2_gui.adapters.gui_privilege import (
    build_gui_privileged_command,
    build_gui_privileged_discord_probe_command,
)
from zap2_gui.adapters.privileged_executor import BoundedNftRunner
import zap2_gui.adapters.privileged_executor as privileged_executor_module
import zap2_gui.adapters.runtime_session as runtime_session_module
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


def test_bounded_nft_observation_preserves_expected_missing_table_result(tmp_path: Path, monkeypatch) -> None:
    project = _copy_project(tmp_path)
    installed = tmp_path / "zap2-runtime-executor"

    monkeypatch.setattr(
        privileged_executor_module,
        "privileged_executor_status",
        lambda *args, **kwargs: SimpleNamespace(ready=True),
    )
    monkeypatch.setattr(privileged_executor_module.shutil, "which", lambda name: "/usr/bin/sudo" if name == "sudo" else None)

    def fake_run(argv, *, input, stdout, stderr, cwd, env, check, timeout):
        request = json.loads(input.decode("utf-8"))
        receipt = {
            "ok": True,
            "schemaVersion": 1,
            "protocol": "zap2-privilege-plan/v1",
            "actionId": "nft.observe-table",
            "requestHash": request["requestHash"],
            "helper": {"version": "p02-v1", "sha256": "a" * 64, "ruid": 0, "euid": 0},
            "planHash": None,
            "command": {
                "argv": ["/usr/bin/nft", "list", "table", "inet", "zap2_test"],
                "returncode": 1,
                "stdout": "",
                "stderr": "Error: No such file or directory\n",
            },
        }
        return subprocess.CompletedProcess(argv, 1, stdout=json.dumps(receipt).encode("utf-8"), stderr=b"")

    monkeypatch.setattr(privileged_executor_module.subprocess, "run", fake_run)
    result = BoundedNftRunner(project, installed_path=installed)(("nft", "list", "table", "inet", "zap2_test"))
    assert result.returncode == 1
    assert "No such file" in result.stderr


def test_privileged_non_observation_command_failure_remains_fatal(tmp_path: Path, monkeypatch) -> None:
    project = _copy_project(tmp_path)
    installed = tmp_path / "zap2-runtime-executor"
    monkeypatch.setattr(
        privileged_executor_module,
        "privileged_executor_status",
        lambda *args, **kwargs: SimpleNamespace(ready=True),
    )
    monkeypatch.setattr(privileged_executor_module.shutil, "which", lambda name: "/usr/bin/sudo" if name == "sudo" else None)

    def fake_run(argv, *, input, stdout, stderr, cwd, env, check, timeout):
        request = json.loads(input.decode("utf-8"))
        receipt = {
            "ok": True,
            "schemaVersion": 1,
            "protocol": "zap2-privilege-plan/v1",
            "actionId": "nft.execute-confirmed-plan",
            "requestHash": request["requestHash"],
            "helper": {"version": "p02-v1", "sha256": "a" * 64, "ruid": 0, "euid": 0},
            "planHash": "b" * 64,
            "command": {"argv": ["/usr/bin/nft", "-f", "-"], "returncode": 1, "stdout": "", "stderr": "syntax error"},
        }
        return subprocess.CompletedProcess(argv, 1, stdout=json.dumps(receipt).encode("utf-8"), stderr=b"")

    monkeypatch.setattr(privileged_executor_module.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="privileged executor failed rc=1"):
        privileged_executor_module._call_helper(
            project,
            "nft.execute-confirmed-plan",
            {},
            askpass=None,
            installed_path=installed,
        )


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


def test_bounded_session_launcher_carries_confirmed_plan_owner_drop_identity(tmp_path: Path, monkeypatch) -> None:
    project = _copy_project(tmp_path)
    plan = {
        "planHash": "a" * 64,
        "runtimeArtifacts": {"owner": {"uid": 1234, "gid": 1235}},
    }
    monkeypatch.setattr(privileged_executor_module, "_confirmed_plan", lambda _root, _plan_id: (plan, {"confirmedByOwner": True}))
    monkeypatch.setattr(
        privileged_executor_module,
        "_call_helper",
        lambda *args, **kwargs: {
            "actionId": "nfqws.start-confirmed-plan",
            "planHash": "a" * 64,
            "requestHash": "b" * 64,
            "helper": {"sha256": "c" * 64, "version": "p02-v1", "ruid": 0, "euid": 0},
            "process": {
                "pid": 4242,
                "executablePath": "/run/zap2/u1234/test/nfqws2",
                "stdoutLogPath": "/run/zap2/u1234/test/stdout.log",
                "stderrLogPath": "/run/zap2/u1234/test/stderr.log",
                "debugLogPath": None,
                "identity": {"bootId": "boot", "procStartTime": "1", "procExecutable": "/run/zap2/u1234/test/nfqws2", "cmdlineSha256": "d" * 64},
            },
        },
    )
    launcher = privileged_executor_module.BoundedSessionLauncher(project)
    receipt = launcher(SimpleNamespace(plan_id="runtime-default-manual-local-start-plan"))
    assert receipt.drop_identity is not None
    assert (receipt.drop_identity.uid, receipt.drop_identity.gid, receipt.drop_identity.source) == (1234, 1235, "bounded-plan-owner")


def test_session_record_uses_bounded_launcher_drop_identity_even_when_owner_config_has_none(tmp_path: Path, monkeypatch) -> None:
    from zap2_gui.adapters.runtime_session import RuntimeDropIdentity, RuntimeSessionConfig, RuntimeSessionLaunchReceipt, _base_session_record

    project = tmp_path / "project"
    project.mkdir()
    binary = project / "nfqws2"
    binary.write_bytes(b"x")
    session = project / "session.json"
    config = RuntimeSessionConfig(
        profile_id="default", plan_id="plan", plan_hash="a" * 64, root_path=project,
        binary_path=binary, cwd=project, argv=(str(binary),), args_path=project / "args",
        session_inputs_dir=project / "inputs", public_session_inputs_dir=None,
        hostlist_input_paths=(), strategy_file_input_paths=(), lua_input_paths=(), blob_input_paths=(),
        pidfile_path=project / "pid", stdout_log_path=project / "out", stderr_log_path=project / "err",
        debug_log_path=project / "debug", session_path=session, runtime_args=(), drop_identity=None,
        nfqueue_num=1, nfqueue_source="test",
    )
    receipt = RuntimeSessionLaunchReceipt(
        pid=os.getpid(), runtime_executable_path=binary, stdout_log_path=project / "hout", stderr_log_path=project / "herr",
        debug_log_path=None, helper_sha256="b" * 64, helper_version="p02-v1", helper_ruid=0, helper_euid=0,
        action_id="nfqws.start-confirmed-plan", plan_hash="a" * 64, request_hash="c" * 64,
        process_identity={"bootId": "boot", "procStartTime": "1", "procExecutable": str(binary), "cmdlineSha256": "d" * 64},
        drop_identity=RuntimeDropIdentity(uid=1000, gid=1000, source="bounded-plan-owner"),
    )
    monkeypatch.setattr(runtime_session_module, "verify_core_bundle", lambda *args, **kwargs: SimpleNamespace(state="verified", message="ok", receipt_path=project / "receipt"))
    monkeypatch.setattr(runtime_session_module, "find_nfqueue_processes", lambda *_args, **_kwargs: ())
    record = _base_session_record(config, os.getpid(), "running", launch_receipt=receipt)
    assert record["dropIdentity"] == {"uid": 1000, "gid": 1000, "source": "bounded-plan-owner"}


def test_backfill_bounded_drop_identity_requires_plan_helper_and_live_identity(tmp_path: Path, monkeypatch) -> None:
    from zap2_gui.adapters.runtime_session import _capture_process_identity, backfill_bounded_drop_identity

    project = _copy_project(tmp_path)
    binary = tmp_path / "sleep"
    shutil.copyfile("/bin/sleep", binary)
    binary.chmod(0o755)
    proc = subprocess.Popen([str(binary), "30"])
    try:
        identity = None
        for _ in range(20):
            identity = _capture_process_identity(proc.pid, binary)
            if identity:
                break
            time.sleep(0.01)
        assert identity
        paths = project / ".zap2/runtime"
        (paths / "sessions").mkdir(parents=True)
        (paths / "plans").mkdir(parents=True)
        (paths / "confirmations").mkdir(parents=True)
        plan_id = "runtime-default-manual-local-start-plan"
        plan_hash = "e" * 64
        plan = {
            "planId": plan_id, "planHash": plan_hash, "action": "start", "buildTarget": "nfqws2",
            "runtimeArtifacts": {"owner": {"uid": os.getuid(), "gid": os.getgid()}},
        }
        (paths / "plans" / f"{plan_id}.json").write_text(json.dumps(plan), encoding="utf-8")
        (paths / "confirmations" / f"{plan_id}.confirmation.json").write_text(json.dumps({"planHash": plan_hash, "confirmedByOwner": True}), encoding="utf-8")
        helper_sha = __import__("hashlib").sha256((project / "tools/privileged/zap2-runtime-executor").read_bytes()).hexdigest()
        session_path = paths / "sessions/default.session.json"
        session_path.write_text(json.dumps({
            "schemaVersion": 2, "marker": SESSION_MARKER, "state": "running", "profileId": "default",
            "rootPath": str(project), "sessionPath": str(session_path), "pid": proc.pid, "binaryPath": str(binary),
            "planId": plan_id, "planHash": plan_hash, "processIdentity": identity, "dropIdentity": None,
            "privilegedExecutor": {"actionId": "nfqws.start-confirmed-plan", "planHash": plan_hash, "helperSha256": helper_sha},
        }), encoding="utf-8")
        monkeypatch.setattr(runtime_session_module, "_proc_executable", lambda _pid: None)
        assert backfill_bounded_drop_identity(project) == "backfilled"
        adopted = json.loads(session_path.read_text(encoding="utf-8"))
        assert adopted["dropIdentity"]["uid"] == os.getuid()
        assert adopted["dropIdentity"]["gid"] == os.getgid()
        assert adopted["dropIdentity"]["source"] == "bounded-plan-owner-backfill"
        assert adopted["dropIdentityBackfill"]["identityMode"] == "drop-identity-anchored"
    finally:
        proc.terminate(); proc.wait(timeout=5)


def test_backfill_bounded_drop_identity_skips_dead_session_without_mutation(tmp_path: Path) -> None:
    from zap2_gui.adapters.runtime_session import backfill_bounded_drop_identity
    project = _copy_project(tmp_path)
    sessions = project / ".zap2/runtime/sessions"
    sessions.mkdir(parents=True)
    path = sessions / "default.session.json"
    original = {
        "schemaVersion": 2, "marker": SESSION_MARKER, "state": "running", "profileId": "default",
        "rootPath": str(project), "sessionPath": str(path), "pid": 99999999,
        "binaryPath": str(project / "core/zapret2/nfq2/nfqws2"), "dropIdentity": None,
    }
    path.write_text(json.dumps(original), encoding="utf-8")
    before = path.read_bytes()
    assert backfill_bounded_drop_identity(project) == "process-not-live"
    assert path.read_bytes() == before
