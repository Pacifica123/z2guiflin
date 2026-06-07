from __future__ import annotations

from pathlib import Path

import pytest

from zap2_gui.adapters.blockcheck_gui import (
    BlockcheckOptions,
    blockcheck_build_plan_to_text,
    blockcheck_plan_to_text,
    blockcheck_preflight,
    build_blockcheck_command,
    current_blockcheck_worker_identity,
    BlockcheckPreparationError,
    execute_blockcheck_with_gui_sudo,
    parse_blockcheck_summary,
    prepare_blockcheck_execution,
)
from zap2_gui.app import main
from zap2_gui.models.navigation import default_navigation_sections

ROOT = Path(__file__).resolve().parents[1]


def test_blockcheck_options_are_batch_and_youtube_oriented() -> None:
    opts = BlockcheckOptions()
    env = opts.to_env()

    assert env["BATCH"] == "1"
    assert env["DOMAINS"] == "youtube.com www.youtube.com"
    assert env["ENABLE_HTTP"] == "0"
    assert env["ENABLE_HTTPS_TLS12"] == "1"
    assert env["ENABLE_HTTPS_TLS13"] == "1"
    assert env["ENABLE_HTTP3"] == "1"
    assert env["SKIP_DNSCHECK"] == "1"
    assert env["SCANLEVEL"] == "quick"


def test_blockcheck_options_reject_shell_like_targets() -> None:
    with pytest.raises(ValueError):
        BlockcheckOptions(domains="youtube.com;rm -rf /tmp/nope").to_env()


def test_blockcheck_command_uses_sudo_askpass_and_state_dir() -> None:
    command = build_blockcheck_command(root=ROOT, options=BlockcheckOptions(domains="youtube.com"))

    assert command.argv[:3] == ("sudo", "-A", "env")
    assert "/bin/sh" in command.argv
    assert str(ROOT / "core" / "zapret2" / "blockcheck2.sh") in command.argv
    assert "SUDO_ASKPASS" in command.env_overrides
    assert any(item.startswith("ZAPRET_RW=") and "/.zap2/blockcheck/rw" in item for item in command.argv)
    assert any(item == "DOMAINS=youtube.com" for item in command.argv)
    assert any(item.startswith("WS_UID=") for item in command.argv)
    assert any(item.startswith("WS_GID=") for item in command.argv)
    assert "blockcheck worker uid/gid:" in command.to_text()
    assert command.log_path == ROOT / ".zap2" / "blockcheck" / "logs" / "last-blockcheck.txt"


def test_blockcheck_plan_is_explicit_about_temporary_firewall_mutation() -> None:
    text = blockcheck_plan_to_text(root=ROOT, options=BlockcheckOptions(domains="youtube.com"))

    assert "Blockcheck preflight" in text
    assert "Blockcheck GUI plan" in text
    assert "mutates firewall temporarily: yes" in text
    assert "executes now: no" in text
    assert "stores password: no" in text


def test_blockcheck_summary_parser_extracts_strategy_lines() -> None:
    stdout = """
!!!!! check_domain_https_tls12: working strategy found for ipv4 youtube.com : nfqws2 --filter-tcp=443 --dpi-desync=fake !!!!!

* SUMMARY
check_domain_https_tls12 ipv4 youtube.com : nfqws2 --filter-tcp=443 --dpi-desync=fake
check_domain_http3 ipv4 youtube.com : nfqws2 --filter-udp=443 --dpi-desync=fake

Please note this SUMMARY does not guarantee a magic pill.
"""
    parsed = parse_blockcheck_summary(stdout)

    assert parsed == (
        "check_domain_https_tls12: working strategy found for ipv4 youtube.com : nfqws2 --filter-tcp=443 --dpi-desync=fake",
        "check_domain_https_tls12 ipv4 youtube.com : nfqws2 --filter-tcp=443 --dpi-desync=fake",
        "check_domain_http3 ipv4 youtube.com : nfqws2 --filter-udp=443 --dpi-desync=fake",
    )


def test_navigation_marks_diagnostics_as_blockcheck_backed() -> None:
    diagnostics = [section for section in default_navigation_sections() if section.key == "diagnostics"][0]
    assert diagnostics.ready_state == "blockcheck-backed"
    assert "Blockcheck" in diagnostics.purpose


def test_blockcheck_preflight_is_read_only() -> None:
    text = blockcheck_preflight(ROOT).to_text()
    assert "read-only: yes" in text
    assert "executes now: no" in text


def test_blockcheck_cli_plan_returns_success() -> None:
    assert main(["--blockcheck-plan", "--blockcheck-domains", "youtube.com"]) == 0


def test_blockcheck_build_plan_is_local_and_unprivileged() -> None:
    text = blockcheck_build_plan_to_text(root=ROOT)

    assert "Blockcheck prerequisites build plan" in text
    assert "target: all" in text
    assert "nfq2/nfqws2" in text
    assert "mdig/mdig" in text
    assert "requires sudo: no" in text
    assert "mutates services/firewall: no" in text
    assert "contains upstream installer script: no" in text


def test_blockcheck_run_stops_before_sudo_when_local_binaries_are_missing(tmp_path: Path) -> None:
    core = tmp_path / "core" / "zapret2"
    core.mkdir(parents=True)
    (core / "blockcheck2.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    result = execute_blockcheck_with_gui_sudo(root=tmp_path, options=BlockcheckOptions(domains="youtube.com"))

    assert result.returncode == 6
    assert "blockcheck preflight failed" in result.skipped_reason
    assert "sudo сейчас не запускался" in result.skipped_reason
    assert "nfqws2 binary" in result.stderr
    assert "mdig binary" in result.stderr
    assert "uses sudo askpass: no (skipped before sudo)" in result.to_text()


def test_blockcheck_has_no_arbitrary_overall_timeout_by_default() -> None:
    opts = BlockcheckOptions()
    command = build_blockcheck_command(root=ROOT, options=opts)

    assert opts.timeout_seconds == 0
    assert "overall timeout: none; owner stops manually" in command.to_text()


def test_prepare_blockcheck_execution_raises_result_before_sudo_when_missing_binaries(tmp_path: Path) -> None:
    core = tmp_path / "core" / "zapret2"
    core.mkdir(parents=True)
    (core / "blockcheck2.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    with pytest.raises(BlockcheckPreparationError) as raised:
        prepare_blockcheck_execution(root=tmp_path, options=BlockcheckOptions(domains="youtube.com"))

    assert raised.value.result.returncode == 6
    assert "sudo сейчас не запускался" in raised.value.result.skipped_reason
    assert "nfqws2 binary" in raised.value.result.stderr


def test_blockcheck_lab_widget_uses_qprocess_live_streaming() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "QtCore.QProcess" in source
    assert "readyReadStandardOutput" in source
    assert "Остановить" in source
    assert "execute_blockcheck_with_gui_sudo" not in source


def test_blockcheck_worker_identity_prefers_sudo_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUDO_UID", "1000")
    monkeypatch.setenv("SUDO_GID", "1000")

    identity = current_blockcheck_worker_identity()
    command = build_blockcheck_command(root=ROOT, options=BlockcheckOptions(domains="youtube.com"))

    assert identity.pair == "1000:1000"
    assert identity.source == "SUDO_UID/SUDO_GID"
    assert "WS_UID=1000" in command.argv
    assert "WS_GID=1000" in command.argv
    assert "blockcheck worker uid/gid: 1000:1000" in command.to_text()


def test_blockcheck_preflight_checks_lua_support_files() -> None:
    preflight = blockcheck_preflight(ROOT)

    labels = {item.label for item in preflight.items}
    assert "lua support files" in labels
    assert "lua/zapret-lib.lua" in preflight.to_text()


def test_blockcheck_lab_suppresses_expected_crash_message_after_owner_stop() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert 'if state.get("stopped_by_user")' in source
    assert "Qt reports a SIGTERM/SIGKILL stopped process as CrashExit" in source
