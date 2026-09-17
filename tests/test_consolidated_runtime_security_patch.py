from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from zap2_gui.adapters.core_provenance import verify_core_bundle, write_core_build_receipt
from zap2_gui.adapters.runtime_apply import RuntimeCommandResult, create_runtime_apply_plan, execute_runtime_owner_rules, prepare_runtime_owner_rules_plan, reconcile_runtime_owner_rules
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


def test_core_provenance_receipt_and_compat_mismatch(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    binary = project / "core/zapret2/nfq2/nfqws2"
    binary.write_bytes(b"synthetic-binary")
    binary.chmod(0o755)
    write_core_build_receipt(project, [binary], "nfqws2")
    assert verify_core_bundle(project, binary).state == "verified"
    header = project / "core/zapret2/nfq2/nfqws.h"
    header.write_text(header.read_text(encoding="utf-8").replace("#define LUA_COMPAT_VER\t5", "#define LUA_COMPAT_VER\t999"), encoding="utf-8")
    status = verify_core_bundle(project, binary)
    assert status.state == "mismatch"
    assert "compatibility mismatch" in status.message


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
