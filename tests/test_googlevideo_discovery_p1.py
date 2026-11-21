"""Offline regression: fresh YouTube CDN discovery → phase targets → Blockcheck."""

from __future__ import annotations

from pathlib import Path

from zap2_gui.adapters.googlevideo_node import (
    REPORT_MAPPING_URL,
    REPORT_MAPPING_URLS,
    WATCH_URLS,
    cluster_to_node,
    discover_googlevideo_candidates,
    extract_googlevideo_hosts,
    normalize_googlevideo_host,
    parse_report_mapping,
)
from zap2_gui.models.service_targets import (
    SERVICE_TARGET_YOUTUBE_BASIC,
    service_target_dynamic_phases,
    with_dynamic_hosts,
)

HOST1 = "rr1---sn-h0jelne7.googlevideo.com"
HOST2 = "rr2---sn-xguxaxjvh-n8me.googlevideo.com"
HOST3 = "rr4---sn-gvnuxaxjvh-o8ge.googlevideo.com"
HOST4 = "rr5---sn-a5mekn7k.googlevideo.com"
ROOT = Path(__file__).resolve().parents[1]


def test_cluster_translation_and_untrusted_mapping_validation() -> None:
    assert cluster_to_node("muc12s10") == "sn-h0jelne7"
    assert parse_report_mapping("192.0.2.0/24 => muc12s10 (pr:1)\n") == "sn-h0jelne7"
    assert parse_report_mapping("192.0.2.0/24 => sn-xguxaxjvh-n8me : router\n") == "sn-xguxaxjvh-n8me"
    for bad in ("", "invalid cluster", "server.example.com", "muc12s10;evil", "not_a_node"):
        assert cluster_to_node(bad) == ""
    assert parse_report_mapping("192.0.2.0 => https://evil.invalid/?x=1\n") == ""
    assert normalize_googlevideo_host("redirector.googlevideo.com") == ""
    assert normalize_googlevideo_host("notgooglevideo.com") == ""
    assert normalize_googlevideo_host("rr1---sn-h0jelne7.googlevideo.com.evil.tld") == ""
    assert normalize_googlevideo_host("RR1---SN-H0JELNE7.GOOGLEVIDEO.COM") == HOST1


def test_extract_from_watch_page_handles_escaped_formats_and_deduplicates_without_secrets() -> None:
    page = (
        '"serverAbrStreamingUrl":"https:\\/\\/RR2---SN-XGUXAXJVH-N8ME.googlevideo.com/videoplayback?sig=SECRET" '
        '"url":"https%3A%2F%2Frr4---sn-gvnuxaxjvh-o8ge.googlevideo.com%2Fvideoplayback%3Fsig%3DTOKEN" '
        '"other":"https://rr2---sn-xguxaxjvh-n8me.googlevideo.com/videoplayback" '
        '"injected":"https://badgooglevideo.com/videoplayback"'
    )
    assert extract_googlevideo_hosts(page) == (HOST2, HOST3)
    assert extract_googlevideo_hosts('"nope":"redirector.googlevideo.com"') == ()


def test_mapping_and_player_hosts_feed_video_phase_in_source_order() -> None:
    visited = []

    def fetch(url: str, timeout: float) -> str:
        visited.append(url)
        if url == REPORT_MAPPING_URL:
            return "203.0.113.0/24 => muc12s10\n"
        if url == WATCH_URLS[0]:
            return f"https://{HOST2}/videoplayback?signature=PRIVATE https://{HOST3}/videoplayback"
        raise AssertionError(f"unexpected URL: {url}")

    discovery = discover_googlevideo_candidates(fetch, lambda _host, _timeout: True)
    assert visited == [REPORT_MAPPING_URL, WATCH_URLS[0]]
    assert discovery.hosts == (HOST2, HOST3, HOST1)
    assert [c.source for c in discovery.candidates] == ["player", "player", "redirector"]
    assert all(c.dns == "resolved" for c in discovery.candidates)
    assert "PRIVATE" not in discovery.to_text()

    (phase,) = service_target_dynamic_phases(SERVICE_TARGET_YOUTUBE_BASIC)
    original = ["www.youtube.com", "youtube.com", "redirector.googlevideo.com", "i.ytimg.com"]
    expected = ["www.youtube.com", "youtube.com", *discovery.hosts, "redirector.googlevideo.com", "i.ytimg.com"]
    assert with_dynamic_hosts(original, phase, discovery.hosts) == expected
    assert with_dynamic_hosts(original, phase, discovery.hosts + (HOST2,)) == expected
    assert with_dynamic_hosts(list(phase.targets), phase, discovery.hosts) == [*discovery.hosts, "redirector.googlevideo.com"]
    assert with_dynamic_hosts(original, phase, ("evil.test",)) == original


def test_bounded_discovery_preserves_mapping_slot_for_its_own_node() -> None:
    def fetch(url: str, timeout: float) -> str:
        if url in REPORT_MAPPING_URLS:
            return "=> muc12s10"
        return " ".join((HOST2, HOST3, HOST4, "rr6---sn-someshard.googlevideo.com"))

    discovery = discover_googlevideo_candidates(fetch, lambda _host, _timeout: True)
    assert discovery.hosts == (HOST2, HOST3, HOST4, HOST1)
    assert len(discovery.hosts) == 4


def test_mapping_fallback_dns_reject_and_unchecked_are_distinct() -> None:
    def fetch(url: str, timeout: float) -> str:
        if url == REPORT_MAPPING_URL:
            raise OSError("blocked")
        if url == REPORT_MAPPING_URLS[1]:
            return "203.0.113.0 => muc12s10"
        raise OSError("watch page not reachable")

    unknown = discover_googlevideo_candidates(fetch, lambda _host, _timeout: None)
    assert unknown.hosts == (HOST1,)
    assert unknown.candidates[0].dns == "unchecked"
    assert "не удалось проверить" in unknown.to_text()

    rejected = discover_googlevideo_candidates(fetch, lambda _host, _timeout: False)
    assert rejected.hosts == ()
    assert rejected.rejected_dns == (HOST1,)
    assert "не добавлены" in rejected.to_text()
    assert "статические альтернативы" in rejected.to_text()


def test_all_sources_down_and_cancel_are_safe_no_privileged_mutations() -> None:
    visits = []

    def fetch(url: str, timeout: float) -> str:
        visits.append(url)
        raise TimeoutError("connection failed")

    no_hosts = discover_googlevideo_candidates(fetch, lambda _host, _timeout: True)
    assert no_hosts.hosts == ()
    assert len(visits) == len(REPORT_MAPPING_URLS) + len(WATCH_URLS)
    assert "не обнаружено" in no_hosts.to_text()

    calls = []
    cancelled = discover_googlevideo_candidates(
        lambda url, _: calls.append(url) or "=> muc12s10",
        lambda _host, _timeout: True,
        cancelled=lambda: True,
    )
    assert cancelled.hosts == ()
    assert calls == []


def test_gui_discovery_is_async_and_stop_cancels_before_privileged_scan() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/blockcheck_lab.py").read_text(encoding="utf-8")
    assert "start_background_task(" in source
    assert "discover_googlevideo_candidates(" in source
    assert "cancelled=cancel.is_set" in source
    assert 'state.get("discovery_token") is not token' in source
    assert "if options.skip_dnscheck else None" in source
    assert 'state["discovery_pending"] = False' in source
    assert "cancel.set()" in source
    assert "with_dynamic_hosts(" in source
    assert "resolve_googlevideo_node()" not in source


def test_unresolved_mapping_fills_reserved_slot_with_spare_player_node() -> None:
    def fetch(url: str, timeout: float) -> str:
        if url in REPORT_MAPPING_URLS:
            return "=> muc12s10"
        return " ".join((HOST2, HOST3, HOST4, "rr6---sn-someshard.googlevideo.com"))

    result = discover_googlevideo_candidates(fetch, lambda host, _: host != HOST1)
    assert result.hosts == (HOST2, HOST3, HOST4, "rr6---sn-someshard.googlevideo.com")
    assert result.rejected_dns == (HOST1,)
