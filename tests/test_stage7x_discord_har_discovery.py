from __future__ import annotations

import json
import zipfile
from pathlib import Path

from zap2_gui.app import main
from zap2_gui.adapters.discord_har_discovery import (
    analyze_discord_har,
    discord_har_analyze_to_text,
    discord_har_plan_to_text,
    discord_har_report_to_text,
    latest_discord_har_summary,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_default_hostlist(tmp_path: Path) -> None:
    hostlists = tmp_path / "profiles" / "hostlists"
    hostlists.mkdir(parents=True)
    hostlists.joinpath("default.hosts").write_text(
        "\n".join(
            [
                "discord.com",
                "gateway.discord.gg",
                "cdn.discordapp.com",
                "media.discordapp.net",
                "discordapp.net",
                "discord.media",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _sample_har() -> dict[str, object]:
    return {
        "log": {
            "entries": [
                {
                    "request": {
                        "method": "GET",
                        "url": "https://discord.com/api/v9/users/@me?token=SHOULD_NOT_APPEAR",
                        "headers": [
                            {"name": "Authorization", "value": "super-secret-token"},
                            {"name": "Cookie", "value": "session=super-secret-cookie"},
                            {"name": "X-Super-Properties", "value": "secret-properties"},
                        ],
                    },
                    "response": {"status": 200, "headers": []},
                    "serverIPAddress": "37.203.37.93",
                },
                {
                    "request": {"method": "GET", "url": "wss://gateway.discord.gg/?v=9", "headers": []},
                    "response": {"status": 101, "headers": []},
                    "_webSocketMessages": [{"type": "send", "data": "payload-must-not-be-stored"}],
                    "serverIPAddress": "37.203.37.93",
                },
                {
                    "request": {
                        "method": "GET",
                        "url": "https://cdn.discordapp.com/avatars/123456789012345678/abcdef0123456789abcdef0123456789.png?size=128",
                        "headers": [],
                    },
                    "response": {"status": 200, "headers": []},
                },
                {
                    "request": {
                        "method": "PUT",
                        "url": "https://discord-attachments-uploads-prd.storage.googleapis.com/files/123456789012345678/blob?X-Goog-Signature=super-secret-signature",
                        "headers": [],
                    },
                    "response": {"status": 200, "headers": []},
                },
                {
                    "request": {"method": "GET", "url": "wss://c-hel02-859c9068.discord.media/?v=7", "headers": []},
                    "response": {"status": 101, "headers": []},
                    "_webSocketMessages": [],
                },
            ]
        }
    }


def test_har_analyzer_redacts_secret_bearing_values_and_queries(tmp_path: Path) -> None:
    _write_default_hostlist(tmp_path)
    har_path = tmp_path / "discord.har"
    har_path.write_text(json.dumps(_sample_har()), encoding="utf-8")

    summary = analyze_discord_har(har_path, root=tmp_path)
    text = summary.to_text()
    payload = json.dumps(summary.to_dict(), ensure_ascii=False)

    assert summary.har_entry_count == 5
    assert summary.discord_related_entry_count == 5
    assert summary.websocket_entry_count == 2
    assert "authorization" in summary.sensitive_header_names
    assert "cookie" in summary.sensitive_header_names
    assert "x-super-properties" in summary.sensitive_header_names
    for forbidden in (
        "super-secret-token",
        "super-secret-cookie",
        "secret-properties",
        "SHOULD_NOT_APPEAR",
        "X-Goog-Signature",
        "super-secret-signature",
        "payload-must-not-be-stored",
        "37.203.37.93",
        "123456789012345678",
    ):
        assert forbidden not in text
        assert forbidden not in payload
    assert "/avatars/{id}/{token}.png" in text


def test_har_analyzer_classifies_coverage_and_optional_hosts(tmp_path: Path) -> None:
    _write_default_hostlist(tmp_path)
    har_path = tmp_path / "discord.har"
    har_path.write_text(json.dumps(_sample_har()), encoding="utf-8")

    summary = analyze_discord_har(har_path, root=tmp_path)
    hosts = {item.host: item for item in summary.host_summaries}

    assert hosts["discord.com"].category == "app-api"
    assert hosts["discord.com"].covered_by_default_hostlist is True
    assert hosts["gateway.discord.gg"].category == "gateway"
    assert hosts["c-hel02-859c9068.discord.media"].category == "media-relay"
    assert hosts["c-hel02-859c9068.discord.media"].covered_by_default_hostlist is True
    upload = hosts["discord-attachments-uploads-prd.storage.googleapis.com"]
    assert upload.category == "attachment-upload"
    assert upload.covered_by_default_hostlist is False
    assert upload in summary.optional_discovery_hosts()


def test_har_analyze_writes_sanitized_summary_and_reads_latest(tmp_path: Path) -> None:
    _write_default_hostlist(tmp_path)
    har_path = tmp_path / "discord.har"
    har_path.write_text(json.dumps(_sample_har()), encoding="utf-8")

    text = discord_har_analyze_to_text(str(har_path), root=tmp_path)
    assert "Discord HAR discovery summary" in text
    assert "attachment-upload" in text

    latest = latest_discord_har_summary(tmp_path)
    assert latest is not None
    assert latest.output_path is not None
    saved = latest.output_path.read_text(encoding="utf-8")
    assert "super-secret" not in saved
    assert "X-Goog-Signature" not in saved
    assert "Discord HAR discovery summary" in discord_har_report_to_text(root=tmp_path)


def test_har_analyzer_accepts_zip_with_har(tmp_path: Path) -> None:
    _write_default_hostlist(tmp_path)
    zip_path = tmp_path / "discord.har.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("capture/discord.har", json.dumps(_sample_har()))

    summary = analyze_discord_har(zip_path, root=tmp_path)

    assert summary.har_entry_count == 5
    assert summary.host_summaries[0].request_count >= 1


def test_har_cli_plan_and_report_are_available(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    assert "Discord HAR discovery plan" in discord_har_plan_to_text()
    assert main(["--discord-har-plan"]) == 0


def test_har_analyzer_keeps_only_protocol_and_error_categories(tmp_path: Path) -> None:
    _write_default_hostlist(tmp_path)
    har = {
        "log": {
            "entries": [
                {
                    "request": {"method": "GET", "url": "https://updates.discord.com/failing", "headers": []},
                    "response": {"status": 0, "httpVersion": "h3", "headers": []},
                    "_error": "net::ERR_CONNECTION_RESET secret diagnostic detail",
                }
            ]
        }
    }
    har_path = tmp_path / "protocol.har"
    har_path.write_text(json.dumps(har), encoding="utf-8")

    summary = analyze_discord_har(har_path, root=tmp_path)
    host = summary.host_summaries[0]
    payload = json.dumps(summary.to_dict(), ensure_ascii=False)

    assert host.schemes == ("https",)
    assert host.http_versions == ("h3",)
    assert host.l7_hints == ("quic",)
    assert host.transport_hints == ("udp",)
    assert host.error_count == 1
    assert host.failed_status_count == 1
    assert host.error_categories == ("reset-or-closed",)
    assert "secret diagnostic detail" not in payload
