"""DNS-gate and Blockcheck action layout regressions (no Qt/network required)."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

from zap2_gui.adapters.blockcheck_gui import diagnose_unscanned_candidate

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "tools/blockcheck_target_preflight.sh"


def _run_gate(tmp_path: Path, mdig_body: str | None, *, family: str = "4", getent_ok: bool = False):
    base = tmp_path / "core"
    (base / "mdig").mkdir(parents=True)
    if mdig_body is not None:
        binary = base / "mdig/mdig"
        binary.write_text("#!/bin/sh\n" + mdig_body + "\n", encoding="utf-8")
        binary.chmod(0o755)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    getent = fake_bin / "getent"
    getent.write_text("#!/bin/sh\nexit " + ("0" if getent_ok else "2") + "\n", encoding="utf-8")
    getent.chmod(0o755)
    marker = tmp_path / "upstream-ran"
    upstream = tmp_path / "upstream.sh"
    upstream.write_text(f"#!/bin/sh\necho yes > '{marker}'\n", encoding="utf-8")
    env = {**os.environ, "ZAPRET_BASE": str(base), "ZAP2_BLOCKCHECK_SCRIPT": str(upstream),
           "ZAP2_TARGET_HOSTS": "www.youtube.com", "IPVS": family,
           "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", "")}
    result = subprocess.run(["/bin/sh", str(GATE)], env=env, capture_output=True, text=True)
    return result, marker


def test_missing_mdig_is_not_misreported_as_network_block(tmp_path):
    result, marker = _run_gate(tmp_path, None)
    assert result.returncode == 7
    assert "mdig-missing" in result.stderr
    assert "firewall was not touched" in result.stderr
    assert not marker.exists()
    assert diagnose_unscanned_candidate(7, "", result.stderr).code == "mdig-missing"


def test_mdig_failure_with_working_nss_is_diagnostic_not_fallback(tmp_path):
    body = 'cat >/dev/null\necho "EAI_AGAIN (temporary resolver failure)" >&2\nexit 0'
    result, marker = _run_gate(tmp_path, body, getent_ok=True)
    assert result.returncode == 6
    assert "EAI_AGAIN" in result.stderr  # real mdig --verbose goes to raw candidate log
    assert "mdig-nss-mismatch" in result.stderr
    assert not marker.exists()  # getent must never override upstream mdig
    assert diagnose_unscanned_candidate(6, "", result.stderr).code == "mdig-nss-mismatch"


def test_mdig_and_nss_failed_requires_real_dns_remediation(tmp_path):
    result, marker = _run_gate(tmp_path, "cat >/dev/null\nexit 0", getent_ok=False)
    assert result.returncode == 6
    assert "resolver-unavailable" in result.stderr
    assert not marker.exists()
    assert diagnose_unscanned_candidate(6, "", result.stderr).code == "dns-resolver-unavailable"


def test_dual_family_must_not_succeed_with_only_ipv4(tmp_path):
    body = '''cat >/dev/null
case "$1" in --family=4) printf '203.0.113.5\\n' ;; esac'''
    result, marker = _run_gate(tmp_path, body, family="46", getent_ok=False)
    assert result.returncode == 6
    assert "IPv6" in result.stderr
    assert not marker.exists()


def test_good_mdig_starts_original_upstream(tmp_path):
    result, marker = _run_gate(tmp_path, "cat >/dev/null\nprintf '203.0.113.5\\n'", getent_ok=False)
    assert result.returncode == 0
    assert marker.exists()
    assert "target DNS preflight OK" in result.stdout


def test_blockcheck_grid_buttons_do_not_overlap():
    source = (ROOT / "gui/zap2_gui/widgets/blockcheck_lab.py").read_text(encoding="utf-8")
    assert "(cdp_collect_button, 10, 0, 1, 1)" in source
    assert "(cdp_finish_button, 10, 1, 1, 1)" in source
    assert "(cdp_reset_button, 11, 0, 1, 2)" in source
    matches = re.findall(r"actions_layout\.addWidget\(net_verdict_button, (\d+), (\d+), (\d+), (\d+)\)", source)
    assert matches == [("12", "0", "1", "2")]
    assert "actions_layout.addWidget(net_verdict_button, 10," not in source
