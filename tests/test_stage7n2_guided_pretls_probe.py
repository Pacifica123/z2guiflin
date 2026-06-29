from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from zap2_gui.adapters.discord_endpoint_discovery import DiscordEndpointObservation, DiscordEndpointSnapshot
from zap2_gui.adapters.discord_pretls_guided_probe import (
    read_nft_counters,
    run_discord_pretls_guided_probe,
)
from zap2_gui.adapters.workspace_profiles import select_workspace_strategy
from zap2_gui.app import main

ROOT = Path(__file__).resolve().parents[1]


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", ".zap2", "__pycache__", "*.pyc", ".pytest_cache"))
    return project


def _write_active_owner_rules(project: Path, *, qnum: int = 421) -> None:
    sessions = project / ".zap2" / "runtime" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / "default.owner-rules.json").write_text(
        json.dumps(
            {
                "state": "applied",
                "strategyId": "community-discord-pretls-diagnostic-pktdebug",
                "nftTable": "zap2_default",
                "nfqueueNum": qnum,
                "queuedTcpPorts": ["443", "5222"],
                "queuedUdpPorts": [],
                "queuedEdgeIps": ["162.159.128.233"],
                "capturePolicy": {"kind": "desktop-early-flow-v1"},
                "queueInputSynAck": True,
                "queueInputFinRst": True,
                "ownerUid": 1000,
                "ownerUidSource": "current-user",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_running_session(project: Path, *, qnum: int = 421) -> subprocess.Popen[bytes]:
    sessions = project / ".zap2" / "runtime" / "sessions"
    logs = project / ".zap2" / "runtime" / "logs"
    sessions.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    args = sessions / "default.nfqws2.args"
    stdout = logs / "default.nfqws2.stdout.log"
    stderr = logs / "default.nfqws2.stderr.log"
    debug = logs / "default.nfqws2.debug.log"
    args.write_text("--qnum=421\n--lua-desync=pktdebug\n", encoding="utf-8")
    stdout.write_text("startup\n", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    fake_binary = project / "fake-nfqws2-sleep"
    shutil.copyfile("/bin/sleep", fake_binary)
    fake_binary.chmod(0o755)
    proc = subprocess.Popen([str(fake_binary), "60"])
    record = {
        "schemaVersion": 1,
        "stage": "v0.3-beta_stage_11",
        "marker": "zap2-runtime-session-v1",
        "state": "running",
        "profileId": "default",
        "rootPath": str(project),
        "sessionPath": str(sessions / "default.session.json"),
        "planId": "runtime-default-community-discord-pretls-diagnostic-pktdebug-start-plan",
        "planHash": "abc123",
        "pid": proc.pid,
        "processGroupId": os.getpgrp(),
        "startedAt": "2026-06-09T16:00:00Z",
        "binaryPath": str(fake_binary),
        "cwd": str(project),
        "argv": [str(fake_binary), "60"],
        "runtimeArgs": ["--qnum=421", "--lua-desync=pktdebug"],
        "nfqueueNum": qnum,
        "nfqueueSource": "test",
        "argsPath": str(args),
        "pidfilePath": str(sessions / "default.nfqws2.pid"),
        "stdoutLogPath": str(stdout),
        "stderrLogPath": str(stderr),
        "debugLogPath": str(debug),
        "mutatesFirewallOrServicesNow": False,
        "managesServiceNow": False,
    }
    (sessions / "default.session.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return proc


def _nft_text(out_packets: int, out_bytes: int = 0, synack_packets: int = 0, udp_packets: int = 0) -> str:
    return f'''
table inet zap2_default {{
    chain local_out {{
        ip daddr {{ 162.159.128.233 }} tcp dport {{ 443, 5222 }} counter packets {out_packets} bytes {out_bytes} queue flags bypass to 421 comment "zap2:zap2_default:tcp-out" # handle 5
        udp dport {{ 80, 443-65535 }} counter packets {udp_packets} bytes 0 queue flags bypass to 421 comment "zap2:zap2_default:udp-out" # handle 6
    }}
    chain local_in {{
        ip saddr {{ 162.159.128.233 }} tcp sport {{ 443, 5222 }} counter packets {synack_packets} bytes 0 queue flags bypass to 421 comment "zap2:zap2_default:tcp-in-synack" # handle 8
        ip saddr {{ 162.159.128.233 }} tcp sport {{ 443, 5222 }} counter packets 0 bytes 0 queue flags bypass to 421 comment "zap2:zap2_default:tcp-in-fin-rst" # handle 11
    }}
}}
'''


def test_stage7n2_nft_counter_parser_supports_text_output() -> None:
    counters = read_nft_counters("zap2_default", runner=lambda table: (0, _nft_text(11, 660, 0), ""))

    assert counters.read_ok is True
    assert counters.tcp_out.packets == 11
    assert counters.tcp_out.bytes == 660
    assert counters.tcp_in_synack.packets == 0
    assert counters.udp_out.packets == 0


def test_stage7n2_guided_probe_refuses_when_workflow_not_running(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    select_workspace_strategy(project, "community-discord-pretls-diagnostic-pktdebug", profile_id="default")

    report = run_discord_pretls_guided_probe(project, interactive=False, wait_seconds=0, nft_runner=lambda table: (1, "", "should not run nft"))

    assert report.verdict == "V0_WORKFLOW_NOT_RUNNING"
    assert report.report_json_path.exists()
    assert report.report_md_path.exists()
    assert "owner-rules are not applied" in report.to_text()


def test_stage7n2_guided_probe_reports_out_hit_alive_logs_silent(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    select_workspace_strategy(project, "community-discord-pretls-diagnostic-pktdebug", profile_id="default")
    _write_active_owner_rules(project)
    proc = _write_running_session(project)
    calls = iter([(0, _nft_text(0), ""), (0, _nft_text(11, 660), "")])

    try:
        report = run_discord_pretls_guided_probe(
            project,
            interactive=False,
            wait_seconds=0,
            nft_runner=lambda table: next(calls),
            endpoint_watch_runner=None,
        )
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert report.verdict == "V5_OUT_HIT_ALIVE_LOGS_SILENT"
    assert report.counter_deltas["tcpOutPackets"].delta == 11
    assert report.session_state_before == "running"
    payload = json.loads(report.report_json_path.read_text(encoding="utf-8"))
    assert payload["counterDeltas"]["tcpOutPackets"]["delta"] == 11
    assert payload["execution"]["readOnly"] is True


def test_stage7n2_guided_probe_reports_log_activity(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    select_workspace_strategy(project, "community-discord-pretls-diagnostic-pktdebug", profile_id="default")
    _write_active_owner_rules(project)
    proc = _write_running_session(project)
    stdout = project / ".zap2" / "runtime" / "logs" / "default.nfqws2.stdout.log"
    calls = iter([(0, _nft_text(0), ""), (0, _nft_text(3, 180), "")])

    def sleep_and_log(_seconds: float) -> None:
        stdout.write_text(stdout.read_text(encoding="utf-8") + "pktdebug activity\n", encoding="utf-8")

    try:
        report = run_discord_pretls_guided_probe(
            project,
            interactive=False,
            wait_seconds=1,
            nft_runner=lambda table: next(calls),
            endpoint_watch_runner=None,
            sleep_func=sleep_and_log,
        )
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert report.verdict == "V6_LOG_ACTIVITY_WITH_OUT_HIT"
    assert report.log_deltas["stdout"].delta and report.log_deltas["stdout"].delta > 0



def _endpoint_snapshot(project: Path) -> DiscordEndpointSnapshot:
    return DiscordEndpointSnapshot(
        created_at="2026-06-13T07:20:13Z",
        seconds=1,
        samples=1,
        process_lines=("16790 /home/noir/.config/discord/Discord",),
        observations=(
            DiscordEndpointObservation(
                proto="tcp",
                local="192.168.0.100:60540",
                peer="162.159.128.233:443",
                state="ESTAB",
                recv_q="0",
                send_q="268",
                timer="on,35sec,10",
                pid="16790",
                process_name="Discord",
                matched_hosts=("updates.discord.com",),
            ),
        ),
        output_path=project / ".zap2" / "discord-discovery" / "endpoint-snapshot-test.json",
    )


def test_stage7n3_guided_probe_correlates_estab_sendq_endpoint(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    select_workspace_strategy(project, "community-discord-pretls-diagnostic-pktdebug", profile_id="default")
    _write_active_owner_rules(project)
    proc = _write_running_session(project)
    calls = iter([(0, _nft_text(0), ""), (0, _nft_text(8, 2032, synack_packets=1), "")])

    try:
        report = run_discord_pretls_guided_probe(
            project,
            interactive=False,
            wait_seconds=1,
            nft_runner=lambda table: next(calls),
            endpoint_watch_runner=lambda root, seconds: _endpoint_snapshot(project),
        )
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert report.verdict == "V9_ESTAB_WITH_SENDQ"
    assert report.endpoint_summary is not None
    assert report.endpoint_summary.established_with_sendq == 1
    assert report.endpoint_summary.capture_matches == 1
    payload = json.loads(report.report_json_path.read_text(encoding="utf-8"))
    assert payload["stage"] == "v0.4-alpha_stage7n3"
    assert payload["endpointSummary"]["establishedWithSendQ"] == 1




def _write_windows_v3_owner_rules(project: Path, *, qnum: int = 421) -> None:
    sessions = project / ".zap2" / "runtime" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / "default.owner-rules.json").write_text(
        json.dumps(
            {
                "state": "applied",
                "strategyId": "windows-all-tcp-udp-v3-2-linux-bridge",
                "nftTable": "zap2_default",
                "nfqueueNum": qnum,
                "queuedTcpPorts": ["80", "443-65535"],
                "queuedUdpPorts": ["80", "443-65535"],
                "queuedEdgeIps": [],
                "capturePolicy": {"kind": "windows-all-tcp-udp-v3-2-owner-wide-v1"},
                "queueInputSynAck": True,
                "queueInputFinRst": True,
                "ownerUid": 1000,
                "ownerUidSource": "current-user",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_stage7n3_guided_probe_accepts_windows_v3_bridge_and_udp_counter(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    select_workspace_strategy(project, "windows-all-tcp-udp-v3-2-linux-bridge", profile_id="default")
    _write_windows_v3_owner_rules(project)
    proc = _write_running_session(project)
    calls = iter([(0, _nft_text(0, udp_packets=0), ""), (0, _nft_text(0, udp_packets=7), "")])

    try:
        report = run_discord_pretls_guided_probe(
            project,
            interactive=False,
            wait_seconds=0,
            nft_runner=lambda table: next(calls),
            endpoint_watch_runner=None,
        )
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert report.strategy_compatible is True
    assert report.active_strategy_id == "windows-all-tcp-udp-v3-2-linux-bridge"
    assert report.verdict == "V3_ONLY_UDP_COUNTER_DELTA"
    assert report.counter_deltas["udpOutPackets"].delta == 7
    payload = json.loads(report.report_json_path.read_text(encoding="utf-8"))
    assert payload["countersAfter"]["udpOut"]["packets"] == 7

def test_stage7n2_cli_exposes_guided_probe_no_wait(capsys) -> None:
    assert main(["--runtime-discord-pretls-guided-probe", "--pretls-probe-no-wait"]) == 0
    output = capsys.readouterr().out
    assert "Discord pre-TLS guided probe" in output
    assert "Discord pre-TLS guided probe result" in output
    assert "report json:" in output
