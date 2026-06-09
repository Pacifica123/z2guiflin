from __future__ import annotations

import json
from pathlib import Path

from zap2_gui.adapters.discord_endpoint_discovery import (
    _parse_ss_output,
    discord_endpoint_discovery_plan_to_text,
    discord_endpoint_report_to_text,
    latest_discord_endpoint_snapshot,
)
from zap2_gui.app import main


def test_discord_endpoint_plan_is_read_only_and_cli_first() -> None:
    text = discord_endpoint_discovery_plan_to_text(seconds=42)

    assert "Discord updater endpoint discovery plan" in text
    assert "executes now: no" in text
    assert "requires sudo: no" in text
    assert "mutates firewall/services: no" in text
    assert "--discord-endpoint-watch --discord-endpoint-seconds 42" in text


def test_parse_ss_output_extracts_discord_tcp_and_udp_endpoints() -> None:
    text = '\n'.join(
        [
            'tcp ESTAB 0 0 10.0.0.2:51922 162.159.136.232:443 users:(("Discord",pid=1234,fd=77))',
            'udp ESTAB 0 0 10.0.0.2:52122 1.1.1.1:443 users:(("Discord",pid=1234,fd=78))',
            'tcp ESTAB 0 0 10.0.0.2:51923 203.0.113.1:443 users:(("Firefox",pid=222,fd=9))',
        ]
    )

    observations = _parse_ss_output(text)

    assert len(observations) == 2
    assert observations[0].proto == "tcp"
    assert observations[0].peer_host == "162.159.136.232"
    assert observations[0].peer_port == "443"
    assert observations[0].pid == "1234"
    assert observations[1].proto == "udp"


def test_latest_discord_endpoint_snapshot_reads_saved_json(tmp_path: Path) -> None:
    out = tmp_path / ".zap2" / "discord-discovery"
    out.mkdir(parents=True)
    (out / "endpoint-snapshot-20260609T010000Z.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "createdAt": "2026-06-09T01:00:00Z",
                "seconds": 3,
                "samples": 2,
                "processLines": ["1234 /opt/Discord/Discord"],
                "warnings": [],
                "observations": [
                    {
                        "proto": "tcp",
                        "local": "10.0.0.2:50000",
                        "peer": "162.159.136.232:443",
                        "process": 'users:(("Discord",pid=1234,fd=77))',
                        "pid": "1234",
                        "processName": "Discord",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    snapshot = latest_discord_endpoint_snapshot(tmp_path)
    assert snapshot is not None
    report = snapshot.to_text()
    assert "Discord endpoint discovery snapshot" in report
    assert "TCP 162.159.136.232:443" in report
    assert "requires sudo: no" in report
    assert "mutates firewall/services: no" in report


def test_discord_endpoint_report_handles_missing_snapshot(tmp_path: Path) -> None:
    text = discord_endpoint_report_to_text(root=tmp_path)

    assert "status: no saved snapshots" in text
    assert "--discord-endpoint-watch" in text


def test_discord_endpoint_cli_plan_is_available() -> None:
    assert main(["--discord-endpoint-plan", "--discord-endpoint-seconds", "5"]) == 0
