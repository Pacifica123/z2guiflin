from __future__ import annotations

import pytest

from zap2_gui.adapters.blockcheck_gui import BlockcheckOptions
from zap2_gui.models.service_targets import (
    DEFAULT_BLOCKCHECK_TARGET_STRING,
    DISCORD_DESKTOP_TARGETS,
    SERVICE_TARGET_CUSTOM,
    SERVICE_TARGET_DISCORD_DESKTOP,
    SERVICE_TARGET_YOUTUBE_BASIC,
    YOUTUBE_BASIC_TARGETS,
    get_service_target_preset,
    list_service_target_presets,
    normalize_service_targets,
    service_target_string,
)


def test_service_target_registry_has_required_stage2_presets() -> None:
    preset_ids = tuple(item.preset_id for item in list_service_target_presets())

    assert preset_ids == (
        SERVICE_TARGET_YOUTUBE_BASIC,
        SERVICE_TARGET_DISCORD_DESKTOP,
        SERVICE_TARGET_CUSTOM,
    )


def test_youtube_basic_preset_preserves_v03_baseline_default() -> None:
    preset = get_service_target_preset(SERVICE_TARGET_YOUTUBE_BASIC)
    opts = BlockcheckOptions()

    assert preset.targets == ("youtube.com", "www.youtube.com")
    assert YOUTUBE_BASIC_TARGETS == preset.targets
    assert DEFAULT_BLOCKCHECK_TARGET_STRING == "youtube.com www.youtube.com"
    assert opts.normalized_domains() == preset.targets
    assert opts.to_env()["DOMAINS"] == "youtube.com www.youtube.com"


def test_discord_desktop_preset_contains_non_voice_seed_targets() -> None:
    preset = get_service_target_preset(SERVICE_TARGET_DISCORD_DESKTOP)

    assert preset.non_voice
    assert preset.targets == DISCORD_DESKTOP_TARGETS
    assert "discord.com" in preset.targets
    assert "gateway.discord.gg" in preset.targets
    assert "cdn.discordapp.com" in preset.targets
    assert "discord.media" in preset.targets
    assert "media.discordapp.net" in preset.targets
    assert "updates.discord.com" in preset.targets
    assert "discord.gg" in preset.targets
    assert service_target_string(SERVICE_TARGET_DISCORD_DESKTOP).startswith("updates.discord.com stable.dl2.discordapp.net")
    assert preset.policy.mode == "ordered-target-chain"
    assert preset.policy.order_mode == "order-important"


def test_custom_preset_is_manual_and_has_no_fixed_targets() -> None:
    preset = get_service_target_preset(SERVICE_TARGET_CUSTOM)

    assert preset.is_custom
    assert preset.targets == ()
    with pytest.raises(ValueError, match="does not have a fixed target string"):
        service_target_string(SERVICE_TARGET_CUSTOM)


def test_service_target_validation_rejects_shell_like_targets() -> None:
    with pytest.raises(ValueError, match="Недопустимый service target"):
        normalize_service_targets("discord.com;rm -rf /tmp/nope")

    with pytest.raises(ValueError, match="Недопустимый service target"):
        BlockcheckOptions(domains="gateway.discord.gg $(whoami)").to_env()


def test_service_target_validation_rejects_duplicate_targets() -> None:
    with pytest.raises(ValueError, match="duplicate service target"):
        normalize_service_targets("discord.com Discord.com")


def test_unknown_service_target_preset_reports_available_choices() -> None:
    with pytest.raises(ValueError, match="youtube-basic"):
        get_service_target_preset("discord-voice")
