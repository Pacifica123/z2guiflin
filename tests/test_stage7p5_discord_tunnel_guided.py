from __future__ import annotations

import socket
import stat
from pathlib import Path

from zap2_gui.adapters.discord_tunnel import (
    SUPPORTED_LAUNCH_MODES,
    discord_launch_through_socks_to_text,
    discord_stop_launched_to_text,
    discord_tunnel_guided_run_to_text,
    discord_tunnel_https_probe_to_text,
    discord_tunnel_route_diagnose_to_text,
    discord_tunnel_stop_to_text,
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




def _unused_tcp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()

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

    isolated_port = _unused_tcp_port()
    text = discord_tunnel_guided_run_to_text(
        root=tmp_path,
        core_binary=str(fake_core),
        socks_port=isolated_port,
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
    assert "Discord tunnel stop: stopped" in discord_tunnel_stop_to_text(root=tmp_path)


def test_stage8a_launch_through_socks_accepts_flatpak_command_string(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = _executable(tmp_path / "xray", FAKE_SOCKS_CORE)
    fake_flatpak = _executable(tmp_path / "flatpak", "#!/bin/sh\necho flatpak-noise\nsleep 30\n")
    fake_discord_app = tmp_path / "com.discordapp.Discord"
    fake_discord_app.write_text("marker", encoding="utf-8")

    from zap2_gui.adapters.discord_tunnel import discord_tunnel_plan_to_text, discord_tunnel_start_to_text
    from zap2_gui.adapters.runtime_state import confirm_runtime_plan

    socks_port = _unused_tcp_port()
    old_path = __import__("os").environ.get("PATH", "")
    __import__("os").environ["PATH"] = f"{tmp_path}:{old_path}"
    try:
        discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=socks_port)
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
    assert f"--proxy-server=socks5://127.0.0.1:{socks_port}" in text

    stop_text = discord_stop_launched_to_text(root=tmp_path)
    assert "Discord launched-through-SOCKS stop:" in stop_text
    assert "Discord tunnel stop: stopped" in discord_tunnel_stop_to_text(root=tmp_path)
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


def test_stage8c_route_diagnose_classifies_routed_tls_closed(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    zap2 = root / ".zap2" / "tunnel"
    runtime = zap2 / "runtime"
    logs = zap2 / "logs"
    runtime.mkdir(parents=True)
    logs.mkdir(parents=True)
    (runtime / "default.session.json").write_text(
        '{"state":"running","pid":999999,"socksHost":"127.0.0.1","socksPort":19999}',
        encoding="utf-8",
    )
    (runtime / "default.discord-session.json").write_text(
        '{"state":"running","pid":999998,"discordCommand":"flatpak run com.discordapp.Discord"}',
        encoding="utf-8",
    )
    (logs / "default.core.stdout.log").write_text(
        "2026/06/25 20:27:25 tcp:127.0.0.1:35720 accepted tcp:discordapp.com:443 [proxy]\n",
        encoding="utf-8",
    )
    (logs / "default.discord.stderr.log").write_text(
        "[WebContents] did-fail-load -100 ERR_CONNECTION_CLOSED retry in 20000 ms\n"
        "[64:0625/202737.593477:ERROR:net/socket/ssl_client_socket_impl.cc:896] handshake failed; returned -1, SSL error code 1, net_error -100\n",
        encoding="utf-8",
    )

    import zap2_gui.adapters.discord_tunnel as discord_tunnel_module

    monkeypatch.setattr(discord_tunnel_module, "_pid_running", lambda pid: bool(pid))
    monkeypatch.setattr(discord_tunnel_module, "_socks5_handshake_probe", lambda host, port: {"ok": True, "portOpen": True, "message": "SOCKS5 no-auth greeting accepted"})

    text = discord_tunnel_route_diagnose_to_text(root=root)

    assert "Discord tunnel route diagnosis" in text
    assert "verdict: TD_APP_ROUTED_BUT_UPSTREAM_TLS_CLOSED" in text
    assert "core accepted Discord destinations: 1" in text
    assert "ERR_CONNECTION_CLOSED" in text
    assert "read-only: yes" in text


def test_stage8c_launch_preflight_blocks_discord_before_spawn(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = _executable(tmp_path / "xray", FAKE_SOCKS_CORE)
    fake_discord = _executable(tmp_path / "discord", "#!/bin/sh\nsleep 30\n")

    from zap2_gui.adapters.discord_tunnel import discord_tunnel_plan_to_text, discord_tunnel_start_to_text
    from zap2_gui.adapters.runtime_state import confirm_runtime_plan

    socks_port = _unused_tcp_port()
    discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=socks_port)
    plan_id = "runtime-default-discord-tunnel-socks-start-plan"
    confirm_runtime_plan(root=tmp_path, plan_id=plan_id)
    discord_tunnel_start_to_text(root=tmp_path, confirm_plan_id=plan_id)

    try:
        discord_launch_through_socks_to_text(
            root=tmp_path,
            discord_binary=str(fake_discord),
            launch_mode="socks-env-only",
            upstream_preflight=True,
            preflight_timeout=1.0,
        )
    except ValueError as exc:
        assert "Upstream preflight не прошёл" in str(exc)
        assert "Discord не запущен" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected failed upstream preflight to block launch")

    assert not (tmp_path / ".zap2" / "tunnel" / "runtime" / "default.discord-session.json").exists()
    assert list((tmp_path / ".zap2" / "tunnel" / "reports").glob("default.launch-preflight-*.json"))
    assert "Discord tunnel stop: stopped" in discord_tunnel_stop_to_text(root=tmp_path)


def test_stage8c_cli_exposes_route_diagnose() -> None:
    assert main(["--discord-tunnel-route-diagnose"]) == 0
