"""Проверка DNS-провайдера и признаков перехвата DNS у провайдера связи.

Только стандартная библиотека, без root. Что проверяется:

* обычный DNS (UDP 53) — отвечает ли и за сколько;
* DoT (TCP 853 + TLS с именем сервера) и DoH (HTTPS, RFC 8484) — доступны ли;
* перехват: запрос на адрес из TEST-NET (192.0.2.53), где DNS-сервера нет. Ответ означает,
  что DNS-трафик на порт 53 перехватывает кто-то по пути (DNAT);
* подмена: ответы одного провайдера по UDP 53 и по DoH для одного имени не пересекаются.

Результат — гипотеза для текущего момента, не доказательство.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import os
import socket
import ssl
import struct
import time
from typing import Callable
import urllib.request

from ..models.dns_catalog import DnsProvider

TIMEOUT_S = 3.0
INTERCEPT_PROBE_ADDRESS = "192.0.2.53"
DEFAULT_PROBE_NAMES = ("example.com", "rutracker.org")


def build_query(name: str, qtype: int = 1, query_id: int | None = None) -> bytes:
    qid = int.from_bytes(os.urandom(2), "big") if query_id is None else query_id
    header = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    labels = b"".join(bytes([len(part)]) + part.encode("ascii") for part in name.rstrip(".").split("."))
    return header + labels + b"\x00" + struct.pack(">HH", qtype, 1)


def _skip_name(data: bytes, offset: int) -> int:
    while True:
        length = data[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0 == 0xC0:
            return offset + 2
        offset += 1 + length


def parse_a_records(data: bytes, query_id: int | None = None) -> tuple[str, ...]:
    """A/AAAA из ответа; пустой кортеж — ответа нет или он не про нас."""

    if len(data) < 12:
        return ()
    qid, flags, qd, an, _ns, _ar = struct.unpack(">HHHHHH", data[:12])
    if query_id is not None and qid != query_id:
        return ()
    if not flags & 0x8000:
        return ()
    offset = 12
    for _ in range(qd):
        offset = _skip_name(data, offset) + 4
    result = []
    for _ in range(an):
        offset = _skip_name(data, offset)
        rtype, _rclass, _ttl, length = struct.unpack(">HHIH", data[offset:offset + 10])
        offset += 10
        rdata = data[offset:offset + length]
        offset += length
        if rtype == 1 and length == 4:
            result.append(str(ipaddress.IPv4Address(rdata)))
        elif rtype == 28 and length == 16:
            result.append(str(ipaddress.IPv6Address(rdata)))
    return tuple(result)


def udp_query(server: str, name: str, timeout: float = TIMEOUT_S, port: int = 53) -> tuple[tuple[str, ...], float] | None:
    family = socket.AF_INET6 if ":" in server else socket.AF_INET
    query = build_query(name)
    qid = struct.unpack(">H", query[:2])[0]
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        started = time.monotonic()
        try:
            sock.sendto(query, (server, port))
            data, _addr = sock.recvfrom(4096)
        except OSError:
            return None
    return parse_a_records(data, qid), (time.monotonic() - started) * 1000


def dot_query(host: str, address: str, name: str, timeout: float = TIMEOUT_S) -> tuple[tuple[str, ...], float] | None:
    query = build_query(name)
    qid = struct.unpack(">H", query[:2])[0]
    context = ssl.create_default_context()
    started = time.monotonic()
    try:
        with socket.create_connection((address, 853), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                tls.sendall(struct.pack(">H", len(query)) + query)
                length = struct.unpack(">H", tls.recv(2))[0]
                data = b""
                while len(data) < length:
                    chunk = tls.recv(length - len(data))
                    if not chunk:
                        break
                    data += chunk
    except (OSError, ssl.SSLError, struct.error):
        return None
    return parse_a_records(data, qid), (time.monotonic() - started) * 1000


def doh_query(url: str, name: str, timeout: float = TIMEOUT_S) -> tuple[tuple[str, ...], float] | None:
    query = build_query(name, query_id=0)  # RFC 8484: id 0 для кэшируемости
    request = urllib.request.Request(url, data=query, method="POST",
                                     headers={"Content-Type": "application/dns-message", "Accept": "application/dns-message"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # напрямую, без системного прокси
    started = time.monotonic()
    try:
        with opener.open(request, timeout=timeout) as response:
            data = response.read(65535)
    except OSError:
        return None
    return parse_a_records(data, 0), (time.monotonic() - started) * 1000


@dataclass
class ProviderCheck:
    provider: DnsProvider
    udp_ms: float | None = None
    dot_ms: float | None = None
    doh_ms: float | None = None
    spoof_names: list[str] = field(default_factory=list)

    @property
    def best(self) -> str:
        options = [(v, k) for k, v in (("DoH", self.doh_ms), ("DoT", self.dot_ms), ("обычный", self.udp_ms)) if v is not None]
        return min(options)[1] if options else "недоступен"

    def to_text(self) -> str:
        def ms(value: float | None, available: bool) -> str:
            if not available:
                return "нет"
            return f"{value:.0f} мс" if value is not None else "не отвечает"
        p = self.provider
        line = (f"{p.name}: обычный {ms(self.udp_ms, p.plain_dns_works and bool(p.ipv4))}, "
                f"DoT {ms(self.dot_ms, bool(p.dot))}, DoH {ms(self.doh_ms, bool(p.doh))}")
        if self.spoof_names:
            line += f"; ответы по UDP и DoH различаются для {', '.join(self.spoof_names)} — возможна подмена"
        return line


Query = Callable[..., "tuple[tuple[str, ...], float] | None"]


def check_provider(provider: DnsProvider, names: tuple[str, ...] = DEFAULT_PROBE_NAMES, *,
                   udp: Query = udp_query, dot: Query = dot_query, doh: Query = doh_query) -> ProviderCheck:
    result = ProviderCheck(provider)
    address = provider.ipv4[0] if provider.ipv4 else None
    plain: dict[str, tuple[str, ...]] = {}
    if address and provider.plain_dns_works:
        for name in names:
            got = udp(address, name)
            if got:
                plain[name] = got[0]
                result.udp_ms = got[1] if result.udp_ms is None else min(result.udp_ms, got[1])
    if provider.dot and address:
        got = dot(provider.dot, address, names[0])
        if got:
            result.dot_ms = got[1]
    if provider.doh:
        for name in names:
            got = doh(provider.doh, name)
            if got:
                result.doh_ms = got[1] if result.doh_ms is None else min(result.doh_ms, got[1])
                if plain.get(name) and got[0] and not set(plain[name]) & set(got[0]):
                    result.spoof_names.append(name)
    return result


def detect_interception(udp: Query = udp_query) -> str:
    got = udp(INTERCEPT_PROBE_ADDRESS, "example.com")
    if got is None:
        return "перехвата DNS не видно: адрес без DNS-сервера не ответил"
    return ("DNS перехватывается: ответил адрес, где DNS-сервера нет (" + INTERCEPT_PROBE_ADDRESS +
            "). Обычный DNS на порт 53 подменяет кто-то по пути — нужен DoH/DoT")


__all__ = ["ProviderCheck", "build_query", "check_provider", "detect_interception", "doh_query", "dot_query",
           "parse_a_records", "udp_query"]
