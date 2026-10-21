from __future__ import annotations

import json
import socket
import struct
import threading
from pathlib import Path

import pytest

from zap2_gui.adapters import dns_nm
from zap2_gui.adapters.dns_nm import Result, apply_dns, revert_dns
from zap2_gui.adapters.dns_probe import build_query, check_provider, detect_interception, parse_a_records, udp_query
from zap2_gui.adapters.dnscrypt_config import dnscrypt_config
from zap2_gui.models.dns_catalog import custom_provider, doh_stamp, load_dns_catalog

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_follows_owner_decisions() -> None:
    catalog = load_dns_catalog()
    names = " ".join(p.name for p in catalog.providers).lower()
    assert "яндекс" not in names and "yandex" not in json.dumps([p.to_dict() for p in catalog.providers]).lower()
    by_id = catalog.by_id()
    assert by_id["bizone"].status == "high_risk"
    assert by_id["google"].status == "blocked" and by_id["cloudflare"].status == "blocked"
    for group in catalog.groups:
        assert "Больше" in group.tradeoff and "—" in group.tradeoff, group
    assert not by_id["wikimedia"].plain_dns_works


def test_doh_stamp_matches_published_quad9_layout() -> None:
    # Официальный stamp Quad9 отличается только битами свойств (у них 3: DNSSEC + no-log).
    stamp = doh_stamp(load_dns_catalog().by_id()["quad9"])
    assert stamp == "sdns://AgEAAAAAAAAABzkuOS45LjkADWRucy5xdWFkOS5uZXQKL2Rucy1xdWVyeQ"
    assert "stamp = 'sdns://" in dnscrypt_config(load_dns_catalog().by_id()["quad9"])


def test_custom_provider_needs_only_https_doh() -> None:
    provider = custom_provider("", "https://dns.example.org/dns-query", ("93.184.216.34",))
    assert provider.group == "custom" and provider.name == "dns.example.org"
    with pytest.raises(ValueError):
        custom_provider("x", "http://dns.example.org/dns-query", ("93.184.216.34",))
    with pytest.raises(ValueError):
        custom_provider("x", "https://dns.example.org/q", ("192.168.1.1",))


class FakeNm:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        if argv[-2:] == ["device", "status"]:
            return Result(0, "wlan0:wifi:connected:Home\\:5G\nwg0:wireguard:connected:vpn\nlo:loopback:connected (externally):lo\n")
        if argv[:3] == ["nmcli", "-g", "GENERAL.CON-UUID"]:
            return Result(0, "uuid-1\n")
        if argv[:2] == ["nmcli", "-g"] and argv[-3:-1] == ["connection", "show"]:
            return Result(0, "192.168.1.1\nno\n\nno\n")
        return Result(0, "")


def test_temporary_dns_touches_only_the_device_and_reverts(tmp_path: Path) -> None:
    nm = FakeNm()
    quad9 = load_dns_catalog().by_id()["quad9"]
    assert [d.connection for d in dns_nm.real_connected_devices(nm)] == ["Home:5G"]
    apply_dns(tmp_path, "wlan0", quad9, runner=nm)
    assert ["nmcli", "device", "modify", "wlan0", "ipv4.dns", "9.9.9.9,149.112.112.112", "ipv4.ignore-auto-dns", "yes",
            "ipv6.dns", "2620:fe::fe,2620:fe::9", "ipv6.ignore-auto-dns", "yes"] in nm.calls
    assert not any("connection" in c and "modify" in c for c in nm.calls)
    revert_dns(tmp_path, runner=nm)
    assert nm.calls[-1] == ["nmcli", "device", "reapply", "wlan0"]
    assert dns_nm.load_dns_state(tmp_path) is None


def test_persistent_dns_backs_up_original_once_and_restores(tmp_path: Path) -> None:
    nm = FakeNm()
    catalog = load_dns_catalog().by_id()
    apply_dns(tmp_path, "wlan0", catalog["quad9"], persistent=True, runner=nm)
    backup = tmp_path / ".zap2/dns/backup-uuid-1.json"
    assert json.loads(backup.read_text())["ipv4.dns"] == "192.168.1.1"
    assert oct(backup.stat().st_mode & 0o777) == "0o600"
    apply_dns(tmp_path, "wlan0", catalog["dnssb"], persistent=True, runner=nm)
    assert json.loads(backup.read_text())["ipv4.dns"] == "192.168.1.1"  # исходное значение, а не Quad9
    revert_dns(tmp_path, runner=nm)
    assert ["nmcli", "connection", "modify", "uuid-1", "ipv4.dns", "192.168.1.1", "ipv4.ignore-auto-dns", "no",
            "ipv6.dns", "", "ipv6.ignore-auto-dns", "no"] in nm.calls
    assert not backup.exists()


def test_vpn_and_encrypted_only_are_refused(tmp_path: Path) -> None:
    nm = FakeNm()
    catalog = load_dns_catalog().by_id()
    with pytest.raises(ValueError, match="VPN"):
        apply_dns(tmp_path, "wg0", catalog["quad9"], runner=nm)
    with pytest.raises(ValueError, match="DoH/DoT"):
        apply_dns(tmp_path, "wlan0", catalog["wikimedia"], runner=nm)


def test_dns_wire_format_round_trip() -> None:
    query = build_query("example.com", query_id=0x1234)
    answer = bytearray(query)
    answer[2:4] = b"\x81\x80"
    answer[6:8] = b"\x00\x01"
    answer += b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 60, 4) + bytes([93, 184, 216, 34])
    assert parse_a_records(bytes(answer), 0x1234) == ("93.184.216.34",)
    assert parse_a_records(bytes(answer), 0x9999) == ()


def test_udp_query_against_local_responder() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]

    def respond() -> None:
        data, addr = server.recvfrom(512)
        reply = bytearray(data)
        reply[2:4] = b"\x81\x80"
        reply[6:8] = b"\x00\x01"
        reply += b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 60, 4) + bytes([10, 0, 0, 1])
        server.sendto(bytes(reply), addr)

    thread = threading.Thread(target=respond)
    thread.start()
    try:
        result = udp_query("127.0.0.1", "x.test", timeout=2, port=port)
    finally:
        thread.join()
        server.close()
    assert result is not None and result[0] == ("10.0.0.1",)


def test_check_provider_reports_spoofing_and_interception() -> None:
    quad9 = load_dns_catalog().by_id()["quad9"]
    result = check_provider(quad9, ("blocked.test",),
                            udp=lambda server, name: (("10.10.10.10",), 5.0),
                            dot=lambda host, address, name: None,
                            doh=lambda url, name: (("203.0.113.7",), 40.0))
    assert result.spoof_names == ["blocked.test"] and "подмена" in result.to_text()
    assert result.dot_ms is None and "DoT не отвечает" in result.to_text()
    assert "перехватывается" in detect_interception(udp=lambda server, name: (("1.2.3.4",), 3.0))
    assert "не видно" in detect_interception(udp=lambda server, name: None)


def test_dns_page_renders_without_networkmanager(monkeypatch, tmp_path: Path) -> None:
    pytest.importorskip("PyQt6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(dns_nm, "run_nmcli", lambda argv: Result(127, "", "nmcli не найден"))
    from PyQt6.QtWidgets import QApplication, QLabel, QTreeWidget
    from zap2_gui.widgets.dns_page import make_dns_page

    app = QApplication.instance() or QApplication([])
    page = make_dns_page(ROOT)
    tree = page.findChild(QTreeWidget, "dnsProviderTree")
    groups = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert groups[:4] == ["Популярные", "Безопасные", "Малоизвестные", "Для ИИ"]
    assert "Больше" in tree.topLevelItem(0).text(1)
    page.refresh_runtime_state()
    assert "NetworkManager недоступен" in page.findChild(QLabel, "dnsCurrentStatus").text()
    app.processEvents()
