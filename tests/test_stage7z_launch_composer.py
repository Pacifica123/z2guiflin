from __future__ import annotations

import stat
from pathlib import Path

from zap2_gui.adapters.discord_tunnel import tunnel_connection_import_vless_to_text
from zap2_gui.adapters.launch_composer import (
    COMPONENT_CUSTOM,
    COMPONENT_MTPROTO,
    COMPONENT_SOCKS5,
    COMPONENT_TUNNEL_VLESS,
    COMPONENT_ZAPRET_DEFAULT,
    KNOWN_LAUNCH_COMPONENTS,
    launch_composer_plan_to_text,
    launch_composer_start_to_text,
    launch_composer_status_to_text,
    launch_composer_stop_to_text,
    normalize_launch_components,
)
from zap2_gui.app import main

SAMPLE_VLESS = (
    "vless://11111111-2222-4333-8444-555555555555@example.net:8080"
    "?security=&encryption=none&host=www.example.org&headerType=http&type=tcp#Sample%20Profile"
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


def _executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_stage7z_known_components_include_future_placeholders() -> None:
    assert KNOWN_LAUNCH_COMPONENTS == (
        COMPONENT_ZAPRET_DEFAULT,
        COMPONENT_TUNNEL_VLESS,
        COMPONENT_SOCKS5,
        COMPONENT_MTPROTO,
        COMPONENT_CUSTOM,
    )
    assert normalize_launch_components("tunnel-vless,zapret-default") == (
        COMPONENT_ZAPRET_DEFAULT,
        COMPONENT_TUNNEL_VLESS,
    )
    assert normalize_launch_components("socks5,zapret-default") == (
        COMPONENT_ZAPRET_DEFAULT,
        COMPONENT_SOCKS5,
    )


def test_stage7z_status_and_plan_are_readable_and_categorized(tmp_path: Path) -> None:
    text = launch_composer_status_to_text(root=tmp_path, components="zapret-default,tunnel-vless")
    assert "Launch composer status" in text
    assert "zapret-default :: Zapret default :: supported :: sudo" in text
    assert "tunnel-vless :: VLESS tunnel :: supported :: no-sudo" in text
    assert "socks5 :: SOCKS5 upstream :: planned" in text
    assert "Secrets are not printed" in text

    plan = launch_composer_plan_to_text(root=tmp_path, components="zapret-default,tunnel-vless", core_binary="/missing/xray")
    assert "Launch composer plan" in plan
    assert "start order: zapret-default -> tunnel-vless" in plan
    assert "stop order: tunnel-vless -> zapret-default" in plan
    assert "Combination note" in plan
    assert "does not transparently route Discord" in plan
    assert "readiness: core binary missing" in plan or "readiness: needs VLESS profile" in plan


def test_stage7z_planned_component_is_visible_but_blocked(tmp_path: Path) -> None:
    plan = launch_composer_plan_to_text(root=tmp_path, components="zapret-default,socks5")
    assert "blocked: unsupported planned components selected: socks5" in plan
    try:
        launch_composer_start_to_text(root=tmp_path, components="socks5")
    except ValueError as exc:
        assert "Unsupported planned components selected: socks5" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected planned component to be blocked")


def test_stage7z_can_start_and_stop_vless_only_with_fake_core(tmp_path: Path) -> None:
    tunnel_connection_import_vless_to_text(SAMPLE_VLESS, root=tmp_path)
    fake_core = _executable(tmp_path / "xray", FAKE_SOCKS_CORE)

    start = launch_composer_start_to_text(
        root=tmp_path,
        components="tunnel-vless",
        core_binary=str(fake_core),
        socks_port=19992,
    )
    assert "Launch composer start" in start
    assert "tunnel-vless: start external core" in start
    assert "Discord tunnel start: started" in start
    assert "parallel with zapret allowed: no" in start
    assert (tmp_path / ".zap2" / "tunnel" / "runtime" / "default.session.json").exists()

    stop = launch_composer_stop_to_text(root=tmp_path, components="tunnel-vless")
    assert "Launch composer stop" in stop
    assert "Discord tunnel stop: stopped" in stop


def test_stage7z_cli_and_gui_sources_expose_composer_panel() -> None:
    assert main(["--launch-composer-plan", "--launch-components", "zapret-default,tunnel-vless"]) == 0
    root = Path(__file__).resolve().parents[1]
    source = (root / "gui" / "zap2_gui" / "widgets" / "runtime_controls.py").read_text(encoding="utf-8")
    assert "Комбинированный запуск" in source
    assert "launchComponentZapretDefault" in source
    assert "launchComponentTunnelVless" in source
    assert "SOCKS5 upstream" in source
    assert "MTProto" in source
