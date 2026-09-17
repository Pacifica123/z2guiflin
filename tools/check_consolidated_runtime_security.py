#!/usr/bin/env python3
"""Self-contained regression checks for the consolidated Zap2 patch.

Uses only Python's standard library and project modules. It intentionally does
not require pytest, PyQt, root, nft, systemd, or network access so devctl can
validate the patch on a normal source checkout.
"""
from __future__ import annotations

import json
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))


def fail(message: str) -> None:
    raise AssertionError(message)


def copy_project(base: Path, name: str) -> Path:
    target = base / name
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns(
            ".git", ".zap2", ".pytest_cache", "__pycache__", "*.pyc", "*.pyo", "build", "dist"
        ),
    )
    return target


class FakeNft:
    def __init__(self) -> None:
        from zap2_gui.adapters.runtime_apply import RuntimeCommandResult
        self._result = RuntimeCommandResult
        self.exists = False
        self.text = ""
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: tuple[str, ...]):
        self.calls.append(argv)
        if argv[:4] == ("nft", "list", "table", "inet"):
            if not self.exists:
                return self._result(argv=argv, returncode=1, stderr="Error: No such file or directory")
            return self._result(argv=argv, returncode=0, stdout=self.text)
        if argv[:3] == ("nft", "--check", "-f"):
            return self._result(argv=argv, returncode=0)
        if argv[:2] == ("nft", "-f"):
            self.text = Path(argv[2]).read_text(encoding="utf-8")
            self.exists = not self.text.lstrip().startswith("delete table")
            return self._result(argv=argv, returncode=0)
        return self._result(argv=argv, returncode=0)


def fixture_cache(_config):
    return {
        "schemaVersion": 1,
        "fetchedAt": "2026-09-17T00:00:00Z",
        "sources": {},
        "dnsResolverExclusions": ["1.1.1.1/32"],
        "lists": {
            "inbound": ["203.0.113.0/24"],
            "outbound": ["198.51.100.4/32", "2001:db8::/48"],
        },
    }


def check_owner_and_reconciliation(base: Path) -> None:
    from zap2_gui.adapters.runtime_apply import create_runtime_apply_plan, reconcile_runtime_owner_rules

    a = copy_project(base, "owner-a")
    b = copy_project(base, "owner-b")
    pa = create_runtime_apply_plan(a, "apply", "default")
    pb = create_runtime_apply_plan(b, "apply", "default")
    if pa.owner_key == pb.owner_key or pa.nft_table == pb.nft_table:
        fail("different workspaces must not share runtime owner/table identity")

    nft = FakeNft()
    clean = reconcile_runtime_owner_rules(a, "default", runner=nft)
    if clean.state != "clean" or any(call[:2] == ("nft", "-f") for call in nft.calls):
        fail("reconciliation must be read-only and clean when owned table is absent")
    nft.exists = True
    nft.text = f'table inet {pa.nft_table} {{ chain owner_meta {{ counter comment "zap2-owner:foreign"; }} }}'
    conflict = reconcile_runtime_owner_rules(a, "default", runner=nft)
    if conflict.state != "conflict" or conflict.owner_marker_matches is not False:
        fail("foreign owner marker must be reported as conflict")


def check_session_identity(base: Path) -> None:
    from zap2_gui.adapters.runtime_session import _capture_process_identity, _record_matches_process

    source = Path("/bin/sleep")
    if not source.is_file():
        print("SKIP process identity live probe: /bin/sleep unavailable")
        return
    binary = base / "identity-sleep"
    shutil.copyfile(source, binary)
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    proc = subprocess.Popen([str(binary), "30"])
    try:
        identity = None
        for _ in range(50):
            identity = _capture_process_identity(proc.pid, binary)
            if identity:
                break
            time.sleep(0.01)
        if not identity:
            fail("could not capture process identity")
        if _record_matches_process({"pid": proc.pid, "binaryPath": str(binary)}):
            fail("legacy PID/path-only session record must fail closed")
        record = {"pid": proc.pid, "binaryPath": str(binary), "processIdentity": identity}
        if not _record_matches_process(record):
            fail("captured process identity must match its live process")
        wrong = dict(record)
        wrong["processIdentity"] = dict(identity, procStartTime=str(int(identity["procStartTime"]) + 1))
        if _record_matches_process(wrong):
            fail("wrong /proc starttime must not match")
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def check_theme_mapping() -> None:
    from zap2_gui.theme_profiles import LIGHT_COLORS, builtin_theme_profile, custom_stylesheet

    css = custom_stylesheet(builtin_theme_profile("light"))
    missing = [key for key, value in LIGHT_COLORS.items() if value not in css]
    if missing:
        fail("theme colors not wired into stylesheet: " + ", ".join(missing))
    for token in ("QFrame#contentSurface", "QToolTip", "QScrollBar::handle"):
        if token not in css:
            fail(f"missing semantic theme selector: {token}")

    # Widget-local literal colors bypassing the semantic map are prohibited.
    import re
    literal = re.compile(r"#[0-9A-Fa-f]{6}\b|rgba?\(")
    offenders: list[str] = []
    for path in sorted((ROOT / "gui/zap2_gui/widgets").glob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if literal.search(line):
                offenders.append(f"{path.name}:{number}")
    if offenders:
        fail("widget-local literal colors bypass theme mapping: " + ", ".join(offenders[:20]))


def check_security_blocklist(base: Path) -> None:
    from zap2_gui.adapters.security_blocklist import (
        apply_security_blocklist,
        refresh_security_blocklist,
        security_blocklist_timer_plan,
        set_security_blocklist_enabled,
        update_security_blocklist,
    )

    project = copy_project(base, "security")
    config_path = set_security_blocklist_enabled(project, True, inbound=False, outbound=True)
    update_security_blocklist(project, fetcher=fixture_cache)
    nft = FakeNft()
    applied = apply_security_blocklist(project, runner=nft, allow_without_root=True)
    if applied.state != "applied":
        fail("security blocklist fixture must apply")
    batches = [Path(call[2]).read_text(encoding="utf-8") for call in nft.calls if call[:2] == ("nft", "-f")]
    if not batches:
        fail("security blocklist did not produce nft batch")
    batch = batches[-1]
    required = (
        "hook output priority -10",
        "meta skuid",
        "198.51.100.4",
        "dns_exclusions4",
        'counter accept comment "zap2-security:dns-exclusion-outbound4"',
    )
    for token in required:
        if token not in batch:
            fail(f"security nft batch missing {token!r}")
    if "security_input" in batch or "queue num" in batch:
        fail("outbound-only security policy must not own input chain or NFQUEUE")

    refreshed = refresh_security_blocklist(
        project,
        runner=nft,
        fetcher=lambda _cfg: (_ for _ in ()).throw(OSError("offline")),
        allow_without_root=True,
    )
    if refreshed.state != "refreshed" or refreshed.used_last_known_good is not True:
        fail("failed refresh must retain validated last-known-good generation")

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    cfg["updateIntervalSeconds"] = 10800
    config_path.write_text(json.dumps(cfg), encoding="utf-8")
    _service_name, _timer_name, _service, timer = security_blocklist_timer_plan(project)
    if "OnUnitActiveSec=10800s" not in timer:
        fail("security timer must honor configured interval")


def check_blockcheck_contract() -> None:
    adapter = (ROOT / "gui/zap2_gui/adapters/blockcheck_gui.py").read_text(encoding="utf-8")
    wrapper = (ROOT / "tools/blockcheck_target_preflight.sh").read_text(encoding="utf-8")
    if '"SKIP_DNSCHECK": "1" if self.skip_dnscheck else "0"' not in adapter:
        fail("Blockcheck environment must expose explicit DNS precheck setting")
    if '"ZAP2_BLOCKCHECK_SCRIPT": str(script)' not in adapter:
        fail("Blockcheck must route upstream script through target-DNS wrapper")
    for token in ("target DNS preflight FAILED", "firewall was not touched", 'exec /bin/sh "$ZAP2_BLOCKCHECK_SCRIPT"'):
        if token not in wrapper:
            fail(f"Blockcheck DNS wrapper missing contract token: {token}")


def main() -> int:
    temp = Path(tempfile.mkdtemp(prefix="zap2-consolidated-check-"))
    try:
        check_owner_and_reconciliation(temp)
        check_session_identity(temp)
        check_theme_mapping()
        check_security_blocklist(temp)
        check_blockcheck_contract()
        print("Consolidated runtime/security/theme/Blockcheck self-check OK (no pytest/root/nft/network/PyQt required)")
        return 0
    except Exception as exc:
        print(f"SELF-CHECK FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
