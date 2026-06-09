from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v04_alpha_stage1_roadmap_documents_service_choice_goal() -> None:
    text = (ROOT / "docs" / "V04_ALPHA_PATCH_ROADMAP.md").read_text(encoding="utf-8")

    assert "v0.4-alpha_stage_1" in text
    assert "youtube-basic" in text
    assert "discord-desktop" in text
    assert "custom" in text
    assert "Одновременная работа YouTube и Discord" in text
    assert "не является критерием готовности" in text


def test_v04_alpha_stage1_roadmap_pins_discord_non_voice_seed() -> None:
    text = (ROOT / "docs" / "V04_ALPHA_PATCH_ROADMAP.md").read_text(encoding="utf-8")

    for domain in (
        "discord.com",
        "gateway.discord.gg",
        "cdn.discordapp.com",
        "discordapp.net",
        "discord.media",
        "media.discordapp.net",
        "updates.discord.com",
        "discord.gg",
    ):
        assert domain in text

    assert "Голосовые каналы не входят" in text
    assert "--filter-udp" in text
    assert "--filter-l7=stun,discord" in text
