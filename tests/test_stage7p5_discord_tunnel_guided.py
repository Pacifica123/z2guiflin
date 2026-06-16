from __future__ import annotations

import stat
from pathlib import Path

from zap2_gui.adapters.discord_tunnel import (
    SUPPORTED_LAUNCH_MODES,
    discord_tunnel_guided_run_to_text,
    discord_tunnel_https_probe_to_text,
    discord_tunnel_tun_plan_to_text,
    tunnel_connection_import_vless_to_text,
)
from zap2_gui.app import main

SAMPLE_VLESS = (
    "vless://11111111-2222-4333-8444-555555555555@example.net:8080"
    "?security=&encryption=none&host=www.example.org&headerType=http&type=tcp#Sample%20Profile"
)


def _executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_stage7p5_launch_modes_and_tun_plan_are_exposed(tmp_path: Path) -> None:
    assert "socks-env-only" in SUPPORTED_LAUNCH_MODES
    assert "socks-flag-only" in SUPPORTED_LAUNCH_MODES
    text = discord_tunnel_tun_plan_to_text(root=tmp_path)
    assert "status: plan-only" in text
    assert "applies firewall/services now: no" in text
    assert (tmp_path / ".zap2" / "tunnel" / "reports" / "default.tun-tproxy-plan.json").exists()


def test_https_probe_requires_running_tunnel_session(tmp_path: Path) -> None:
    try:
        discord_tunnel_https_probe_to_text(root=tmp_path)
    except ValueError as exc:
        assert "Tunnel session" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected missing session error")


def test_guided_run_auto_prepares_confirms_starts_and_reports_without_sudo(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = _executable(tmp_path / "xray", "#!/bin/sh\nsleep 30\n")
    fake_discord = _executable(tmp_path / "discord", "#!/bin/sh\nsleep 30\n")

    text = discord_tunnel_guided_run_to_text(
        root=tmp_path,
        core_binary=str(fake_core),
        discord_binary=str(fake_discord),
        launch_mode="socks-env-only",
        observe_seconds=0,
        updater_result="unknown",
        interactive=False,
    )

    assert "Discord tunnel guided run result" in text
    assert "plan auto-confirmed: runtime-default-discord-tunnel-socks-start-plan" in text
    assert "https probe verdict: T1_HTTPS_THROUGH_SOCKS_FAILED" in text
    assert "requires sudo: no" in text
    assert (tmp_path / ".zap2" / "tunnel" / "runtime" / "default.session.json").exists()
    assert (tmp_path / ".zap2" / "tunnel" / "runtime" / "default.discord-session.json").exists()
    reports = list((tmp_path / ".zap2" / "tunnel" / "reports").glob("default.guided-run-*.json"))
    assert reports


def test_cli_accepts_stage7p5_tun_plan() -> None:
    assert main(["--discord-tunnel-tun-plan"]) == 0
