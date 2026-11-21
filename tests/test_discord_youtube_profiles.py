from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from zap2_gui.adapters.blockcheck_gui import _coverage_phases_in_policy_order
from zap2_gui.adapters.discord_media_probe import TransferResult, interpret, validate_attachment_url
from zap2_gui.adapters.googlevideo_node import REPORT_MAPPING_URL, parse_report_mapping, resolve_googlevideo_node
from zap2_gui.distribution import merge_hostlist_seed
from zap2_gui.models.service_icons import dns_badge, service_for_target_preset, services_for_preset, services_for_profile
from zap2_gui.models.service_targets import (
    SERVICE_TARGET_DISCORD_DESKTOP,
    SERVICE_TARGET_YOUTUBE_BASIC,
    hostlist_covers_host,
    service_target_dynamic_phases,
    service_target_phase_for_target,
    service_target_preset_missing_from_hostlist,
    with_dynamic_host,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOSTLIST = (ROOT / "profiles/hostlists/default.hosts").read_text(encoding="utf-8")
NODE = "rr1---sn-xguxaxjvh-n8me.googlevideo.com"


def test_hostlist_matching_follows_nfqws2_subdomain_rule() -> None:
    assert hostlist_covers_host(NODE, "googlevideo.com\n")
    assert hostlist_covers_host("googlevideo.com", "googlevideo.com\n")
    assert not hostlist_covers_host("notgooglevideo.com", "googlevideo.com\n")
    # `^` disables subdomain matching, as in zapret2 manual.
    assert not hostlist_covers_host(NODE, "^googlevideo.com\n")
    assert hostlist_covers_host("googlevideo.com", "^googlevideo.com\n")


def test_default_hostlist_covers_both_presets_and_dynamic_hosts() -> None:
    assert service_target_preset_missing_from_hostlist(SERVICE_TARGET_YOUTUBE_BASIC, DEFAULT_HOSTLIST) == ()
    assert service_target_preset_missing_from_hostlist(SERVICE_TARGET_DISCORD_DESKTOP, DEFAULT_HOSTLIST) == ()
    for host in (NODE, "russia1234.discord.media", "images-ext-2.discordapp.net", "discord-attachments-uploads-prd.storage.googleapis.com"):
        assert hostlist_covers_host(host, DEFAULT_HOSTLIST), host


def test_report_mapping_node_is_parsed_and_resolved_without_network() -> None:
    body = "203.0.113.0/24 => sn-xguxaxjvh-n8me : router: \"ae1.r1\" (pr:1)\n"
    assert parse_report_mapping(body) == "sn-xguxaxjvh-n8me"

    calls: list[str] = []

    def fetch(url: str, timeout: float) -> str:
        calls.append(url)
        return body

    node = resolve_googlevideo_node(fetch)
    assert calls == [REPORT_MAPPING_URL]
    assert node.ok and node.host == NODE


def test_report_mapping_failures_fall_back_honestly() -> None:
    cluster = resolve_googlevideo_node(lambda url, timeout: "203.0.113.0/24 => muc12s10 (pr:1)\n")
    assert cluster.ok and cluster.node == "sn-h0jelne7"

    def broken(url: str, timeout: float) -> str:
        raise OSError("timed out")

    failed = resolve_googlevideo_node(broken)
    assert not failed.ok
    assert "redirector.googlevideo.com" in failed.to_text()


def test_dynamic_googlevideo_node_joins_the_video_phase() -> None:
    (phase,) = service_target_dynamic_phases(SERVICE_TARGET_YOUTUBE_BASIC)
    assert phase.phase_id == "video"
    targets = with_dynamic_host(["www.youtube.com", "youtube.com", "redirector.googlevideo.com", "i.ytimg.com"], phase, NODE)
    assert targets == ["www.youtube.com", "youtube.com", NODE, "redirector.googlevideo.com", "i.ytimg.com"]
    # Not a googlevideo host: never injected.
    assert with_dynamic_host(["redirector.googlevideo.com"], phase, "example.com") == ["redirector.googlevideo.com"]
    assert service_target_phase_for_target(SERVICE_TARGET_YOUTUBE_BASIC, NODE).phase_id == "video"


def test_coverage_counts_resolved_node_as_video_alternative() -> None:
    data = {
        "targets": {
            "www.youtube.com": {"target": "www.youtube.com", "status": "available"},
            NODE: {"target": NODE, "status": "available"},
            "redirector.googlevideo.com": {"target": "redirector.googlevideo.com", "status": "unavailable"},
        }
    }
    phases = {phase["phaseId"]: phase for phase in _coverage_phases_in_policy_order(data, SERVICE_TARGET_YOUTUBE_BASIC)}
    assert phases["site"]["status"] == "passed"
    assert phases["video"]["status"] == "passed"
    assert phases["video"]["winner"]["target"] == NODE
    assert phases["images"]["status"] == "not-tested"


def test_discord_media_without_attachments_no_longer_passes_cdn_phase() -> None:
    data = {
        "targets": {
            "media.discordapp.net": {"target": "media.discordapp.net", "status": "available"},
            "cdn.discordapp.com": {"target": "cdn.discordapp.com", "status": "unavailable"},
        }
    }
    phases = {phase["phaseId"]: phase for phase in _coverage_phases_in_policy_order(data, SERVICE_TARGET_DISCORD_DESKTOP)}
    assert phases["media"]["status"] == "passed"
    assert phases["attachments"]["status"] == "blocked"


def test_attachment_url_must_be_discord_https() -> None:
    url = "https://cdn.discordapp.com/attachments/1/2/file.zip?ex=1&is=2&hm=3"
    assert validate_attachment_url(url) == url
    with pytest.raises(ValueError):
        validate_attachment_url("http://cdn.discordapp.com/attachments/1/2/file.zip")
    with pytest.raises(ValueError):
        validate_attachment_url("https://example.com/file.zip")


def test_body_stall_reads_as_volume_cap_not_as_dead_domain() -> None:
    ok_cdn = TransferResult(label="cdn", url="https://cdn.discordapp.com/x", host="cdn.discordapp.com", stage="ok", status=404)
    ok_media = TransferResult(label="media", url="https://media.discordapp.net/x", host="media.discordapp.net", stage="ok", status=404)
    stalled = TransferResult(
        label="attachment", url="https://cdn.discordapp.com/attachments/1", host="cdn.discordapp.com",
        stage="body", body_bytes=16 * 1024, stalled=True, error="нет данных 6 с",
    )
    assert "ограничение по объёму" in stalled.verdict()
    conclusion = " ".join(interpret([ok_media, ok_cdn, stalled], stalled.url))
    assert "не устаревший домен" in conclusion
    assert "внешнем браузере" in conclusion

    tls = TransferResult(label="cdn", url="https://cdn.discordapp.com/x", host="cdn.discordapp.com", stage="tls", error="The read operation timed out")
    assert "DPI по SNI" in tls.verdict()
    assert "две обязательные фазы" in " ".join(interpret([ok_media, tls], ""))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_untouched_hostlist_seed_is_replaced_on_upgrade(tmp_path: Path) -> None:
    package = tmp_path / "package.hosts"
    package.write_text("discord.com\ndiscord.app\n", encoding="utf-8")
    user = tmp_path / "user.hosts"
    user.write_text("discord.com\n", encoding="utf-8")
    offered = merge_hostlist_seed(package, user, _sha(user), [], "1.4.0")
    assert user.read_text(encoding="utf-8") == package.read_text(encoding="utf-8")
    assert offered == ["discord.com", "discord.app"]


def test_edited_hostlist_seed_gets_new_domains_once(tmp_path: Path) -> None:
    package = tmp_path / "package.hosts"
    package.write_text("discord.com\ndiscord.app\ndis.gd\n", encoding="utf-8")
    user = tmp_path / "user.hosts"
    user.write_text("discord.com\nmy.example\n", encoding="utf-8")
    offered = merge_hostlist_seed(package, user, "not-the-baseline", [], "1.4.0")
    text = user.read_text(encoding="utf-8")
    assert text.startswith("discord.com\nmy.example\n")
    assert "# добавлено обновлением z2guiflin 1.4.0" in text
    assert text.rstrip().endswith("discord.app\ndis.gd")

    # The owner deletes one offered domain; the next upgrade does not bring it back.
    user.write_text(text.replace("dis.gd\n", ""), encoding="utf-8")
    merge_hostlist_seed(package, user, "not-the-baseline", offered, "1.4.1")
    assert "dis.gd" not in user.read_text(encoding="utf-8")


def test_service_icons_follow_blockcheck_target_then_title_then_domains() -> None:
    assert services_for_preset("Blockcheck X / t #01", {"presetId": "discord-desktop"}) == ("discord",)
    assert services_for_preset("YouTube: fake · www.youtube.com · 21.10.2026") == ("youtube",)
    assert services_for_preset("Мой пресет", None, ["discord.com", "googlevideo.com"]) == ("discord", "youtube")
    assert services_for_preset("Мой пресет", None, ["example.com"]) == ()
    assert services_for_profile("TCP 443", ["discord.media"]) == ("discord",)
    assert service_for_target_preset("youtube-basic") == "youtube"
    for key in ("discord", "youtube"):
        assert (ROOT / f"gui/zap2_gui/assets/icons/services/{key}.svg").is_file()


def test_dns_badges_are_known_or_stable_initials() -> None:
    assert dns_badge("cloudflare", "Cloudflare") == ("CF", "#F38020")
    text, color = dns_badge("geohide-eu", "GeoHide EU")
    assert text == "GE"
    assert re.fullmatch(r"#[0-9A-F]{6}", color)
    assert dns_badge("geohide-eu", "GeoHide EU") == (text, color)
