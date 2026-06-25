from __future__ import annotations

import stat
from pathlib import Path

from zap2_gui.adapters.discord_tunnel import (
    SUPPORTED_LAUNCH_MODES,
    discord_launch_through_socks_to_text,
    discord_stop_launched_to_text,
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

FAKE_SOCKS_CORE = r'''#!/usr/bin/env python3
import json
import socket
import sys
import time
from pathlib import Path

config = None
for index, arg in enumerate(sys.argv):
    if arg in {"-config", "-c"} and index + 1 < len(sys.argv):
        config = Path(sys.argv[index + 1])
        break
port = 19993
if config and config.exists():
    data = json.loads(config.read_text(encoding="utf-8"))
    port = int(data["inbounds"][0]["port"])

server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", port))
server.listen(16)
server.settimeout(0.2)
started = time.time()
while time.time() - started < 30:
    try:
        conn, _addr = server.accept()
    except socket.timeout:
        continue
    with conn:
        data = conn.recv(3)
        if data == b"\x05\x01\x00":
            conn.sendall(b"\x05\x00")
            try:
                conn.recv(4096)
            except OSError:
                pass
'''


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


def test_guided_run_auto_prepares_confirms_starts_and_blocks_launch_when_socks_is_not_ready(tmp_path: Path) -> None:
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
    assert "Discord launch through SOCKS: blocked" in text
    assert "requires sudo: no" in text
    assert (tmp_path / ".zap2" / "tunnel" / "runtime" / "default.session.json").exists()
    assert not (tmp_path / ".zap2" / "tunnel" / "runtime" / "default.discord-session.json").exists()
    reports = list((tmp_path / ".zap2" / "tunnel" / "reports").glob("default.guided-run-*.json"))
    assert reports


def test_stage8a_launch_through_socks_accepts_flatpak_command_string(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = _executable(tmp_path / "xray", FAKE_SOCKS_CORE)
    fake_flatpak = _executable(tmp_path / "flatpak", "#!/bin/sh\necho flatpak-noise\nsleep 30\n")
    fake_discord_app = tmp_path / "com.discordapp.Discord"
    fake_discord_app.write_text("marker", encoding="utf-8")

    from zap2_gui.adapters.discord_tunnel import discord_tunnel_plan_to_text, discord_tunnel_start_to_text
    from zap2_gui.adapters.runtime_state import confirm_runtime_plan

    old_path = __import__("os").environ.get("PATH", "")
    __import__("os").environ["PATH"] = f"{tmp_path}:{old_path}"
    try:
        discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=19993)
        plan_id = "runtime-default-discord-tunnel-socks-start-plan"
        confirm_runtime_plan(root=tmp_path, plan_id=plan_id)
        discord_tunnel_start_to_text(root=tmp_path, confirm_plan_id=plan_id)
        text = discord_launch_through_socks_to_text(
            root=tmp_path,
            discord_binary="flatpak run com.discordapp.Discord",
            launch_mode="socks-flag-only",
        )
    finally:
        __import__("os").environ["PATH"] = old_path

    assert "Discord launch through SOCKS: started" in text
    assert "discord command: flatpak run com.discordapp.Discord" in text
    assert "flatpak command: yes" in text
    assert "discord stdout:" in text
    assert "--proxy-server=socks5://127.0.0.1:19993" in text

    stop_text = discord_stop_launched_to_text(root=tmp_path)
    assert "Discord launched-through-SOCKS stop:" in stop_text
    assert (tmp_path / ".zap2" / "tunnel" / "logs" / "default.discord.stdout.log").exists()


def test_stage8b_launch_is_blocked_when_tunnel_session_is_stopped(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = _executable(tmp_path / "xray", "#!/bin/sh\nsleep 30\n")
    fake_discord = _executable(tmp_path / "discord", "#!/bin/sh\nsleep 30\n")

    from zap2_gui.adapters.discord_tunnel import discord_tunnel_plan_to_text, discord_tunnel_start_to_text, discord_tunnel_stop_to_text
    from zap2_gui.adapters.runtime_state import confirm_runtime_plan

    discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=19994)
    plan_id = "runtime-default-discord-tunnel-socks-start-plan"
    confirm_runtime_plan(root=tmp_path, plan_id=plan_id)
    discord_tunnel_start_to_text(root=tmp_path, confirm_plan_id=plan_id)
    discord_tunnel_stop_to_text(root=tmp_path)

    try:
        discord_launch_through_socks_to_text(root=tmp_path, discord_binary=str(fake_discord), launch_mode="socks-env-only")
    except ValueError as exc:
        assert "Tunnel core не running" in str(exc)
        assert "session state=stopped" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected stopped tunnel session to block Discord launch")


def test_cli_accepts_stage7p5_tun_plan() -> None:
    assert main(["--discord-tunnel-tun-plan"]) == 0
