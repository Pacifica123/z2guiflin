from __future__ import annotations

from pathlib import Path

from zap2_gui.adapters import discord_dns_edge_diagnostics as dns_edge
from zap2_gui.adapters.discord_dns_edge_diagnostics import (
    DnsEdgeDiagnosis,
    DnsEdgeProbe,
    DnsEdgeResolution,
    parse_dns_address_output,
    discord_dns_edge_plan_to_text,
    discord_dns_edge_check_to_text,
)
from zap2_gui.app import main


def test_parse_dns_address_output_handles_getent_dig_and_nslookup() -> None:
    text = "\n".join(
        [
            "162.159.128.233 STREAM updates.discord.com",
            "162.159.128.233",
            "Address: 162.159.135.232",
            "not-an-ip",
        ]
    )

    assert parse_dns_address_output(text) == ("162.159.128.233", "162.159.135.232")


def test_dns_edge_plan_explains_dns_limit() -> None:
    text = discord_dns_edge_plan_to_text(hosts="updates.discord.com", resolvers="system,google", timeout_seconds=2)

    assert "Discord DNS edge diagnosis plan" in text
    assert "executes now: no" in text
    assert "mutates DNS settings/hosts/firewall/services: no" in text
    assert "DNS can help only" in text
    assert "system, google" in text


def test_dns_edge_report_marks_all_timeout_as_not_dns_only() -> None:
    diagnosis = DnsEdgeDiagnosis(
        created_at="2026-06-09T12:00:00Z",
        hosts=("updates.discord.com",),
        resolvers=("system",),
        timeout_seconds=3,
        resolutions=(DnsEdgeResolution("updates.discord.com", "system", addresses=("162.159.128.233",)),),
        probes=(DnsEdgeProbe("updates.discord.com", "system", "", "162.159.128.233", ok=False, error="timed out"),),
    )

    text = diagnosis.to_text()

    assert "no-working-edge-observed" in text
    assert "all-timeout edges" in text
    assert "no reachable Discord Cloudflare edge" in text


def test_dns_edge_report_marks_reachable_edge_as_dns_steering_candidate() -> None:
    diagnosis = DnsEdgeDiagnosis(
        created_at="2026-06-09T12:00:00Z",
        hosts=("updates.discord.com",),
        resolvers=("system", "google"),
        timeout_seconds=3,
        resolutions=(
            DnsEdgeResolution("updates.discord.com", "system", addresses=("162.159.128.233",)),
            DnsEdgeResolution("updates.discord.com", "google", server="8.8.8.8", addresses=("203.0.113.10",)),
        ),
        probes=(
            DnsEdgeProbe("updates.discord.com", "system", "", "162.159.128.233", ok=False, error="timed out"),
            DnsEdgeProbe("updates.discord.com", "google", "8.8.8.8", "203.0.113.10", ok=True),
        ),
    )

    text = diagnosis.to_text()

    assert "dns-edge-can-help" in text
    assert "ok: 203.0.113.10:443 via google @8.8.8.8" in text
    assert "DNS/hosts steering may be useful" in text


def test_dns_edge_check_can_be_mocked_and_writes_snapshot(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        dns_edge,
        "resolve_dns_edges",
        lambda hosts, resolvers: (DnsEdgeResolution(hosts[0], resolvers[0], addresses=("203.0.113.10",)),),
    )
    monkeypatch.setattr(
        dns_edge,
        "probe_tcp_edge",
        lambda host, resolver, server, ip, port=443, timeout=3.0: DnsEdgeProbe(host, resolver, server, ip, port=port, ok=True),
    )

    text = discord_dns_edge_check_to_text(root=tmp_path, hosts="updates.discord.com", resolvers="system", timeout_seconds=1)

    assert "verdict: at least one reachable edge observed" in text
    assert list((tmp_path / ".zap2" / "discord-discovery").glob("dns-edge-diagnosis-*.json"))


def test_discord_dns_edge_cli_plan_is_available() -> None:
    assert main(["--discord-dns-edge-plan", "--discord-dns-edge-hosts", "updates.discord.com"]) == 0
