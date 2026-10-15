from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from zap2_gui.adapters.core_provenance import verify_core_bundle, write_core_build_receipt
from zap2_gui.adapters.runtime_apply import RuntimeCommandResult, authorize_stale_legacy_v04_table, create_runtime_apply_plan, execute_runtime_owner_rules, prepare_runtime_owner_rules_plan, reconcile_runtime_owner_rules
from zap2_gui.adapters import runtime_session as runtime_session_module
from zap2_gui.adapters.runtime_session import _capture_process_identity, _record_matches_process
from zap2_gui.adapters.runtime_state import confirm_runtime_plan
from zap2_gui.adapters.security_blocklist import (
    apply_security_blocklist,
    refresh_security_blocklist,
    set_security_blocklist_enabled,
    update_security_blocklist,
    security_blocklist_timer_plan,
)
from zap2_gui.theme_profiles import LIGHT_COLORS, builtin_theme_profile, custom_stylesheet

ROOT = Path(__file__).resolve().parents[1]



def _wait_for_exec(proc, binary, timeout=5.0):
    """Ждать, пока дочерний процесс выполнит exec и опубликует argv.

    До exec /proc/<pid>/exe указывает на python, а сразу после exec /proc/<pid>/cmdline
    ещё короткое время пуст (гонка fork→exec→argv). Продуктовый код законно отказывает
    в такой момент, поэтому тест ждёт устойчивого состояния.
    """
    import os, time
    target = os.path.realpath(str(binary))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            exe_ok = os.path.realpath(os.readlink(f"/proc/{proc.pid}/exe")) == target
            with open(f"/proc/{proc.pid}/cmdline", "rb") as handle:
                argv_ok = bool(handle.read().split(b"\0")[0])
            if exe_ok and argv_ok:
                return
        except OSError:
            pass
        time.sleep(0.01)
    raise AssertionError(f"process {proc.pid} did not exec {target} within {timeout}s")

def _copy_project(tmp_path: Path, name: str = "project") -> Path:
    target = tmp_path / name
    shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))
    return target


class FakeNft:
    def __init__(self):
        self.exists = False
        self.text = ""
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: tuple[str, ...]):
        self.calls.append(argv)
        if argv[:4] == ("nft", "list", "table", "inet"):
            if not self.exists:
                return RuntimeCommandResult(argv=argv, returncode=1, stderr="Error: No such file or directory")
            return RuntimeCommandResult(argv=argv, returncode=0, stdout=self.text)
        if argv[:3] == ("nft", "--check", "-f"):
            return RuntimeCommandResult(argv=argv, returncode=0)
        if argv[:2] == ("nft", "-f"):
            self.text = Path(argv[2]).read_text(encoding="utf-8")
            self.exists = not self.text.lstrip().startswith("delete table")
            return RuntimeCommandResult(argv=argv, returncode=0)
        return RuntimeCommandResult(argv=argv, returncode=0)


def test_owner_identity_separates_two_workspace_tables_and_revert_addresses(tmp_path: Path) -> None:
    root_a = _copy_project(tmp_path, "a")
    copied_root = _copy_project(tmp_path, "b")
    a = create_runtime_apply_plan(root_a, "apply", "default")
    b = create_runtime_apply_plan(copied_root, "apply", "default")
    assert a.owner_key != b.owner_key
    assert a.nft_table != b.nft_table
    assert create_runtime_apply_plan(root_a, "revert", "default").commands[0].argv[-1] == a.nft_table
    assert create_runtime_apply_plan(copied_root, "revert", "default").commands[0].argv[-1] == b.nft_table


def test_nft_precheck_failure_never_executes_apply_batch(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    prepared = prepare_runtime_owner_rules_plan(project, "apply", "default")
    confirm_runtime_plan(project, prepared.plan_id)
    calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
        calls.append(argv)
        if argv[:4] == ("nft", "list", "table", "inet"):
            return RuntimeCommandResult(argv, 1, stderr="No such file or directory")
        if argv[:3] == ("nft", "--check", "-f"):
            return RuntimeCommandResult(argv, 1, stderr="synthetic parse failure")
        return RuntimeCommandResult(argv, 0)

    result = execute_runtime_owner_rules(project, "apply", "default", prepared.plan_id, runner=runner, allow_without_root=True)
    assert result.state == "failed"
    assert not any(call[:2] == ("nft", "-f") for call in calls)


def test_session_identity_fails_closed_for_legacy_and_wrong_starttime(tmp_path: Path) -> None:
    binary = tmp_path / "sleep"
    shutil.copyfile("/bin/sleep", binary)
    binary.chmod(0o755)
    proc = subprocess.Popen([str(binary), "30"])
    _wait_for_exec(proc, binary)
    try:
        identity = None
        for _ in range(20):
            identity = _capture_process_identity(proc.pid, binary)
            if identity:
                break
            time.sleep(0.01)
        assert identity
        assert not _record_matches_process({"pid": proc.pid, "binaryPath": str(binary)})
        record = {"pid": proc.pid, "binaryPath": str(binary), "processIdentity": identity}
        assert _record_matches_process(record)
        wrong = dict(record)
        wrong["processIdentity"] = dict(identity, procStartTime=str(int(identity["procStartTime"]) + 1))
        assert not _record_matches_process(wrong)
    finally:
        proc.terminate(); proc.wait(timeout=5)


def test_session_identity_accepts_kernel_hidden_exe_only_for_expected_drop_identity(tmp_path: Path, monkeypatch) -> None:
    binary = tmp_path / "sleep"
    shutil.copyfile("/bin/sleep", binary)
    binary.chmod(0o755)
    proc = subprocess.Popen([str(binary), "30"])
    _wait_for_exec(proc, binary)
    try:
        identity = None
        for _ in range(20):
            identity = _capture_process_identity(proc.pid, binary)
            if identity:
                break
            time.sleep(0.01)
        assert identity
        record = {
            "pid": proc.pid,
            "binaryPath": str(binary),
            "processIdentity": identity,
            "dropIdentity": {"uid": os.getuid(), "gid": os.getgid(), "source": "test"},
        }

        # Linux may hide /proc/<pid>/exe after setuid makes a task non-dumpable.
        # The task anchor and cmdline must still match, and the live credentials
        # must equal the explicitly recorded dropIdentity.
        monkeypatch.setattr(runtime_session_module, "_proc_executable", lambda _pid: None)
        assert _record_matches_process(record)

        wrong_uid = dict(record)
        wrong_uid["dropIdentity"] = {"uid": os.getuid() + 1, "gid": os.getgid(), "source": "test"}
        assert not _record_matches_process(wrong_uid)

        no_drop = dict(record)
        no_drop.pop("dropIdentity")
        assert not _record_matches_process(no_drop)

        wrong_cmdline = dict(record)
        wrong_cmdline["processIdentity"] = dict(identity, cmdlineSha256="0" * 64)
        assert not _record_matches_process(wrong_cmdline)
    finally:
        proc.terminate(); proc.wait(timeout=5)


def test_core_provenance_receipt_and_compat_mismatch(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    binary = project / "core/zapret2/nfq2/nfqws2"
    binary.write_bytes(b"synthetic-binary")
    binary.chmod(0o755)
    write_core_build_receipt(project, [binary], "nfqws2")
    assert verify_core_bundle(project, binary).state == "verified"
    header = project / "core/zapret2/nfq2/nfqws.h"
    header.write_text(header.read_text(encoding="utf-8").replace("#define LUA_COMPAT_VER\t6", "#define LUA_COMPAT_VER\t999"), encoding="utf-8")
    status = verify_core_bundle(project, binary)
    assert status.state == "mismatch"
    assert "compatibility generation mismatch" in status.message


def test_theme_semantic_colors_are_all_wired_into_custom_stylesheet() -> None:
    css = custom_stylesheet(builtin_theme_profile("light"))
    for key, value in LIGHT_COLORS.items():
        assert value in css, key
    assert "QFrame#contentSurface" in css and LIGHT_COLORS["surface"] in css
    assert "QToolTip" in css
    assert "QScrollBar::handle" in css


def _fixture_cache(_config):
    return {
        "schemaVersion": 1,
        "fetchedAt": "2026-09-17T00:00:00Z",
        "sources": {},
        "dnsResolverExclusions": ["1.1.1.1/32"],
        "lists": {"inbound": ["203.0.113.0/24"], "outbound": ["198.51.100.4/32", "2001:db8::/48"]},
    }


def test_security_blocklist_is_isolated_uid_scoped_and_lkg_recoverable(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    set_security_blocklist_enabled(project, True, inbound=False, outbound=True)
    update_security_blocklist(project, fetcher=_fixture_cache)
    nft = FakeNft()
    applied = apply_security_blocklist(project, runner=nft, allow_without_root=True)
    assert applied.state == "applied"
    batch = next(Path(call[2]).read_text(encoding="utf-8") for call in nft.calls if call[:2] == ("nft", "-f"))
    assert "hook output priority -10" in batch
    assert "meta skuid" in batch
    assert "198.51.100.4" in batch
    assert "security_input" not in batch
    assert "dns_exclusions4" in batch
    assert "counter accept comment \"zap2-security:dns-exclusion-outbound4\"" in batch
    assert "queue num" not in batch

    refreshed = refresh_security_blocklist(
        project,
        runner=nft,
        fetcher=lambda _cfg: (_ for _ in ()).throw(OSError("offline")),
        allow_without_root=True,
    )
    assert refreshed.state == "refreshed"
    assert refreshed.used_last_known_good is True


def test_runtime_reconciliation_is_read_only_and_never_claims_foreign_table(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    nft = FakeNft()
    clean = reconcile_runtime_owner_rules(project, "default", runner=nft)
    assert clean.state == "clean"
    assert not any(call[:2] == ("nft", "-f") for call in nft.calls)

    plan = create_runtime_apply_plan(project, "apply", "default")
    nft.exists = True
    nft.text = f'table inet {plan.nft_table} {{ chain owner_meta {{ counter comment "{plan.owner_marker}"; }} }}'
    orphan = reconcile_runtime_owner_rules(project, "default", runner=nft)
    assert orphan.state == "cleanup-required"
    assert orphan.owner_marker_matches is True

    nft.text = f'table inet {plan.nft_table} {{ chain owner_meta {{ counter comment "zap2-owner:foreign"; }} }}'
    conflict = reconcile_runtime_owner_rules(project, "default", runner=nft)
    assert conflict.state == "conflict"
    assert conflict.owner_marker_matches is False


def test_security_timer_uses_config_interval(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    config_path = set_security_blocklist_enabled(project, True, inbound=False, outbound=True)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["updateIntervalSeconds"] = 10800
    config_path.write_text(json.dumps(config), encoding="utf-8")
    _service_name, _timer_name, _service, timer = security_blocklist_timer_plan(project)
    assert "OnUnitActiveSec=10800s" in timer


def test_security_blocklist_mixed_ip_families_are_streamed_without_cross_family_collapse(tmp_path: Path, monkeypatch) -> None:
    project = _copy_project(tmp_path)
    set_security_blocklist_enabled(project, True, inbound=False, outbound=True)
    payload = b"198.51.100.4\n198.51.100.0/24\n2001:db8::1\n2001:db8:1::/48\n"
    calls = []

    def fake_fetch(url: str, timeout: int, max_bytes: int) -> bytes:
        calls.append(url)
        return payload

    monkeypatch.setattr("zap2_gui.adapters.security_blocklist._fetch", fake_fetch)
    config_path = set_security_blocklist_enabled(project, True, inbound=False, outbound=True)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["minEntries"] = 1
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = update_security_blocklist(project)
    assert result.outbound_count == 4
    assert result.inbound_count == 0
    assert calls == [config["sources"]["outbound"]]


def test_security_blocklist_generation_integrity_failure_is_fail_closed(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    set_security_blocklist_enabled(project, True, inbound=False, outbound=True)
    update_security_blocklist(project, fetcher=_fixture_cache)
    pointer = json.loads((project / ".zap2/security/ipblocklist/cache.json").read_text(encoding="utf-8"))
    generation = project / ".zap2/security/ipblocklist/generations" / pointer["activeGeneration"]
    outbound4 = generation / "outbound4.txt"
    outbound4.write_text(outbound4.read_text(encoding="utf-8") + "203.0.113.9\n", encoding="utf-8")
    nft = FakeNft()
    try:
        apply_security_blocklist(project, runner=nft, allow_without_root=True)
    except ValueError as exc:
        assert "integrity mismatch" in str(exc)
    else:
        raise AssertionError("tampered cache generation must not be applied")
    assert not any(call[:2] == ("nft", "-f") for call in nft.calls)


def test_legacy_runtime_session_is_adopted_only_after_exact_pidfile_exe_argv_match(tmp_path: Path) -> None:
    from zap2_gui.adapters.runtime_session import SESSION_MARKER, runtime_session_status, stop_runtime_session
    from zap2_gui.adapters.runtime_migration import migrate_runtime_session_state

    project = _copy_project(tmp_path)
    binary = project / "legacy-sleep"
    shutil.copyfile("/bin/sleep", binary)
    binary.chmod(0o755)
    sessions = project / ".zap2" / "runtime" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    pidfile = sessions / "default.pid"
    session_path = sessions / "default.session.json"
    proc = subprocess.Popen([str(binary), "30"])
    _wait_for_exec(proc, binary)
    try:
        pidfile.write_text(str(proc.pid), encoding="utf-8")
        session_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "marker": SESSION_MARKER,
                    "state": "running",
                    "profileId": "default",
                    "rootPath": str(project),
                    "sessionPath": str(session_path),
                    "pid": proc.pid,
                    "binaryPath": str(binary),
                    "argv": [str(binary), "30"],
                    "pidfilePath": str(pidfile),
                    "planId": "legacy-plan",
                    "planHash": "legacy-hash",
                }
            ),
            encoding="utf-8",
        )
        status = runtime_session_status(project, "default")
        assert status.state == "migration-required"
        # Read-only status must not silently rewrite legacy state.
        assert json.loads(session_path.read_text(encoding="utf-8"))["schemaVersion"] == 1
        receipt = migrate_runtime_session_state(project, "default")
        assert receipt.state == "migrated"
        assert receipt.backup_path is not None and receipt.backup_path.is_file()
        upgraded = json.loads(session_path.read_text(encoding="utf-8"))
        assert upgraded["schemaVersion"] == 2
        assert upgraded["processIdentity"]["procStartTime"]
        assert upgraded["legacyIdentityUpgrade"].startswith("schema-1 exact")
        stopped = stop_runtime_session(project, "default")
        assert stopped.state == "stopped"
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)


def test_apply_migrates_proven_workspace_sync_legacy_table_in_same_transaction(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    prepared = prepare_runtime_owner_rules_plan(project, "apply", "default")
    confirm_runtime_plan(project, prepared.plan_id)
    expected = create_runtime_apply_plan(project, "apply", "default")
    state_path = project / ".zap2" / "runtime" / "sessions" / "default.owner-rules.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "marker": "zap2-runtime-apply-v1",
                "state": "applied",
                "profileId": "default",
                "nftTable": "zap2_default",
                "ownerUid": expected.owner_uid,
            }
        ),
        encoding="utf-8",
    )
    calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
        calls.append(argv)
        if argv[:4] == ("nft", "list", "table", "inet"):
            table = argv[4]
            if table == "zap2_default":
                return RuntimeCommandResult(argv, 0, stdout="table inet zap2_default { chain local_out { } }")
            return RuntimeCommandResult(argv, 1, stderr="No such table")
        return RuntimeCommandResult(argv, 0)

    result = execute_runtime_owner_rules(project, "apply", "default", prepared.plan_id, runner=runner, allow_without_root=True)
    assert result.state == "applied"
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["legacyNftTableMigrated"] == "zap2_default"
    transaction = (project / state["transactionPath"]).read_text(encoding="utf-8")
    assert transaction.splitlines()[0] == "delete table inet zap2_default"
    assert f"add table inet {expected.nft_table}" in transaction


def test_apply_refuses_unproven_legacy_table(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    prepared = prepare_runtime_owner_rules_plan(project, "apply", "default")
    confirm_runtime_plan(project, prepared.plan_id)
    executed_batch = False

    def runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
        nonlocal executed_batch
        if argv[:4] == ("nft", "list", "table", "inet"):
            if argv[4] == "zap2_default":
                return RuntimeCommandResult(argv, 0, stdout="table inet zap2_default { }")
            return RuntimeCommandResult(argv, 1, stderr="No such table")
        if argv[:2] == ("nft", "-f"):
            executed_batch = True
        return RuntimeCommandResult(argv, 0)

    result = execute_runtime_owner_rules(project, "apply", "default", prepared.plan_id, runner=runner, allow_without_root=True)
    assert result.state == "conflict"
    assert "ownership cannot be proven" in result.message
    assert executed_batch is False


def _known_legacy_v04_table(owner_uid: int, qnum: int = 506) -> str:
    return (
        "table inet zap2_default {\n"
        "  chain local_out {\n"
        "    type filter hook output priority filter; policy accept;\n"
        f"    meta skuid {owner_uid} meta mark & 0x40000000 == 0 tcp dport {{ 80, 443 }} ct original packets 1-8 counter queue num {qnum} bypass comment \"zap2:zap2_default:tcp-out\"\n"
        "  }\n"
        "}\n"
    )


def test_stale_known_v04_table_can_be_explicitly_authorized_and_atomically_migrated(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    expected = create_runtime_apply_plan(project, "apply", "default")
    table_text = _known_legacy_v04_table(expected.owner_uid)

    def authorize_runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
        assert argv == ("nft", "list", "table", "inet", "zap2_default")
        return RuntimeCommandResult(argv, 0, stdout=table_text)

    receipt = authorize_stale_legacy_v04_table(project, "default", runner=authorize_runner, live_queue_numbers=set())
    assert receipt["state"] == "authorized"
    assert receipt["explicitOwnerConsent"] is True

    prepared = prepare_runtime_owner_rules_plan(project, "apply", "default")
    confirm_runtime_plan(project, prepared.plan_id)

    def apply_runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
        if argv[:4] == ("nft", "list", "table", "inet"):
            if argv[4] == "zap2_default":
                return RuntimeCommandResult(argv, 0, stdout=table_text)
            return RuntimeCommandResult(argv, 1, stderr="No such table")
        return RuntimeCommandResult(argv, 0)

    result = execute_runtime_owner_rules(project, "apply", "default", prepared.plan_id, runner=apply_runner, allow_without_root=True)
    assert result.state == "applied"
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert state["legacyNftTableMigrated"] == "zap2_default"
    transaction = Path(project / state["transactionPath"]).read_text(encoding="utf-8")
    assert transaction.splitlines()[0] == "delete table inet zap2_default"
    consent_path = project / ".zap2/runtime/migrations/default.legacy-v04-consent.json"
    consent = json.loads(consent_path.read_text(encoding="utf-8"))
    assert consent["state"] == "consumed"


def test_v04_migration_authorization_refuses_live_nfqueue_listener(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    expected = create_runtime_apply_plan(project, "apply", "default")
    table_text = _known_legacy_v04_table(expected.owner_uid, qnum=593)

    def runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
        return RuntimeCommandResult(argv, 0, stdout=table_text)

    receipt = authorize_stale_legacy_v04_table(project, "default", runner=runner, live_queue_numbers={593})
    assert receipt["state"] == "active"
    assert receipt["activeQueueNums"] == [593]
    assert not (project / ".zap2/runtime/migrations/default.legacy-v04-consent.json").exists()


def test_v04_migration_authorization_refuses_foreign_shape(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    expected = create_runtime_apply_plan(project, "apply", "default")
    foreign = (
        "table inet zap2_default {\n"
        "  chain local_out {\n"
        f"    meta skuid {expected.owner_uid} tcp dport 443 queue num 506 bypass comment \"foreign-rule\"\n"
        "  }\n"
        "}\n"
    )

    def runner(argv: tuple[str, ...]) -> RuntimeCommandResult:
        return RuntimeCommandResult(argv, 0, stdout=foreign)

    receipt = authorize_stale_legacy_v04_table(project, "default", runner=runner, live_queue_numbers=set())
    assert receipt["state"] == "conflict"
    assert not (project / ".zap2/runtime/migrations/default.legacy-v04-consent.json").exists()
