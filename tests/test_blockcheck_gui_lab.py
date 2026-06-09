from __future__ import annotations

from pathlib import Path
import json
import shutil

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
    parse_blockcheck_run_stats,
    parse_blockcheck_summary,
    prepare_blockcheck_execution,
    export_blockcheck_available_strategies,
    parse_blockcheck_available_strategies,
    BlockcheckPortPrecheckMonitor,
    BLOCKCHECK_DEAD_TARGET_GUARD_AUTO_STOP,
    BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY,
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


def test_blockcheck_options_emit_dead_target_guard_env() -> None:
    opts = BlockcheckOptions(domains="youtube.com", dead_target_guard=BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY)
    env = opts.to_env()

    assert env["ZAP2_DEAD_TARGET_GUARD"] == BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY
    assert "dead-target guard: observe-only" in build_blockcheck_command(root=ROOT, options=opts).to_text()
    assert BlockcheckOptions(domains="youtube.com").dead_target_guard == BLOCKCHECK_DEAD_TARGET_GUARD_AUTO_STOP


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



def test_blockcheck_run_stats_parser_summarizes_partial_owner_stopped_log() -> None:
    stdout = """
* port block tests ipv4 youtube.com:443
142.251.127.136 does not connect. netcat code 1
142.251.127.190 connects

* curl_test_https_tls12 ipv4 youtube.com
* script : standard/15-misc.sh
- curl_test_https_tls12 ipv4 youtube.com : nfqws2 --payload=tls_client_hello --lua-desync=tcpseg:pos=0,1
curl: (28) Connection timed out after 3002 milliseconds
UNAVAILABLE code=28
- curl_test_https_tls12 ipv4 youtube.com : nfqws2 --payload=tls_client_hello --lua-desync=tcpseg:pos=0,midsld
!!!!! AVAILABLE !!!!!
- curl_test_https_tls12 ipv4 youtube.com : nfqws2 --payload=tls_client_hello --lua-desync=tcpseg:pos=1
"""
    stderr = "QSettings::value: Empty key passed\n"

    stats = parse_blockcheck_run_stats(stdout, stderr)

    assert stats.strategy_attempts == 3
    assert stats.unavailable == 1
    assert stats.available == 1
    assert stats.unknown == 1
    assert stats.port_connects == 1
    assert stats.port_failures == 1
    assert not stats.port_precheck_dead
    assert "verdict:" in stats.to_text()
    assert stats.top_unavailable_reasons[0] == ("curl code 28: connection timed out", 1)
    assert "curl_test_https_tls12 ipv4 youtube.com" in stats.to_text()
    assert "Qt/QSettings empty key warning" in stats.to_text()


def test_blockcheck_stats_detect_dead_port_precheck_verdict() -> None:
    stdout = """
* port block tests ipv4 youtube.com:443
142.251.127.136 does not connect. netcat code 1
142.251.127.190 does not connect. netcat code 1

* curl_test_https_tls12 ipv4 youtube.com
* script : standard/15-misc.sh
- curl_test_https_tls12 ipv4 youtube.com : nfqws2 --payload=tls_client_hello
curl: (28) Connection timed out after 3002 milliseconds
UNAVAILABLE code=28
"""

    stats = parse_blockcheck_run_stats(stdout)

    assert stats.port_precheck_dead
    assert "port-precheck-dead-target" in stats.to_text()


def test_blockcheck_port_precheck_monitor_requests_evidence_based_skip() -> None:
    monitor = BlockcheckPortPrecheckMonitor(target="youtube.com")

    reason = monitor.feed_stdout(
        "* port block tests ipv4 youtube.com:443\n"
        "142.251.127.136 does not connect. netcat code 1\n"
        "142.251.127.190 does not connect. netcat code 1\n"
        "\n"
        "* curl_test_https_tls12 ipv4 youtube.com\n"
    )

    assert "port-precheck-dead-target for youtube.com" in reason
    assert monitor.dead_target


def test_blockcheck_last_log_writer_includes_run_statistics(tmp_path: Path) -> None:
    command = build_blockcheck_command(root=ROOT, options=BlockcheckOptions(domains="youtube.com"))
    command = command.__class__(
        options=command.options,
        argv=command.argv,
        cwd=command.cwd,
        env_overrides=command.env_overrides,
        script_env=command.script_env,
        log_path=tmp_path / "last-blockcheck.txt",
        backend=command.backend,
        worker_identity=command.worker_identity,
    )
    from zap2_gui.adapters.blockcheck_gui import write_blockcheck_last_log

    stdout = """
* script : standard/15-misc.sh
- curl_test_https_tls12 ipv4 youtube.com : nfqws2 --payload=tls_client_hello
curl: (28) Connection timed out after 3002 milliseconds
UNAVAILABLE code=28
"""
    write_blockcheck_last_log(command, stdout, "", footer="return code: 15")

    text = command.log_path.read_text(encoding="utf-8")
    assert "===== BLOCKCHECK RUN STATISTICS =====" in text
    assert "strategy checks seen: 1" in text
    assert "curl code 28: connection timed out: 1" in text
    assert "===== GUI FINISH =====" in text
    assert not (tmp_path / "latest-successful-blockcheck.txt").exists()

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
    assert "■ Stop" in source
    assert "candidate_targets" in source
    assert "Auto-skip dead target" in source
    assert "BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY" in source
    assert "BlockcheckPortPrecheckMonitor" in source
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


def test_blockcheck_lab_footer_uses_parsed_run_statistics() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "parse_blockcheck_run_stats" in source
    assert "Blockcheck run statistics" in source or "stats.to_text()" in source
    assert "footer=footer_text" in source



def _copy_project_for_blockcheck(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))
    return project


def test_blockcheck_available_strategy_parser_keeps_concrete_runtime_args() -> None:
    stdout = """
* script : standard/15-misc.sh
- curl_test_https_tls12 ipv4 youtube.com : nfqws2 --payload=tls_client_hello --lua-desync=tcpseg:pos=0,1
!!!!! AVAILABLE !!!!!
- curl_test_http3 ipv4 youtube.com : nfqws2 --payload=quic_initial --lua-desync=fake
!!!!! AVAILABLE !!!!!
"""
    available = parse_blockcheck_available_strategies(stdout)

    assert len(available) == 2
    assert available[0].command.startswith("nfqws2 --payload=tls_client_hello")
    assert "--filter-tcp=443" in available[0].runtime_args
    assert "--filter-l7=tls" in available[0].runtime_args
    assert "--filter-udp=443" in available[1].runtime_args
    assert "--lua-init=@core/zapret2/lua/zapret-lib.lua" in available[0].runtime_args


def test_blockcheck_export_available_strategies_updates_generated_catalog(tmp_path: Path) -> None:
    project = _copy_project_for_blockcheck(tmp_path)
    log_path = project / ".zap2" / "blockcheck" / "logs" / "last-blockcheck.txt"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        """
Blockcheck GUI plan
domains: youtube.com, www.youtube.com

===== STDOUT =====
* script : standard/15-misc.sh
- curl_test_https_tls12 ipv4 youtube.com : nfqws2 --payload=tls_client_hello --lua-desync=tcpseg:pos=0,1
!!!!! AVAILABLE !!!!!
- curl_test_https_tls12 ipv4 youtube.com : nfqws2 --payload=tls_client_hello --lua-desync=tcpseg:pos=0,midsld
curl: (28) Connection timed out after 3002 milliseconds
UNAVAILABLE code=28
- curl_test_https_tls13 ipv4 youtube.com : nfqws2 --payload=tls_client_hello --lua-desync=multidisorder:pos=midsld
!!!!! AVAILABLE !!!!!
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = export_blockcheck_available_strategies(project)

    assert result.ok
    assert len(result.generated) == 2
    catalog = json.loads((project / "strategies" / "catalog.json").read_text(encoding="utf-8"))
    for item in result.generated:
        rel = item.path.relative_to(project).as_posix()
        assert rel in catalog["strategyFiles"]
        data = json.loads(item.path.read_text(encoding="utf-8"))
        assert data["id"] == item.strategy_id
        assert data["sourcePreset"]["name"] == "Blockcheck generated AVAILABLE strategy"
        assert "--filter-tcp=443" in data["runtimeArgs"]
        assert "--lua-init=@core/zapret2/lua/zapret-antidpi.lua" in data["runtimeArgs"]


def test_blockcheck_export_prefers_latest_successful_log_over_failed_last(tmp_path: Path) -> None:
    project = _copy_project_for_blockcheck(tmp_path)
    logs = project / ".zap2" / "blockcheck" / "logs"
    logs.mkdir(parents=True)
    (logs / "latest-successful-blockcheck.txt").write_text(
        """
Blockcheck GUI plan
domains: www.youtube.com

===== STDOUT =====
* script : standard/15-misc.sh
- curl_test_https_tls12 ipv4 www.youtube.com : nfqws2 --payload=tls_client_hello --lua-desync=tcpseg:pos=0,1
!!!!! AVAILABLE !!!!!
""".strip() + "\n",
        encoding="utf-8",
    )
    (logs / "last-blockcheck.txt").write_text(
        """
Blockcheck GUI plan
domains: youtube.com

===== STDOUT =====
* port block tests ipv4 youtube.com:443
142.251.127.136 does not connect. netcat code 1
142.251.127.190 does not connect. netcat code 1

* curl_test_https_tls12 ipv4 youtube.com
* script : standard/15-misc.sh
- curl_test_https_tls12 ipv4 youtube.com : nfqws2 --payload=tls_client_hello
curl: (28) Connection timed out after 3002 milliseconds
UNAVAILABLE code=28
""".strip() + "\n",
        encoding="utf-8",
    )

    result = export_blockcheck_available_strategies(project)

    assert result.ok
    assert result.source_log.name == "latest-successful-blockcheck.txt"
    assert result.target_label == "www.youtube.com"


def test_blockcheck_lab_exposes_export_button() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "Создать стратегии" in source
    assert "export_blockcheck_available_strategies" in source


def test_blockcheck_cli_target_preset_expands_discord_domains(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--blockcheck-plan", "--blockcheck-target-preset", "discord-desktop"]) == 0

    out = capsys.readouterr().out
    assert "domains: stable.dl2.discordapp.net, updates.discord.com, discord.com" in out
    assert "ordered domains: stable.dl2.discordapp.net, updates.discord.com, discord.com" in out
    assert "service coverage policy: ordered-target-chain; order: order-important" in out
    assert "DOMAINS=stable.dl2.discordapp.net updates.discord.com discord.com" in out


def test_blockcheck_cli_custom_preset_requires_manual_domains(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--blockcheck-plan", "--blockcheck-target-preset", "custom"]) == 2

    err = capsys.readouterr().err
    assert "custom требует явный --blockcheck-domains" in err


def test_blockcheck_lab_widget_exposes_service_target_selector() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "target_preset_combo" in source
    assert "blockcheckServiceTargetPreset" in source
    assert "list_service_target_presets" in source
    assert "SERVICE_TARGET_CUSTOM" in source
    assert "domains_edit.setReadOnly(True)" in source
    assert "state[\"custom_targets\"]" in source
