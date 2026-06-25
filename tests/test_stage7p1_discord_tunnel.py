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
    assert outbound["settings"]["vnext"][0]["address"] == "example.net"
    assert outbound["settings"]["vnext"][0]["users"][0]["encryption"] == "none"
    assert outbound["streamSettings"]["network"] == "tcp"
    assert outbound["streamSettings"]["tcpSettings"]["header"]["type"] == "http"
    assert outbound["streamSettings"]["tcpSettings"]["header"]["request"]["headers"]["Host"] == ["www.example.org"]


def test_import_list_and_plan_do_not_print_raw_secret(tmp_path: Path) -> None:
    import_text = tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    assert "11111111-2222-4333-8444-555555555555" not in import_text
    assert "example.net" not in import_text
    list_text = tunnel_connections_to_text(root=tmp_path)
    assert "Sample Profile" in list_text
    assert "11111111-2222-4333-8444-555555555555" not in list_text
    fake_core = tmp_path / "xray"
    fake_core.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
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
    fake_core.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
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
    # The fake core does not open SOCKS, but the probe must return a clear report instead of crashing.
    assert "verdict: T0_CORE_NOT_READY" in probe_text
    assert "socks handshake: no" in probe_text
    assert "upstream tested: no" in probe_text
    stop_text = discord_tunnel_stop_to_text(root=tmp_path)
    assert "Discord tunnel stop: stopped" in stop_text


def test_stage8a_proxy_route_plan_explains_non_transparent_socks(tmp_path: Path) -> None:
    text = discord_proxy_route_plan_to_text(root=tmp_path)

    assert "Discord proxy route plan" in text
    assert "Starting VLESS tunnel only opens a local SOCKS listener" in text
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
