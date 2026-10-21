"""Мосты Tor: разбор вставленных строк, поиск pluggable transports, хранение.

Строки мостов принимаются в том виде, в каком их выдают bridges.torproject.org, бот
@GetBridgesBot или письмо: ``obfs4 1.2.3.4:443 FINGERPRINT cert=… iat-mode=0``, с префиксом
``Bridge`` или без. Программа сама мосты не запрашивает (Moat выключен): обращение к
сервису мостов уже говорит наблюдателю, что вы ищете Tor.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import shutil

# транспорт -> программы, которые его умеют, в порядке предпочтения
TRANSPORT_PROGRAMS: dict[str, tuple[str, ...]] = {
    "obfs4": ("lyrebird", "obfs4proxy"),
    "meek_lite": ("lyrebird", "obfs4proxy"),
    "webtunnel": ("lyrebird", "webtunnel-client"),
    "snowflake": ("snowflake-client",),
    "conjure": ("conjure-client",),
}
PROGRAM_SEARCH_DIRS = ("/usr/bin", "/usr/local/bin", "/usr/lib/tor", "/usr/libexec/tor", "/usr/lib/tor-browser")
INSTALL_HINTS = {
    "lyrebird": "пакет lyrebird (obfs4, meek, webtunnel; в Arch — из репозитория или AUR)",
    "obfs4proxy": "пакет obfs4proxy (obfs4, meek; старый, его заменил lyrebird)",
    "snowflake-client": "пакет snowflake-pt-client или snowflake (в Arch — AUR)",
    "webtunnel-client": "нужен только если lyrebird слишком старый для webtunnel",
    "conjure-client": "собирается из gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/conjure",
}
_FINGERPRINT = re.compile(r"^[0-9A-Fa-f]{40}$")
_ARG = re.compile(r"^[A-Za-z0-9_.-]+=\S*$")


@dataclass(frozen=True)
class BridgeLine:
    transport: str  # "" — обычный мост без транспорта
    address: str
    port: int
    fingerprint: str
    args: tuple[str, ...]

    @property
    def line(self) -> str:
        parts = [self.transport] if self.transport else []
        host = f"[{self.address}]" if ":" in self.address else self.address
        parts.append(f"{host}:{self.port}")
        if self.fingerprint:
            parts.append(self.fingerprint)
        parts.extend(self.args)
        return " ".join(parts)

    @property
    def label(self) -> str:
        kind = self.transport or "обычный"
        host = f"[{self.address}]" if ":" in self.address else self.address
        return f"{kind} {host}:{self.port}"


@dataclass(frozen=True)
class BridgeParseResult:
    bridges: tuple[BridgeLine, ...]
    errors: tuple[str, ...]
    duplicates: int = 0

    @property
    def transports(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.transport for item in self.bridges if item.transport))


def _address(token: str) -> tuple[str, int]:
    if token.startswith("["):
        host, sep, port = token[1:].partition("]:")
        if not sep:
            raise ValueError(f"адрес {token}: нужен [IPv6]:порт")
    else:
        host, sep, port = token.rpartition(":")
        if not sep:
            raise ValueError(f"адрес {token}: нужен IP:порт")
    ip = ipaddress.ip_address(host)
    number = int(port)
    if not 1 <= number <= 65535:
        raise ValueError(f"адрес {token}: порт вне 1..65535")
    return str(ip), number


def parse_bridge_line(text: str) -> BridgeLine:
    tokens = text.strip().split()
    if tokens and tokens[0].lower() == "bridge":
        tokens = tokens[1:]
    if not tokens:
        raise ValueError("пустая строка")
    transport = ""
    if not re.match(r"^[\[0-9]", tokens[0]):
        transport = tokens[0].lower()
        if transport not in TRANSPORT_PROGRAMS:
            known = ", ".join(sorted(TRANSPORT_PROGRAMS))
            raise ValueError(f"неизвестный транспорт {tokens[0]!r}; поддерживаются: {known} и обычные мосты")
        tokens = tokens[1:]
    if not tokens:
        raise ValueError("нет адреса моста")
    try:
        address, port = _address(tokens[0])
    except ValueError as exc:
        raise ValueError(str(exc) if "адрес" in str(exc) else f"адрес {tokens[0]}: не IP") from exc
    rest = tokens[1:]
    fingerprint = ""
    if rest and _FINGERPRINT.match(rest[0]):
        fingerprint = rest[0].upper()
        rest = rest[1:]
    bad = [item for item in rest if not _ARG.match(item)]
    if bad:
        raise ValueError(f"непонятные части: {' '.join(bad[:3])}")
    if transport == "obfs4" and not any(item.startswith("cert=") for item in rest):
        raise ValueError("obfs4 без cert= не подключится — скопируйте строку целиком")
    if transport == "webtunnel" and not any(item.startswith("url=") for item in rest):
        raise ValueError("webtunnel без url= не подключится — скопируйте строку целиком")
    return BridgeLine(transport, address, port, fingerprint, tuple(rest))


def parse_bridges(text: str) -> BridgeParseResult:
    bridges: list[BridgeLine] = []
    errors: list[str] = []
    seen: set[str] = set()
    duplicates = 0
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            bridge = parse_bridge_line(line)
        except ValueError as exc:
            errors.append(f"строка {number}: {exc}")
            continue
        if bridge.line in seen:
            duplicates += 1
            continue
        seen.add(bridge.line)
        bridges.append(bridge)
    return BridgeParseResult(tuple(bridges), tuple(errors), duplicates)


def find_program(name: str, extra_dirs: tuple[str, ...] = PROGRAM_SEARCH_DIRS) -> str:
    found = shutil.which(name)
    if found:
        return found
    for directory in extra_dirs:
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return ""


@dataclass(frozen=True)
class TransportPrograms:
    found: dict[str, str]  # программа -> путь
    by_transport: dict[str, str]  # транспорт -> путь программы, которая его выполнит

    def missing_for(self, transports: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(item for item in transports if item not in self.by_transport)

    def to_text(self) -> str:
        lines = []
        for program in dict.fromkeys(name for names in TRANSPORT_PROGRAMS.values() for name in names):
            path = self.found.get(program)
            lines.append(f"{'✓' if path else '·'} {program}: {path or 'не найден — ' + INSTALL_HINTS.get(program, '')}")
        return "\n".join(lines)


def detect_transport_programs(finder=find_program) -> TransportPrograms:
    found: dict[str, str] = {}
    for names in TRANSPORT_PROGRAMS.values():
        for name in names:
            if name not in found:
                path = finder(name)
                if path:
                    found[name] = path
    by_transport = {}
    for transport, names in TRANSPORT_PROGRAMS.items():
        for name in names:
            if name in found:
                by_transport[transport] = found[name]
                break
    return TransportPrograms(found, by_transport)


def plugin_groups(transports: tuple[str, ...], programs: TransportPrograms) -> tuple[tuple[tuple[str, ...], str], ...]:
    """Транспорты, сгруппированные по программе: одна строка ClientTransportPlugin на программу."""

    groups: dict[str, list[str]] = {}
    for transport in transports:
        path = programs.by_transport.get(transport)
        if path:
            groups.setdefault(path, []).append(transport)
    return tuple((tuple(items), path) for path, items in groups.items())


def bridges_path(tor_root: Path) -> Path:
    return tor_root / "bridges.txt"


def save_bridges(tor_root: Path, bridges: tuple[BridgeLine, ...]) -> Path:
    path = bridges_path(tor_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(item.line + "\n" for item in bridges), encoding="utf-8")
    os.chmod(tmp, 0o600)  # адреса мостов не публичны: их раскрытие помогает их заблокировать
    os.replace(tmp, path)
    return path


def load_bridges(tor_root: Path) -> tuple[BridgeLine, ...]:
    path = bridges_path(tor_root)
    if not path.is_file():
        return ()
    return parse_bridges(path.read_text(encoding="utf-8")).bridges


def bridges_digest(bridges: tuple[BridgeLine, ...]) -> str:
    return hashlib.sha256("".join(item.line + "\n" for item in bridges).encode()).hexdigest()


__all__ = [
    "BridgeLine",
    "BridgeParseResult",
    "INSTALL_HINTS",
    "TRANSPORT_PROGRAMS",
    "TransportPrograms",
    "bridges_digest",
    "bridges_path",
    "detect_transport_programs",
    "find_program",
    "load_bridges",
    "parse_bridge_line",
    "parse_bridges",
    "plugin_groups",
    "save_bridges",
]
