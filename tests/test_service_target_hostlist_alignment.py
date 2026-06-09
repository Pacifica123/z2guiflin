from __future__ import annotations

from pathlib import Path

import pytest

from zap2_gui.adapters.runtime_apply import create_runtime_apply_plan
from zap2_gui.models.service_targets import (
    SERVICE_TARGET_CUSTOM,
    SERVICE_TARGET_DISCORD_DESKTOP,
    SERVICE_TARGET_YOUTUBE_BASIC,
    hostlist_entries_from_text,
    service_target_host_token,
    service_target_preset_missing_from_hostlist,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOSTLIST = ROOT / "profiles" / "hostlists" / "default.hosts"


def test_hostlist_parser_normalizes_comments_urls_and_duplicates() -> None:
    text = """
    # comment
    HTTPS://Gateway.Discord.GG/some/path # inline comment
    *.media.discordapp.net
    media.discordapp.net
    youtube.com
    """

    assert service_target_host_token("https://Gateway.Discord.GG/api?v=1") == "gateway.discord.gg"
    assert hostlist_entries_from_text(text) == (
        "gateway.discord.gg",
        "media.discordapp.net",
        "youtube.com",
    )


def test_default_hostlist_covers_stage4_service_presets() -> None:
    text = DEFAULT_HOSTLIST.read_text(encoding="utf-8")

    assert service_target_preset_missing_from_hostlist(SERVICE_TARGET_YOUTUBE_BASIC, text) == ()
    assert service_target_preset_missing_from_hostlist(SERVICE_TARGET_DISCORD_DESKTOP, text) == ()
    assert "gateway.discord.gg" in text
    assert "cdn.discordapp.com" in text
    assert "media.discordapp.net" in text


def test_custom_preset_has_no_fixed_hostlist_coverage_contract() -> None:
    with pytest.raises(ValueError, match="custom service target preset"):
        service_target_preset_missing_from_hostlist(SERVICE_TARGET_CUSTOM, "example.com")


def test_runtime_apply_plan_uses_hostlist_aligned_with_discord_targets() -> None:
    plan = create_runtime_apply_plan(root=ROOT, action="apply", profile_id="default")

    assert plan.hostlists == ("profiles/hostlists/default.hosts",)
    hostlist_text = (ROOT / plan.hostlists[0]).read_text(encoding="utf-8")
    assert service_target_preset_missing_from_hostlist(SERVICE_TARGET_DISCORD_DESKTOP, hostlist_text) == ()
    payload = plan.to_payload()
    assert payload["hostlists"] == ["profiles/hostlists/default.hosts"]
    assert payload["queuedTcpPorts"] == ["80", "443"]
    assert payload["queuedUdpPorts"] == []
