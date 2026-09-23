from __future__ import annotations

import json
import stat
from pathlib import Path

from zap2_gui.adapters.discord_tunnel import generate_xray_vless_socks_config, parse_vless_uri
from zap2_gui.adapters.runtime_state import confirm_runtime_plan
from zap2_gui.adapters.tor_backends import (
    generate_arti_config,
    generate_c_tor_config,
    tor_backend_paths,
    tor_backend_plan_to_text,
    tor_backend_start_to_text,
    tor_backend_status_to_text,
    tor_backend_stop_to_text,
)

V2RAYNG_STYLE = (
    "vless://11111111-2222-4333-8444-555555555555@example.net:443"
    "?encryption=none&security=tls&type=xhttp&host=edge.example.org&path=%2Fx"
    "&mode=auto&extra=%7B%22scMaxEachPostBytes%22%3A1000%7D&allowInsecure=1"
    "&fp=chrome&ech=ECH&vcn=edge.example.org&serviceName=svc&authority=auth.example.org#xhttp"
)


def _executable(path: Path, body: str = "#!/bin/sh\nsleep 30\n") -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_v2rayng_style_vless_fields_are_preserved() -> None:
    profile = parse_vless_uri(V2RAYNG_STYLE)
    assert profile.network == "xhttp"
    assert profile.xhttp_mode == "auto"
    assert profile.allow_insecure is True
    config = generate_xray_vless_socks_config(profile)
    stream = config["outbounds"][0]["streamSettings"]
    assert stream["method"] == "xhttp"
    assert stream["xhttpSettings"]["path"] == "/x"
    assert stream["xhttpSettings"]["extra"]["scMaxEachPostBytes"] == 1000
    assert stream["tlsSettings"]["allowInsecure"] is True
    assert stream["tlsSettings"]["fingerprint"] == "chrome"
    assert stream["tlsSettings"]["echConfigList"] == "ECH"


def test_arti_and_c_tor_configs_are_loopback_and_project_local(tmp_path: Path) -> None:
    paths = tor_backend_paths(tmp_path)
    arti = generate_arti_config(paths, socks_host="127.0.0.1", socks_port=19050)
    ctor = generate_c_tor_config(paths, socks_host="127.0.0.1", socks_port=19051)
    assert 'socks_listen = "127.0.0.1:19050"' in arti
    assert str(tmp_path / ".zap2" / "tor" / "data" / "arti-state") in arti
    assert "SocksPort 127.0.0.1:19051" in ctor
    assert "ClientOnly 1" in ctor


def test_arti_backend_plan_confirm_start_status_stop(tmp_path: Path) -> None:
    arti = _executable(tmp_path / "arti")
    plan = tor_backend_plan_to_text(root=tmp_path, backend="arti", binary=str(arti), socks_port=19150)
    plan_id = "runtime-default-tor-arti-start-plan"
    assert "binary exists/executable: yes" in plan
    confirm_runtime_plan(root=tmp_path, plan_id=plan_id)
    started = tor_backend_start_to_text(root=tmp_path, backend="arti", confirm_plan_id=plan_id)
    assert "Tor backend start: started" in started
    shared = tmp_path / ".zap2" / "tunnel" / "runtime" / "default.session.json"
    payload = json.loads(shared.read_text(encoding="utf-8"))
    assert payload["providerKind"] == "tor"
    assert payload["torBackend"] == "arti"
    assert payload["argv"][1:3] == ["proxy", "-c"]
    assert "state: running" in tor_backend_status_to_text(root=tmp_path)
    assert "Tor backend stop: stopped" in tor_backend_stop_to_text(root=tmp_path)


def test_selected_v2rayng_source_keeps_license_and_manifest() -> None:
    root = Path(__file__).resolve().parents[1]
    selected = root / "references" / "upstream" / "v2rayng-selected"
    manifest = json.loads((selected / "UPSTREAM_IMPORT.json").read_text(encoding="utf-8"))
    assert manifest["upstreamCommit"] == "98e7b8e1a1f5201dda161cca4efbbad8839c3f4d"
    assert manifest["license"] == "GPL-3.0"
    assert (selected / "LICENSE").exists()
    assert (root / "references" / "external" / "arti_source_identity.json").exists()
