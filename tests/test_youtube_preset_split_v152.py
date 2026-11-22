"""Regression: static YouTube remains independent from auto discovery and preflight isn't a DPI verdict."""
from __future__ import annotations

from pathlib import Path

from zap2_gui.adapters.blockcheck_gui import diagnose_unscanned_candidate, parse_blockcheck_run_stats
from zap2_gui.models.service_targets import (
    DEFAULT_SERVICE_TARGET_PRESET_ID,
    SERVICE_TARGET_YOUTUBE_BASIC,
    SERVICE_TARGET_YOUTUBE_GOOGLEVIDEO_AUTO,
    get_service_target_preset,
    service_target_dynamic_phases,
    service_target_phase_chain,
    with_dynamic_hosts,
)

ROOT = Path(__file__).resolve().parents[1]
GUI = (ROOT / "gui/zap2_gui/widgets/blockcheck_lab.py").read_text(encoding="utf-8")


def test_static_default_is_unchanged_no_dynamic_discovery() -> None:
    baseline = get_service_target_preset(SERVICE_TARGET_YOUTUBE_BASIC)
    enhanced = get_service_target_preset(SERVICE_TARGET_YOUTUBE_GOOGLEVIDEO_AUTO)
    assert DEFAULT_SERVICE_TARGET_PRESET_ID == SERVICE_TARGET_YOUTUBE_BASIC
    assert baseline.targets == enhanced.targets == (
        "www.youtube.com", "youtube.com", "redirector.googlevideo.com", "i.ytimg.com"
    )
    assert service_target_dynamic_phases(SERVICE_TARGET_YOUTUBE_BASIC) == ()
    assert len(service_target_dynamic_phases(SERVICE_TARGET_YOUTUBE_GOOGLEVIDEO_AUTO)) == 1
    assert [phase.phase_id for phase in service_target_phase_chain(SERVICE_TARGET_YOUTUBE_BASIC)] == ["site", "video", "images"]
    assert [phase.phase_id for phase in service_target_phase_chain(SERVICE_TARGET_YOUTUBE_GOOGLEVIDEO_AUTO)] == ["site", "video", "images"]


def test_auto_injects_cdn_only_into_video_alternatives() -> None:
    phase = service_target_dynamic_phases(SERVICE_TARGET_YOUTUBE_GOOGLEVIDEO_AUTO)[0]
    host = "rr1---sn-xguxaxjvh-n8me.googlevideo.com"
    assert with_dynamic_hosts(list(phase.targets), phase, (host,)) == [host, "redirector.googlevideo.com"]
    assert "if not any(phase.dynamic == GOOGLEVIDEO_DYNAMIC_NODE" in GUI
    assert "service_target_dynamic_phases(options.service_target_preset_id)" in GUI
    assert "capture_browser_googlevideo(" in GUI


def test_dns_preflight_failure_is_unscanned_not_dpi_failure() -> None:
    stderr = (
        "[zap2] target DNS preflight FAILED: www.youtube.com has no IPv4 answer from mdig\n"
        "[zap2] Blockcheck was not started; firewall was not touched.\n"
    )
    stats = parse_blockcheck_run_stats("", stderr)
    assert stats.verdict == "no-observations"
    diagnostic = diagnose_unscanned_candidate(6, "", stderr, stats)
    assert diagnostic is not None and diagnostic.code == "dns-preflight-failed"
    assert "www.youtube.com" not in diagnostic.to_text()
    assert "failed" in diagnostic.to_text()


def test_sudo_failed_start_and_silent_process_failure_fail_closed() -> None:
    assert diagnose_unscanned_candidate(1, "", "sudo: no askpass program specified").code == "sudo-start-failed"
    assert diagnose_unscanned_candidate(-1, "", "").code == "upstream-start-failed"
    assert diagnose_unscanned_candidate(0, "", "").code == "no-strategy-evidence"


def test_real_strategy_attempt_never_misclassified_as_unscanned() -> None:
    output = """* script : standard/25-fake.sh
- curl_test_https_tls13 ipv4 www.youtube.com : nfqws2 --lua-desync=fake
UNAVAILABLE code=28
"""
    stats = parse_blockcheck_run_stats(output)
    assert stats.strategy_attempts == 1
    assert diagnose_unscanned_candidate(1, output, "", stats) is None


def test_gui_drains_pending_output_and_stops_unscanned_tournament() -> None:
    assert 'process.readAllStandardOutput()' in GUI
    assert 'process.readAllStandardError()' in GUI
    assert 'if not stopped and state.get("phase_gated_run") and unscanned is not None:' in GUI
    assert 'if error == QtCore.QProcess.ProcessError.FailedToStart' in GUI
    assert 'state["candidate_targets"] = []' in GUI
