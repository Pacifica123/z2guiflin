from __future__ import annotations

import json
from pathlib import Path

from zap2_gui.adapters.discord_endpoint_discovery import (
    DnsHostResolution,
    DiscordEndpointObservation,
    DiscordEndpointSnapshot,
    _parse_getent_ahosts,
    _parse_ss_output,
    discord_endpoint_discovery_plan_to_text,
    discord_netlog_plan_to_text,
    latest_discord_endpoint_snapshot,
)
from zap2_gui.app import main
from zap2_gui.models.service_targets import service_target_phase_chain


def test_parse_ss_tanop_syn_sent_state_timer_and_pid() -> None:
    text = 'SYN-SENT 0 1 192.168.0.100:36158 162.159.138.232:443 users:(("Discord",pid=82950,fd=120)) timer:(on,1.014sec,5)'

    observations = _parse_ss_output(text, default_proto="tcp")

    assert len(observations) == 1
    item = observations[0]
    assert item.proto == "tcp"
    assert item.state == "SYN-SENT"
    assert item.peer_host == "162.159.138.232"
    assert item.peer_port == "443"
    assert item.pid == "82950"
    assert item.timer == "on,1.014sec,5"


def test_parse_getent_deduplicates_addresses() -> None:
    text = "162.159.138.232 STREAM updates.discord.com\n162.159.138.232 DGRAM updates.discord.com\n162.159.135.232 STREAM updates.discord.com\n"

    assert _parse_getent_ahosts(text) == ("162.159.138.232", "162.159.135.232")


def test_snapshot_report_matches_syn_sent_to_dns_host() -> None:
    snapshot = DiscordEndpointSnapshot(
        created_at="2026-06-09T11:00:00Z",
        seconds=30,
        samples=3,
        dns_map=(DnsHostResolution("updates.discord.com", ("162.159.138.232",)),),
        observations=(
            DiscordEndpointObservation(
                proto="tcp",
                local="192.168.0.100:36158",
                peer="162.159.138.232:443",
                state="SYN-SENT",
                timer="on,1.014sec,5",
                process='users:(("Discord",pid=82950,fd=120))',
                pid="82950",
                process_name="Discord",
                sightings=4,
                matched_hosts=("updates.discord.com",),
            ),
        ),
    )

    report = snapshot.to_text()

    assert "states: SYN-SENT=4" in report
    assert "hosts=updates.discord.com" in report
    assert "TCP SYN-SENT was observed" in report
    assert "pre-TLS TCP connectivity" in report


def test_latest_snapshot_reads_schema_v2_dns_and_state(tmp_path: Path) -> None:
    out = tmp_path / ".zap2" / "discord-discovery"
    out.mkdir(parents=True)
    (out / "endpoint-snapshot-20260609T110000Z.json").write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "createdAt": "2026-06-09T11:00:00Z",
                "seconds": 30,
                "samples": 2,
                "processLines": [],
                "dnsMap": [{"hostname": "updates.discord.com", "addresses": ["162.159.138.232"], "error": ""}],
                "warnings": [],
                "observations": [
                    {
                        "proto": "tcp",
                        "local": "192.168.0.100:36158",
                        "peer": "162.159.138.232:443",
                        "state": "SYN-SENT",
                        "timer": "on,1.014sec,5",
                        "process": 'users:(("Discord",pid=82950,fd=120))',
                        "pid": "82950",
                        "processName": "Discord",
                        "sightings": 2,
                        "matchedHosts": ["updates.discord.com"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    snapshot = latest_discord_endpoint_snapshot(tmp_path)

    assert snapshot is not None
    assert snapshot.dns_map[0].hostname == "updates.discord.com"
    assert snapshot.observations[0].state == "SYN-SENT"
    assert snapshot.observations[0].matched_hosts == ("updates.discord.com",)


def test_endpoint_plan_mentions_socket_state_and_dns_mapping() -> None:
    text = discord_endpoint_discovery_plan_to_text(seconds=30)

    assert "captures socket state: yes" in text
    assert "matches endpoint IPs to known Discord hostnames" in text
    assert "SYN-SENT" in text


def test_netlog_plan_is_privacy_aware_and_cli_available() -> None:
    text = discord_netlog_plan_to_text()

    assert "executes now: no" in text
    assert "potentially yes" in text
    assert "discord --log-net-log" in text
    assert main(["--discord-netlog-plan"]) == 0


def test_discord_updater_phase_prioritizes_observed_metadata_host() -> None:
    phases = service_target_phase_chain("discord-desktop")

    assert phases[0].phase_id == "updater"
    assert phases[0].targets[0] == "updates.discord.com"
    assert "stable.dl2.discordapp.net" in phases[0].targets
