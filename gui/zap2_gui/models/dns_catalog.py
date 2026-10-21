"""Каталог DNS-провайдеров: данные из `assets/dns/providers.json` и свои серверы пользователя.

Только данные и проверка формата, без сети и без Qt.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import ipaddress
import json
from pathlib import Path
import re
import struct
from urllib.parse import urlsplit

CATALOG_PATH = Path(__file__).resolve().parents[1] / "assets" / "dns" / "providers.json"
KNOWN_STATUSES = ("ok", "blocked", "at_risk", "high_risk")
KNOWN_FLAGS = ("dnssec", "adblock", "family", "encrypted_only")
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
_HOST = re.compile(r"(?=.{1,253}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}")


@dataclass(frozen=True)
class DnsGroup:
    group_id: str
    title: str
    tradeoff: str


@dataclass(frozen=True)
class DnsProvider:
    provider_id: str
    group: str
    name: str
    ipv4: tuple[str, ...]
    ipv6: tuple[str, ...] = ()
    doh: str | None = None
    dot: str | None = None
    flags: tuple[str, ...] = ()
    status: str = "ok"
    note: str = ""

    @property
    def plain_dns_works(self) -> bool:
        return "encrypted_only" not in self.flags

    def to_dict(self) -> dict:
        return {"id": self.provider_id, "group": self.group, "name": self.name, "ipv4": list(self.ipv4),
                "ipv6": list(self.ipv6), "doh": self.doh, "dot": self.dot, "flags": list(self.flags),
                "status": self.status, "note": self.note}


@dataclass(frozen=True)
class DnsCatalog:
    groups: tuple[DnsGroup, ...]
    providers: tuple[DnsProvider, ...]
    statuses: dict[str, str] = field(default_factory=dict)

    def by_id(self) -> dict[str, DnsProvider]:
        return {p.provider_id: p for p in self.providers}

    def in_group(self, group_id: str) -> tuple[DnsProvider, ...]:
        return tuple(p for p in self.providers if p.group == group_id)


def _addresses(values: object, version: int, where: str) -> tuple[str, ...]:
    result = []
    for value in values or ():
        address = ipaddress.ip_address(str(value))
        if address.version != version or not address.is_global:
            raise ValueError(f"{where}: {value} — не публичный IPv{version}")
        result.append(str(address))
    return tuple(result)


def validate_doh_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or not _HOST.fullmatch(parts.hostname) or parts.username or parts.password:
        raise ValueError(f"DoH должен быть https://имя/путь без логина: {url}")
    return url


def provider_from_dict(raw: dict, groups: set[str]) -> DnsProvider:
    pid = str(raw.get("id", ""))
    if not _ID.fullmatch(pid):
        raise ValueError(f"неверный id провайдера: {pid!r}")
    group = str(raw.get("group", ""))
    if group not in groups:
        raise ValueError(f"{pid}: неизвестная группа {group!r}")
    status = str(raw.get("status", "ok"))
    if status not in KNOWN_STATUSES:
        raise ValueError(f"{pid}: неизвестный статус {status!r}")
    flags = tuple(str(f) for f in raw.get("flags", ()))
    if any(f not in KNOWN_FLAGS for f in flags):
        raise ValueError(f"{pid}: неизвестный флаг в {flags}")
    doh = raw.get("doh")
    dot = raw.get("dot")
    if doh:
        validate_doh_url(str(doh))
    if dot and not _HOST.fullmatch(str(dot)):
        raise ValueError(f"{pid}: неверное имя DoT {dot!r}")
    ipv4 = _addresses(raw.get("ipv4"), 4, pid)
    ipv6 = _addresses(raw.get("ipv6"), 6, pid)
    if not ipv4 and not ipv6:
        raise ValueError(f"{pid}: нет адресов")
    return DnsProvider(pid, group, str(raw.get("name") or pid), ipv4, ipv6, str(doh) if doh else None,
                       str(dot) if dot else None, flags, status, str(raw.get("note", "")))


def load_dns_catalog(path: Path = CATALOG_PATH, custom: tuple[DnsProvider, ...] = ()) -> DnsCatalog:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("formatVersion") != 1:
        raise ValueError("неизвестный формат каталога DNS")
    groups = tuple(DnsGroup(str(g["id"]), str(g["title"]), str(g["tradeoff"])) for g in data["groups"])
    ids = {g.group_id for g in groups}
    providers = [provider_from_dict(raw, ids) for raw in data["providers"]]
    seen = {p.provider_id for p in providers}
    for item in custom:
        if item.provider_id not in seen:
            providers.append(item)
            seen.add(item.provider_id)
    return DnsCatalog(groups, tuple(providers), dict(data.get("statuses", {})))


def custom_provider(name: str, doh_url: str, ipv4: tuple[str, ...], ipv6: tuple[str, ...] = ()) -> DnsProvider:
    """Свой сервер: достаточно DoH URL, адреса подставляет вызывающий (из резолва имени)."""

    validate_doh_url(doh_url)
    host = urlsplit(doh_url).hostname or "custom"
    pid = "custom-" + re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")[:40]
    return provider_from_dict({"id": pid, "group": "custom", "name": name.strip() or host, "ipv4": list(ipv4),
                               "ipv6": list(ipv6), "doh": doh_url, "dot": None}, {"custom"})


def doh_stamp(provider: DnsProvider) -> str:
    """DNS stamp (sdns://) для dnscrypt-proxy: протокол 0x02 (DoH), без закреплённых хэшей сертификата."""

    if not provider.doh:
        raise ValueError(f"{provider.name}: нет DoH")
    parts = urlsplit(provider.doh)
    props = 1 if "dnssec" in provider.flags else 0

    def lp(value: str) -> bytes:
        raw = value.encode()
        if len(raw) > 255:
            raise ValueError("слишком длинное поле stamp")
        return bytes([len(raw)]) + raw

    address = provider.ipv4[0] if provider.ipv4 else ""
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    body = b"\x02" + struct.pack("<Q", props) + lp(address) + b"\x00" + lp(parts.hostname or "") + lp(path)
    return "sdns://" + base64.urlsafe_b64encode(body).decode().rstrip("=")


__all__ = ["CATALOG_PATH", "DnsCatalog", "DnsGroup", "DnsProvider", "custom_provider", "doh_stamp",
           "load_dns_catalog", "provider_from_dict", "validate_doh_url"]
