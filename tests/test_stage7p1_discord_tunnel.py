from __future__ import annotations

import base64
import os
import stat
import time
from pathlib import Path

from zap2_gui.adapters.discord_tunnel import (
    DEFAULT_SOCKS_PORT,
    discord_tunnel_plan_to_text,
    discord_tunnel_probe_to_text,
    discord_tunnel_start_to_text,
    discord_proxy_route_plan_to_text,
    discord_tunnel_stop_to_text,
    generate_xray_vless_socks_config,
    parse_vless_uri,
    preview_vless_import_text_to_text,
    tunnel_connection_import_vless_text_to_text,
    tunnel_connection_import_vless_to_text,
    tunnel_connections_to_text,
)
from zap2_gui.adapters.runtime_state import confirm_runtime_plan

SAMPLE_VLESS = (
    "vless://11111111-2222-4333-8444-555555555555@example.net:8080"
    "?security=&encryption=none&host=www.example.org&headerType=http&type=tcp#Sample%20Profile"
)

REALITY_VLESS = (
    "vless://11111111-2222-4333-8444-555555555555@203.0.113.10:8443"
    "?security=reality&encryption=none&type=tcp&flow=xtls-rprx-vision"
    "&sni=storage.example.net&fp=firefox&pbk=PUBLICKEY123&sid=0905b6e16602f326&spx=%2F#Reality"
)

FAKE_SOCKS_CORE = r'''#!/usr/bin/env python3
import json, socket, sys, time
from pathlib import Path
config = None
for index, arg in enumerate(sys.argv):
    if arg in {"-config", "-c"} and index + 1 < len(sys.argv):
        config = Path(sys.argv[index + 1]); break
if "-test" in sys.argv:
    raise SystemExit(0)
port = int(json.loads(config.read_text(encoding="utf-8"))["inbounds"][0]["port"])
def _socks_settings():
    try:
        return json.loads(config.read_text(encoding="utf-8"))["inbounds"][0].get("settings", {})
    except Exception:
        return {}
SOCKS_SETTINGS = _socks_settings()
def handle(conn):
    # RFC1928/RFC1929 fake: honour the generated inbound auth mode.
    head = conn.recv(2)
    if len(head) < 2 or head[0] != 5:
        return
    methods = conn.recv(head[1])
    if SOCKS_SETTINGS.get("auth") == "password":
        if 2 not in methods:
            conn.sendall(b"\x05\xff"); return
        conn.sendall(b"\x05\x02")
        ver_len = conn.recv(2); user = conn.recv(ver_len[1]); plen = conn.recv(1)[0]; pw = conn.recv(plen)
        ok = any(a.get("user") == user.decode() and a.get("pass") == pw.decode() for a in SOCKS_SETTINGS.get("accounts", []))
        conn.sendall(b"\x01\x00" if ok else b"\x01\x01")
        if not ok:
            return
    else:
        if 0 not in methods:
            conn.sendall(b"\x05\xff"); return
        conn.sendall(b"\x05\x00")
    try:
        conn.recv(4096)
    except OSError:
        pass
server = socket.socket(); server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", port)); server.listen(8); server.settimeout(0.2)
started=time.time()
while time.time()-started < 30:
    try: conn,_=server.accept()
    except socket.timeout: continue
    with conn:
        try:
            handle(conn)
        except Exception:
            pass
'''


def test_vless_parser_redacts_and_preserves_transport_fields() -> None:
    profile = parse_vless_uri(SAMPLE_VLESS)
    assert profile.connection_id.startswith("vless-")
    assert profile.user_id == "11111111-2222-4333-8444-555555555555"
    assert profile.server == "example.net"
    assert profile.port == 8080
    assert profile.security == "none"
    assert profile.encryption == "none"
    assert profile.network == "tcp"
    assert profile.header_type == "http"
    assert profile.host == "www.example.org"
    assert profile.remarks == "Sample Profile"
    redacted = profile.redacted_dict()
    assert "11111111-2222" not in str(redacted)
    assert "example.net" not in redacted["server"]


def test_vless_config_generates_loopback_socks_and_http_header() -> None:
    profile = parse_vless_uri(SAMPLE_VLESS)
    config = generate_xray_vless_socks_config(profile, socks_port=19080)
    inbound = config["inbounds"][0]
    assert inbound["listen"] == "127.0.0.1"
    assert inbound["port"] == 19080
    assert inbound["protocol"] == "socks"
    outbound = config["outbounds"][0]
    assert outbound["protocol"] == "vless"
    assert outbound["settings"]["address"] == "example.net"
    assert outbound["settings"]["encryption"] == "none"
    assert outbound["streamSettings"]["method"] == "raw"
    assert outbound["streamSettings"]["rawSettings"]["header"]["type"] == "http"
    assert outbound["streamSettings"]["rawSettings"]["header"]["request"]["headers"]["Host"] == ["www.example.org"]


def test_vless_config_preserves_reality_settings_for_openray_links() -> None:
    profile = parse_vless_uri(REALITY_VLESS)
    config = generate_xray_vless_socks_config(profile, socks_port=19081)
    stream = config["outbounds"][0]["streamSettings"]

    assert stream["security"] == "reality"
    assert stream["method"] == "raw"
    assert stream["realitySettings"]["serverName"] == "storage.example.net"
    assert stream["realitySettings"]["fingerprint"] == "firefox"
    assert stream["realitySettings"]["password"] == "PUBLICKEY123"
    assert stream["realitySettings"]["shortId"] == "0905b6e16602f326"
    assert stream["realitySettings"]["spiderX"] == "/"


def test_v2ray_config_keeps_classic_vnext_schema() -> None:
    profile = parse_vless_uri(SAMPLE_VLESS)
    config = generate_xray_vless_socks_config(profile, socks_port=19082, core_kind="v2ray")
    outbound = config["outbounds"][0]
    assert outbound["settings"]["vnext"][0]["address"] == "example.net"
    assert outbound["streamSettings"]["network"] == "tcp"
    assert outbound["streamSettings"]["tcpSettings"]["header"]["type"] == "http"


def test_import_list_and_plan_do_not_print_raw_secret(tmp_path: Path) -> None:
    import_text = tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    assert "11111111-2222-4333-8444-555555555555" not in import_text
    assert "example.net" not in import_text
    list_text = tunnel_connections_to_text(root=tmp_path)
    assert "Sample Profile" in list_text
    assert "11111111-2222-4333-8444-555555555555" not in list_text
    fake_core = tmp_path / "xray"
    fake_core.write_text(FAKE_SOCKS_CORE, encoding="utf-8")
    fake_core.chmod(fake_core.stat().st_mode | stat.S_IXUSR)
    plan_text = discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=19080)
    assert "core binary exists/executable: yes" in plan_text
    assert "runtime-default-discord-tunnel-socks-start-plan" in plan_text
    assert "11111111-2222-4333-8444-555555555555" not in plan_text
    assert "example.net" not in plan_text
    plan_files = list((tmp_path / ".zap2" / "runtime" / "plans").glob("*.json"))
    assert plan_files
    plan_payload = plan_files[0].read_text(encoding="utf-8")
    assert "11111111-2222-4333-8444-555555555555" not in plan_payload
    assert "example.net" not in plan_payload


def test_confirm_start_probe_stop_with_fake_core(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = tmp_path / "xray"
    fake_core.write_text(FAKE_SOCKS_CORE, encoding="utf-8")
    fake_core.chmod(fake_core.stat().st_mode | stat.S_IXUSR)
    discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=19991)
    plan_id = "runtime-default-discord-tunnel-socks-start-plan"
    confirm_runtime_plan(root=tmp_path, plan_id=plan_id)
    start_text = discord_tunnel_start_to_text(root=tmp_path, confirm_plan_id=plan_id)
    assert "Discord tunnel start: started" in start_text
    session_file = tmp_path / ".zap2" / "tunnel" / "runtime" / "default.session.json"
    assert session_file.exists()
    generated = tmp_path / ".zap2" / "tunnel" / "generated" / "default.core.json"
    assert generated.exists()
    assert stat.S_IMODE(generated.stat().st_mode) == 0o600
    probe_text = discord_tunnel_probe_to_text(root=tmp_path)
    assert "verdict: T0_SOCKS_READY" in probe_text
    assert "socks handshake: ok" in probe_text
    assert "upstream tested: no" in probe_text
    stop_text = discord_tunnel_stop_to_text(root=tmp_path)
    assert "Discord tunnel stop: stopped" in stop_text


def test_stage8a_proxy_route_plan_explains_non_transparent_socks(tmp_path: Path) -> None:
    text = discord_proxy_route_plan_to_text(root=tmp_path)

    assert "Discord proxy route plan" in text
    assert "Starting VLESS tunnel only opens a local SOCKS listener" in text
    assert "flatpak run dev.vencord.Vesktop" in text
    assert "flatpak run com.discordapp.Discord" in text
    assert "Firefox/web Discord" in text
    assert "read-only: yes" in text


def test_stage7p1_tree_does_not_commit_user_example_secret() -> None:
    forbidden = [
        "47c87a37" + "-3d09-4c3d-96fb-91ce3bcae058",
        "62.60" + ".148.226",
    ]
    root = Path(__file__).resolve().parents[1]
    checked = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if ".zap2" in path.parts or path.suffix in {".pyc", ".zip"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        checked.append(path)
        for needle in forbidden:
            assert needle not in text, f"secret leaked in {path}"
    assert checked


def test_stage7y_imports_vless_batch_text_and_base64_without_printing_secrets(tmp_path: Path) -> None:
    second = (
        "vless://aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee@second.example.net:443"
        "?security=tls&encryption=none&type=ws&path=%2Fws&sni=edge.example.org#Second"
    )
    payload = f"note before\n{SAMPLE_VLESS}\n{second}\n"
    encoded_payload = base64.b64encode(payload.encode("utf-8")).decode("ascii")

    preview_text = preview_vless_import_text_to_text(encoded_payload, source="test-clipboard")
    assert "valid: 2" in preview_text
    assert "writes files now: no" in preview_text
    assert "11111111-2222-4333-8444-555555555555" not in preview_text
    assert "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee" not in preview_text
    assert "example.net" not in preview_text

    import_text = tunnel_connection_import_vless_text_to_text(encoded_payload, source="test-clipboard", root=tmp_path)
    assert "Tunnel VLESS batch import" in import_text
    assert "imported valid profiles: 2" in import_text
    assert "auto-selected: vless-" in import_text
    assert "11111111-2222-4333-8444-555555555555" not in import_text
    assert "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee" not in import_text
    assert "example.net" not in import_text
    assert "second.example.net" not in import_text

    list_text = tunnel_connections_to_text(root=tmp_path)
    assert "Sample Profile" in list_text
    assert "Second" in list_text
    assert "example.net" not in list_text


def test_stage7y_tunnel_gui_source_exposes_clipboard_import_without_runtime_launch() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "gui" / "zap2_gui" / "widgets" / "tunnel.py").read_text(encoding="utf-8")

    assert "Импорт из буфера" in source
    assert "QApplication.clipboard" in source
    assert "preview_vless_import_text_to_text" in source
    assert "tunnel_connection_import_vless_text_to_text" in source
    assert "GUI не скачивает core" in source


# --- loopback SOCKS auth hardening (wiki.zapret.moe/VLESS-SOCKS5-vulnerability, 07.04.2026) ---

import json as _json
import socket as _socket
import threading as _threading

from zap2_gui.adapters import discord_tunnel as _tunnel


def _noauth_only_socks_server():
    """Tiny 127.0.0.1 SOCKS5 server that only offers NO_AUTH (insecure)."""

    server = _socket.socket()
    server.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(4)
    server.settimeout(5)

    def serve() -> None:
        try:
            conn, _ = server.accept()
        except OSError:
            return
        with conn:
            head = conn.recv(2)
            if len(head) == 2:
                conn.recv(head[1])
                conn.sendall(b"\x05\x00")

    thread = _threading.Thread(target=serve, daemon=True)
    thread.start()
    return server, thread


def test_default_generated_config_never_contains_noauth() -> None:
    profile = parse_vless_uri(SAMPLE_VLESS)
    config = generate_xray_vless_socks_config(profile, socks_port=23456)
    settings = config["inbounds"][0]["settings"]
    assert settings["auth"] == "password"
    assert settings["accounts"][0]["user"] and len(settings["accounts"][0]["pass"]) >= 24
    assert "noauth" not in _json.dumps(config)
    other = generate_xray_vless_socks_config(profile, socks_port=23456)
    assert other["inbounds"][0]["settings"]["accounts"] != settings["accounts"]
    legacy = generate_xray_vless_socks_config(profile, socks_port=23456, legacy_noauth=True)
    assert legacy["inbounds"][0]["settings"]["auth"] == "noauth"


def test_default_socks_port_is_random_high_and_not_scanned(tmp_path: Path) -> None:
    assert DEFAULT_SOCKS_PORT == 0
    for _ in range(20):
        port = _tunnel.pick_random_socks_port()
        assert port != 10808
        assert not 16000 <= port <= 16100
        assert 20000 <= port <= 60999
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = tmp_path / "xray"
    fake_core.write_text(FAKE_SOCKS_CORE, encoding="utf-8")
    fake_core.chmod(fake_core.stat().st_mode | stat.S_IXUSR)
    discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core))
    plan = _json.loads((tmp_path / ".zap2" / "runtime" / "plans" / "runtime-default-discord-tunnel-socks-start-plan.json").read_text(encoding="utf-8"))
    port = plan["localSocks"]["port"]
    assert port != 10808 and not 16000 <= port <= 16100 and 20000 <= port <= 60999


def test_credentials_are_private_and_redacted_in_plan_and_reports(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = tmp_path / "xray"
    fake_core.write_text(FAKE_SOCKS_CORE, encoding="utf-8")
    fake_core.chmod(fake_core.stat().st_mode | stat.S_IXUSR)
    plan_text = discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=_tunnel.pick_random_socks_port())
    auth_file = tmp_path / ".zap2" / "tunnel" / "runtime" / "default.plan-socks-auth.json"
    assert stat.S_IMODE(auth_file.stat().st_mode) == 0o600
    password = _json.loads(auth_file.read_text(encoding="utf-8"))["pass"]
    assert password not in plan_text
    assert "<redacted>" in plan_text and "socks5h://" in plan_text
    plan_id = "runtime-default-discord-tunnel-socks-start-plan"
    plan_file = tmp_path / ".zap2" / "runtime" / "plans" / f"{plan_id}.json"
    assert password not in plan_file.read_text(encoding="utf-8")
    confirm_runtime_plan(root=tmp_path, plan_id=plan_id)
    try:
        start_text = discord_tunnel_start_to_text(root=tmp_path, confirm_plan_id=plan_id)
        assert "Discord tunnel start: started" in start_text
        probe_text = discord_tunnel_probe_to_text(root=tmp_path)
        assert "socks handshake: ok" in probe_text
        assert "verdict: T0_SOCKS_READY" in probe_text
        route_text = discord_proxy_route_plan_to_text(root=tmp_path)
        session_auth = tmp_path / ".zap2" / "tunnel" / "runtime" / "default.session-socks-auth.json"
        assert stat.S_IMODE(session_auth.stat().st_mode) == 0o600
        for text in (start_text, probe_text, route_text):
            assert password not in text
        for path in (tmp_path / ".zap2").rglob("*"):
            if path.is_file() and path.name not in {"default.plan-socks-auth.json", "default.session-socks-auth.json", "default.core.json"}:
                assert password not in path.read_text(encoding="utf-8", errors="replace"), path
    finally:
        discord_tunnel_stop_to_text(root=tmp_path)


def test_probe_rejects_listener_that_offers_only_noauth() -> None:
    server, thread = _noauth_only_socks_server()
    try:
        port = server.getsockname()[1]
        result = _tunnel._socks5_handshake_probe("127.0.0.1", port, timeout=2.0, credentials=("u", "p"))
    finally:
        thread.join(timeout=5)
        server.close()
    assert result["ok"] is False
    assert result["insecureNoAuth"] is True
    assert "INSECURE" in result["message"]


def test_launch_via_proxy_server_flag_refused_in_password_mode(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = tmp_path / "xray"
    fake_core.write_text(FAKE_SOCKS_CORE, encoding="utf-8")
    fake_core.chmod(fake_core.stat().st_mode | stat.S_IXUSR)
    discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=_tunnel.pick_random_socks_port())
    plan_id = "runtime-default-discord-tunnel-socks-start-plan"
    confirm_runtime_plan(root=tmp_path, plan_id=plan_id)
    try:
        discord_tunnel_start_to_text(root=tmp_path, confirm_plan_id=plan_id)
        try:
            _tunnel.discord_launch_through_socks_to_text(root=tmp_path, discord_binary=str(fake_core), launch_mode="socks-flag-only")
        except ValueError as exc:
            assert "legacy-noauth" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected --proxy-server launch to be refused without legacy opt-in")
    finally:
        discord_tunnel_stop_to_text(root=tmp_path)


def test_legacy_noauth_plan_is_explicit_and_warns(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = tmp_path / "xray"
    fake_core.write_text(FAKE_SOCKS_CORE, encoding="utf-8")
    fake_core.chmod(fake_core.stat().st_mode | stat.S_IXUSR)
    text = discord_tunnel_plan_to_text(root=tmp_path, core_binary=str(fake_core), socks_port=_tunnel.pick_random_socks_port(), socks_auth_mode="legacy-noauth")
    assert "LEGACY NOAUTH" in text
    assert "localhost ≠ private" in text
