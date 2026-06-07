from __future__ import annotations

from pathlib import Path

import pytest

from zap2_gui.adapters.blockcheck_gui import (
    BlockcheckOptions,
    blockcheck_plan_to_text,
    blockcheck_preflight,
    build_blockcheck_command,
    parse_blockcheck_summary,
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
