from __future__ import annotations

import json
import stat
import time
from pathlib import Path

import pytest

from zap2_gui.adapters import tor_bridges
from zap2_gui.adapters.discord_tunnel import generate_xray_vless_socks_config, parse_vless_uri
from zap2_gui.adapters.runtime_state import confirm_runtime_plan
from zap2_gui.adapters.tor_backends import (
    TorSettings,
    generate_arti_config,
    generate_c_tor_config,
    parse_bootstrap,
    save_tor_settings,
    tor_backend_paths,
    tor_backend_plan_to_text,
    tor_backend_start_to_text,
    tor_backend_stop_to_text,
    tor_bootstrap_status,
    tor_upstream_for_vless,
)
from zap2_gui.adapters.tor_bridges import (
    TransportPrograms,
    detect_transport_programs,
    parse_bridges,
    plugin_groups,
    save_bridges,
)

FP = "0123456789ABCDEF0123456789ABCDEF01234567"
OBFS4 = f"Bridge obfs4 192.0.2.10:443 {FP} cert=AbCd+/xyz iat-mode=0"
SNOWFLAKE = f"snowflake 192.0.2.3:80 {FP} fingerprint={FP} url=https://snowflake-broker.example/ ice=stun:stun.example:3478"
WEBTUNNEL = f"webtunnel [2001:db8::1]:443 {FP} url=https://example.org/secret ver=0.0.1"
VANILLA = f"198.51.100.7:9001 {FP}"


def _executable(path: Path, body: str = "#!/bin/sh\nsleep 30\n") -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_bridge_lines_are_parsed_validated_and_deduplicated() -> None:
    text = "\n".join([OBFS4, OBFS4.replace("Bridge ", ""), SNOWFLAKE, WEBTUNNEL, VANILLA, "# comment", "",
                      "obfs4 192.0.2.11:443 " + FP, "vmess 1.2.3.4:1 x", "obfs4 not-an-ip:443 " + FP + " cert=x"])
    result = parse_bridges(text)
    assert [item.transport for item in result.bridges] == ["obfs4", "snowflake", "webtunnel", ""]
    assert result.duplicates == 1
    assert result.transports == ("obfs4", "snowflake", "webtunnel")
    assert result.bridges[2].line.startswith("webtunnel [2001:db8::1]:443 ")
    assert result.bridges[0].line == OBFS4.replace("Bridge ", "")
    assert len(result.errors) == 3
    assert "cert=" in result.errors[0] and "неизвестный транспорт" in result.errors[1] and "не IP" in result.errors[2]


def test_transport_detection_prefers_lyrebird_and_groups_plugins() -> None:
    present = {"lyrebird": "/usr/bin/lyrebird", "obfs4proxy": "/usr/bin/obfs4proxy", "snowflake-client": "/opt/snowflake-client"}
    programs = detect_transport_programs(lambda name: present.get(name, ""))
    assert programs.by_transport["obfs4"] == "/usr/bin/lyrebird"
    assert programs.by_transport["webtunnel"] == "/usr/bin/lyrebird"
    assert programs.missing_for(("obfs4", "conjure")) == ("conjure",)
    groups = plugin_groups(("obfs4", "webtunnel", "snowflake"), programs)
    assert groups == ((("obfs4", "webtunnel"), "/usr/bin/lyrebird"), (("snowflake",), "/opt/snowflake-client"))
    assert "✓ lyrebird" in programs.to_text() and "· webtunnel-client" in programs.to_text()


def test_c_tor_and_arti_configs_with_bridges(tmp_path: Path) -> None:
    paths = tor_backend_paths(tmp_path)
    bridges = parse_bridges("\n".join([OBFS4, SNOWFLAKE])).bridges
    plugins = ((("obfs4",), "/usr/bin/lyrebird"), (("snowflake",), "/usr/bin/snowflake-client"))
    ctor = generate_c_tor_config(paths, socks_host="127.0.0.1", socks_port=19051, bridges=bridges, plugins=plugins)
    assert "UseBridges 1" in ctor
    assert "ClientTransportPlugin obfs4 exec /usr/bin/lyrebird" in ctor
    assert f"Bridge obfs4 192.0.2.10:443 {FP} cert=AbCd+/xyz iat-mode=0" in ctor
    unix = generate_c_tor_config(paths, socks_host="127.0.0.1", socks_port=0, socks_unix="/run/user/1000/zap2gui-tor/default.socks")
    assert "SocksPort unix:/run/user/1000/zap2gui-tor/default.socks" in unix and "UseBridges" not in unix
    arti = generate_arti_config(paths, socks_host="127.0.0.1", socks_port=19050, bridges=bridges, plugins=plugins)
    assert "[bridges]" in arti and "enabled = true" in arti
    assert json.dumps(bridges[0].line) in arti
    assert '[[bridges.transports]]\nprotocols = ["snowflake"]\npath = "/usr/bin/snowflake-client"' in arti


def test_plan_refuses_bridges_without_transport_program(tmp_path: Path, monkeypatch) -> None:
    paths = tor_backend_paths(tmp_path)
    save_bridges(paths.tor_root, parse_bridges(OBFS4).bridges)
    assert oct((paths.tor_root / "bridges.txt").stat().st_mode & 0o777) == "0o600"
    monkeypatch.setattr("zap2_gui.adapters.tor_backends.detect_transport_programs",
                        lambda: TransportPrograms({}, {}))
    with pytest.raises(ValueError, match="obfs4"):
        tor_backend_plan_to_text(root=tmp_path, backend="c-tor", binary=str(_executable(tmp_path / "tor")), use_bridges=True)
    with pytest.raises(ValueError, match="только для C Tor"):
        tor_backend_plan_to_text(root=tmp_path, backend="arti", listen="unix")


def test_start_with_bridges_random_port_and_bootstrap_progress(tmp_path: Path, monkeypatch) -> None:
    paths = tor_backend_paths(tmp_path)
    save_bridges(paths.tor_root, parse_bridges(OBFS4).bridges)
    lyrebird = _executable(tmp_path / "lyrebird")
    monkeypatch.setattr("zap2_gui.adapters.tor_backends.detect_transport_programs",
                        lambda: TransportPrograms({"lyrebird": str(lyrebird)}, {"obfs4": str(lyrebird)}))
    fake_tor = _executable(tmp_path / "tor", "#!/bin/sh\necho 'Oct 21 [notice] Bootstrapped 45% (requesting_descriptors): Asking for relay descriptors'\nsleep 30\n")
    plan = tor_backend_plan_to_text(root=tmp_path, backend="c-tor", binary=str(fake_tor), listen="random", use_bridges=True)
    assert "bridges: 1 (obfs4)" in plan and "bridge requests to Moat: no" in plan
    plan_id = "runtime-default-tor-c-tor-start-plan"
    confirm_runtime_plan(root=tmp_path, plan_id=plan_id)
    record = json.loads((paths.plans_dir / f"{plan_id}.json").read_text(encoding="utf-8"))
    assert 20000 <= record["localSocks"]["port"] <= 60999 and record["safety"]["bridgesConfigured"] is True
    started = tor_backend_start_to_text(root=tmp_path, backend="c-tor", confirm_plan_id=plan_id)
    try:
        assert "Tor backend start: started" in started
        config = (paths.generated_dir / "default.c-tor.torrc").read_text(encoding="utf-8")
        assert f"ClientTransportPlugin obfs4 exec {lyrebird}" in config
        status = None
        for _ in range(40):
            status = tor_bootstrap_status(root=tmp_path)
            if status.percent is not None:
                break
            time.sleep(0.05)
        assert status is not None and status.state == "starting" and status.percent == 45
        assert status.socks == f"socks5h://127.0.0.1:{record['localSocks']['port']}"
    finally:
        tor_backend_stop_to_text(root=tmp_path)
    assert tor_bootstrap_status(root=tmp_path).state == "stopped"


def test_changed_bridges_after_plan_block_start(tmp_path: Path, monkeypatch) -> None:
    paths = tor_backend_paths(tmp_path)
    save_bridges(paths.tor_root, parse_bridges(VANILLA).bridges)
    fake_tor = _executable(tmp_path / "tor")
    tor_backend_plan_to_text(root=tmp_path, backend="c-tor", binary=str(fake_tor), use_bridges=True)
    plan_id = "runtime-default-tor-c-tor-start-plan"
    confirm_runtime_plan(root=tmp_path, plan_id=plan_id)
    save_bridges(paths.tor_root, parse_bridges(VANILLA.replace("198.51.100.7", "198.51.100.8")).bridges)
    with pytest.raises(ValueError, match="изменился после плана"):
        tor_backend_start_to_text(root=tmp_path, backend="c-tor", confirm_plan_id=plan_id)


def test_bootstrap_parsing_for_c_tor_and_arti() -> None:
    assert parse_bootstrap("x\n[notice] Bootstrapped 10% (conn_done): Connected\n[notice] Bootstrapped 100% (done): Done\n") == (100, "Done")
    assert parse_bootstrap("INFO arti: Sufficiently bootstrapped; system SOCKS now functional.")[0] == 100
    assert parse_bootstrap("nothing yet") == (None, "")


def test_tor_before_vless_chains_the_vless_dial(tmp_path: Path) -> None:
    profile = parse_vless_uri("vless://11111111-2222-4333-8444-555555555555@example.net:443?security=tls&type=tcp#t")
    xray = generate_xray_vless_socks_config(profile, core_kind="xray", upstream_socks=("127.0.0.1", 31000))
    proxy = xray["outbounds"][0]
    assert proxy["streamSettings"]["sockopt"]["dialerProxy"] == "tor-upstream"
    assert xray["outbounds"][-1] == {"tag": "tor-upstream", "protocol": "socks", "settings": {"servers": [{"address": "127.0.0.1", "port": 31000}]}}
    v2ray = generate_xray_vless_socks_config(profile, core_kind="v2ray", upstream_socks=("127.0.0.1", 31000))
    assert v2ray["outbounds"][0]["proxySettings"] == {"tag": "tor-upstream"}
    plain = generate_xray_vless_socks_config(profile, core_kind="xray")
    assert "sockopt" not in plain["outbounds"][0]["streamSettings"] and len(plain["outbounds"]) == 3

    assert tor_upstream_for_vless(tmp_path) is None  # режим выключен
    save_tor_settings(TorSettings(vless_via_tor=True), tmp_path)
    with pytest.raises(ValueError, match="Tor не запущен"):
        tor_upstream_for_vless(tmp_path)


def test_tor_page_builds_and_validates_bridges(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("PyQt6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QPushButton

    from zap2_gui.widgets.tor_page import make_tor_page

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(tor_bridges, "find_program", lambda name, extra_dirs=(): "")
    page = make_tor_page(tmp_path)
    edit = page.findChild(QPlainTextEdit, "torBridges")
    edit.setPlainText(OBFS4 + "\nvmess 1.2.3.4:1")
    save = next(item for item in page.findChildren(QPushButton) if item.text() == "Проверить и сохранить")
    save.click()
    texts = [label.text() for label in page.findChildren(QLabel)]
    assert any(text.startswith("Не сохранено") for text in texts)
    edit.setPlainText(OBFS4)
    save.click()
    texts = [label.text() for label in page.findChildren(QLabel)]
    assert any(text.startswith("Сохранено мостов: 1 (obfs4)") for text in texts)
    assert any("не хватает: obfs4" in text for text in texts)
    settings = json.loads((tmp_path / ".zap2" / "tor" / "settings.json").read_text(encoding="utf-8"))
    assert settings["useBridges"] is True and settings["listen"] == "random"
    page.close()
    app.processEvents()
