"""Порядок профилей пресета: кто кого перекрывает и кто сработает первым.

nfqws2 проверяет профили сверху вниз и берёт первый, чьи условия совпали. Условия
профиля объединяются через «И»: протокол и порт, L3, L7, домен (hostlist), адрес
(ipset), прочие фильтры (fwmark, ssid). Исключения (``--hostlist-exclude*``,
``--ipset-exclude*``) вычитаются из условий своего профиля.

Модуль только читает: argv пресета и, через ``ListResolver``, файлы hostlist/ipset.
Без Qt и без сети. Всё, что нельзя проверить статически (нечитаемый список,
``--hostlist-auto``, разные fwmark), даёт «не знаю», а не догадку.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
from pathlib import Path
from typing import Callable, Iterable

from .preset import TrafficProfile, ZapretPreset

PORT_MAX = 65535
_HOST_FILTER_PREFIXES = ("--hostlist=", "--hostlist-domains=", "--hostlist-auto=")
_IP_FILTER_PREFIXES = ("--ipset=", "--ipset-ip=")
_OTHER_FILTER_PREFIXES = ("--filter-mark=", "--filter-ssid", "--filter-ssid-neg")
_AUTO_L7 = {("tcp", 443): "tls", ("tcp", 80): "http", ("udp", 443): "quic"}

Network = ipaddress.IPv4Network | ipaddress.IPv6Network
# Путь списка из argv -> строки файла или None, если файл не прочитать.
ListResolver = Callable[[str], "tuple[str, ...] | None"]

SUPERSET, NARROWER, OVERLAP, DISJOINT, UNKNOWN = "superset", "narrower", "overlap", "disjoint", "unknown"


# --- значения условий ------------------------------------------------------------------

def _merge(ranges: Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    result: list[list[int]] = []
    for lo, hi in sorted(ranges):
        if result and lo <= result[-1][1] + 1:
            result[-1][1] = max(result[-1][1], hi)
        else:
            result.append([lo, hi])
    return tuple((lo, hi) for lo, hi in result)


def parse_ports(values: Iterable[str]) -> tuple[tuple[int, int], ...]:
    """``80,443,1000-2000``, ``*`` и ``~X`` (всё, кроме X) -> отсортированные диапазоны."""

    positive: list[tuple[int, int]] = []
    negative: list[tuple[int, int]] = []
    for raw in values:
        token = raw.strip()
        if not token:
            continue
        target = positive
        if token.startswith("~"):
            target, token = negative, token[1:]
        if token == "*":
            target.append((0, PORT_MAX))
            continue
        lo_text, _sep, hi_text = token.partition("-")
        lo = int(lo_text)
        hi = int(hi_text) if hi_text else lo
        if not 0 <= lo <= hi <= PORT_MAX:
            raise ValueError(f"порт вне диапазона: {raw}")
        target.append((lo, hi))
    base = _merge(positive) if positive else ((0, PORT_MAX),)
    if not negative:
        return base
    result = list(base)
    for nlo, nhi in _merge(negative):
        cut: list[tuple[int, int]] = []
        for lo, hi in result:
            if nhi < lo or nlo > hi:
                cut.append((lo, hi))
                continue
            if lo < nlo:
                cut.append((lo, nlo - 1))
            if nhi < hi:
                cut.append((nhi + 1, hi))
        result = cut
    return tuple(result)


def _ranges_contain(outer: tuple[tuple[int, int], ...], inner: tuple[tuple[int, int], ...]) -> bool:
    return all(any(olo <= lo and hi <= ohi for olo, ohi in outer) for lo, hi in inner)


def _ranges_intersect(a: tuple[tuple[int, int], ...], b: tuple[tuple[int, int], ...]) -> bool:
    return any(alo <= bhi and blo <= ahi for alo, ahi in a for blo, bhi in b)


def _port_in(ranges: tuple[tuple[int, int], ...], port: int) -> bool:
    return any(lo <= port <= hi for lo, hi in ranges)


def _ports_text(ranges: tuple[tuple[int, int], ...]) -> str:
    return ",".join(str(lo) if lo == hi else f"{lo}-{hi}" for lo, hi in ranges)


def normalize_domain(value: str) -> str:
    text = value.strip().lower().rstrip(".")
    if "://" in text:
        text = text.split("://", 1)[1]
    return text.split("/", 1)[0].split(":", 1)[0]


def _list_domains(lines: Iterable[str]) -> tuple[str, ...]:
    result = []
    for line in lines:
        item = line.split("#", 1)[0].strip()
        if item:
            result.append(item.lower().rstrip("."))
    return tuple(result)


@dataclass(frozen=True)
class DomainSet:
    """Домены hostlist: запись покрывает себя и поддомены, ``^имя`` — только само имя."""

    suffixes: frozenset[str]
    exact: frozenset[str] = frozenset()

    @classmethod
    def from_items(cls, items: Iterable[str]) -> "DomainSet":
        suffixes, exact = set(), set()
        for raw in items:
            if raw.startswith("^"):
                exact.add(normalize_domain(raw[1:]))
            elif normalize_domain(raw):
                suffixes.add(normalize_domain(raw))
        return cls(frozenset(suffixes), frozenset(exact))

    @property
    def items(self) -> tuple[str, ...]:
        return tuple(sorted(self.suffixes | {"^" + item for item in self.exact}))

    def covers(self, host: str) -> bool:
        name = normalize_domain(host)
        if name in self.exact or name in self.suffixes:
            return True
        parts = name.split(".")
        return any(".".join(parts[index:]) in self.suffixes for index in range(1, len(parts)))

    def covers_entry(self, entry: str) -> bool:
        """Покрывает ли набор всё, что ловит одна запись другого hostlist."""

        if entry.startswith("^"):
            return self.covers(entry[1:])
        name = normalize_domain(entry)
        if name in self.suffixes:
            return True
        parts = name.split(".")
        return any(".".join(parts[index:]) in self.suffixes for index in range(1, len(parts)))

    def touches_entry(self, entry: str) -> bool:
        """Есть ли хоть один общий хост с записью (она внутри набора или набор внутри неё)."""

        if self.covers_entry(entry):
            return True
        if entry.startswith("^"):
            return False
        name = normalize_domain(entry)
        tail = "." + name
        return any(item.endswith(tail) for item in self.suffixes | self.exact)


def _networks(values: Iterable[str]) -> tuple[Network, ...]:
    result = []
    for raw in values:
        item = raw.split("#", 1)[0].strip()
        if item:
            result.append(ipaddress.ip_network(item, strict=False))
    return tuple(result)


def _net_covered(net: Network, by: tuple[Network, ...]) -> bool:
    return any(net.version == other.version and net.subnet_of(other) for other in by)  # type: ignore[arg-type]


def _nets_touch(a: tuple[Network, ...], b: tuple[Network, ...]) -> bool:
    return any(x.version == y.version and x.overlaps(y) for x in a for y in b)


# --- профиль как набор условий ---------------------------------------------------------

@dataclass(frozen=True)
class ProfileConditions:
    index: int
    name: str
    enabled: bool
    # протокол -> диапазоны портов; "other" — не TCP/UDP. Пусто = профиль без протокольного фильтра.
    transport: dict[str, tuple[tuple[int, int], ...]]
    l3: frozenset[str]
    l7: frozenset[str]
    hosts: DomainSet | None
    nets: tuple[Network, ...] | None
    exclude_hosts: DomainSet
    exclude_nets: tuple[Network, ...]
    other: tuple[str, ...]
    unknown: tuple[str, ...] = ()

    @property
    def has_host_filter(self) -> bool:
        return self.hosts is not None

    def transport_text(self) -> str:
        if not self.transport:
            return "любой протокол"
        parts = []
        for proto in ("tcp", "udp"):
            if proto in self.transport:
                parts.append(f"{proto.upper()} {_ports_text(self.transport[proto])}")
        return ", ".join(parts)


def _values(args: Iterable[str], prefix: str) -> list[str]:
    return [item.strip() for arg in args if arg.startswith(prefix) for item in arg.partition("=")[2].split(",") if item.strip()]


def _paths(args: Iterable[str], prefix: str) -> list[str]:
    return [arg.partition("=")[2].strip() for arg in args if arg.startswith(prefix) and arg.partition("=")[2].strip()]


def profile_conditions(profile: TrafficProfile, resolver: ListResolver | None = None) -> ProfileConditions:
    args = profile.raw_args
    unknown: list[str] = []

    def read_list(path: str) -> tuple[str, ...]:
        lines = resolver(path) if resolver is not None else None
        if lines is None:
            unknown.append(f"список {path} не прочитан")
            return ()
        return lines

    transport: dict[str, tuple[tuple[int, int], ...]] = {}
    for proto in ("tcp", "udp"):
        values = _values(args, f"--filter-{proto}=")
        if values:
            try:
                transport[proto] = parse_ports(values)
            except ValueError as exc:
                unknown.append(str(exc))
                transport[proto] = ((0, PORT_MAX),)

    hosts: DomainSet | None = None
    if any(arg.startswith(_HOST_FILTER_PREFIXES) for arg in args):
        items = list(_values(args, "--hostlist-domains="))
        for path in _paths(args, "--hostlist="):
            items.extend(_list_domains(read_list(path)))
        if any(arg.startswith("--hostlist-auto=") for arg in args):
            unknown.append("--hostlist-auto пополняется на ходу")
        hosts = DomainSet.from_items(items)
        if not hosts.items:
            hosts = None  # пустые листы nfqws2 приравнивает к отсутствию фильтра

    nets: tuple[Network, ...] | None = None
    if any(arg.startswith(_IP_FILTER_PREFIXES) for arg in args):
        items = list(_values(args, "--ipset-ip="))
        for path in _paths(args, "--ipset="):
            items.extend(read_list(path))
        try:
            nets = _networks(items)
        except ValueError as exc:
            unknown.append(f"ipset: {exc}")
            nets = ()

    exclude_items = list(_values(args, "--hostlist-exclude-domains="))
    for path in _paths(args, "--hostlist-exclude="):
        exclude_items.extend(_list_domains(read_list(path)))
    exclude_net_items = list(_values(args, "--ipset-exclude-ip="))
    for path in _paths(args, "--ipset-exclude="):
        exclude_net_items.extend(read_list(path))
    try:
        exclude_nets = _networks(exclude_net_items)
    except ValueError as exc:
        unknown.append(f"ipset-exclude: {exc}")
        exclude_nets = ()

    return ProfileConditions(
        index=profile.index,
        name=profile.name,
        enabled=profile.enabled,
        transport=transport,
        l3=frozenset(item.lower() for item in profile.traffic_filter.l3),
        l7=frozenset(item.lower() for item in profile.traffic_filter.l7),
        hosts=hosts,
        nets=nets,
        exclude_hosts=DomainSet.from_items(exclude_items),
        exclude_nets=exclude_nets,
        other=tuple(sorted(arg for arg in args if arg.startswith(_OTHER_FILTER_PREFIXES))),
        unknown=tuple(unknown),
    )


def file_list_resolver(root: Path, max_bytes: int = 32 * 1024 * 1024) -> ListResolver:
    """Читать hostlist/ipset относительно workspace; путь наружу или большой файл -> None."""

    cache: dict[str, tuple[str, ...] | None] = {}
    base = root.resolve()

    def resolve(raw: str) -> tuple[str, ...] | None:
        if raw in cache:
            return cache[raw]
        value = raw.lstrip("@").replace("\\", "/").strip()
        path = Path(value)
        result: tuple[str, ...] | None = None
        if value and not path.is_absolute() and ".." not in path.parts:
            target = (base / path).resolve()
            try:
                target.relative_to(base)
                if target.is_file() and target.stat().st_size <= max_bytes:
                    result = tuple(target.read_text(encoding="utf-8", errors="replace").splitlines())
            except (OSError, ValueError):
                result = None
        cache[raw] = result
        return result

    return resolve


# --- сравнение двух профилей -----------------------------------------------------------

def _relation(a_covers_b: bool, b_covers_a: bool, touch: bool) -> str:
    if a_covers_b:
        return SUPERSET
    if b_covers_a:
        return NARROWER
    return OVERLAP if touch else DISJOINT


def _transport_relation(a: ProfileConditions, b: ProfileConditions) -> str:
    if not a.transport:
        return SUPERSET
    if not b.transport:
        return NARROWER
    shared = set(a.transport) & set(b.transport)
    if not shared:
        return DISJOINT
    a_covers = set(b.transport) <= set(a.transport) and all(_ranges_contain(a.transport[p], b.transport[p]) for p in b.transport)
    b_covers = set(a.transport) <= set(b.transport) and all(_ranges_contain(b.transport[p], a.transport[p]) for p in a.transport)
    touch = any(_ranges_intersect(a.transport[p], b.transport[p]) for p in shared)
    return _relation(a_covers, b_covers, touch)


def _set_relation(a: frozenset[str], b: frozenset[str]) -> str:
    if not a:
        return SUPERSET
    if not b:
        return NARROWER
    return _relation(b <= a, a <= b, bool(a & b))


def _host_relation(a: ProfileConditions, b: ProfileConditions) -> tuple[str, tuple[str, ...]]:
    """Отношение по доменам и общие записи профиля ниже, которые заберёт профиль выше."""

    def taken(entry: str) -> bool:
        return (a.hosts is None or a.hosts.covers_entry(entry)) and not a.exclude_hosts.touches_entry(entry)

    if b.hosts is None:
        if a.hosts is not None:
            return NARROWER, ()
        # исключения — вырез из «всего»: профиль выше всё равно забирает почти весь трафик
        return (OVERLAP if a.exclude_hosts.items else SUPERSET), ()
    entries = b.hosts.items
    if a.hosts is None:
        shared = tuple(entry for entry in entries if taken(entry))
        if len(shared) == len(entries):
            return SUPERSET, shared
        return (OVERLAP, shared) if shared else (DISJOINT, ())
    shared = tuple(entry for entry in entries if taken(entry))
    if entries and len(shared) == len(entries):
        return SUPERSET, shared
    touching = tuple(entry for entry in entries if a.hosts.touches_entry(entry) and not a.exclude_hosts.touches_entry(entry))
    if not touching:
        return DISJOINT, ()
    if all(b.hosts.covers_entry(entry) for entry in a.hosts.items):
        return NARROWER, touching
    return OVERLAP, touching


def _net_relation(a: ProfileConditions, b: ProfileConditions) -> str:
    def taken(net: Network) -> bool:
        return not _net_covered(net, a.exclude_nets)

    if b.nets is None:
        if a.nets is not None:
            return NARROWER
        return OVERLAP if a.exclude_nets else SUPERSET
    if a.nets is None:
        return SUPERSET if all(taken(net) for net in b.nets) else OVERLAP
    a_covers = all(_net_covered(net, a.nets) and taken(net) for net in b.nets)
    b_covers = all(_net_covered(net, b.nets) for net in a.nets)
    return _relation(a_covers, b_covers, _nets_touch(a.nets, b.nets))


def _other_relation(a: ProfileConditions, b: ProfileConditions) -> str:
    if not a.other or a.other == b.other:
        return SUPERSET
    if not b.other:
        return NARROWER
    return UNKNOWN


@dataclass(frozen=True)
class OverlapFix:
    kind: str  # "move-above" | "exclude-domains"
    label: str
    profile_index: int
    target_index: int = -1
    domains: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProfileOverlap:
    earlier: int
    later: int
    severity: str  # "error": профиль ниже никогда не сработает; "warning": часть его трафика уходит выше
    message: str
    shared_domains: tuple[str, ...] = ()
    fixes: tuple[OverlapFix, ...] = ()

    def to_text(self) -> str:
        return ("✖ " if self.severity == "error" else "⚠ ") + self.message


def _shown(items: tuple[str, ...], limit: int = 3) -> str:
    text = ", ".join(items[:limit])
    return text + (f" и ещё {len(items) - limit}" if len(items) > limit else "")


def compare_profiles(a: ProfileConditions, b: ProfileConditions) -> ProfileOverlap | None:
    """Перекрывает ли профиль ``a`` (выше) профиль ``b`` (ниже)."""

    if not a.enabled or not b.enabled or a.unknown or b.unknown:
        return None
    host_relation, shared = _host_relation(a, b)
    relations = (
        _transport_relation(a, b),
        _set_relation(a.l3, b.l3),
        _set_relation(a.l7, b.l7),
        host_relation,
        _net_relation(a, b),
        _other_relation(a, b),
    )
    if DISJOINT in relations or UNKNOWN in relations:
        return None
    if OVERLAP not in relations and NARROWER in relations:
        return None  # узкий профиль над общим — так и задумано
    a_label, b_label = f"#{a.index + 1} «{a.name}»", f"#{b.index + 1} «{b.name}»"
    fixes = [OverlapFix("move-above", f"Поднять #{b.index + 1} над #{a.index + 1}", b.index, a.index)]
    if shared:
        fixes.append(OverlapFix("exclude-domains", f"Исключить общие домены из #{a.index + 1}", a.index, domains=shared))
    if all(item == SUPERSET for item in relations):
        what = f" (в том числе {_shown(shared)})" if shared else ""
        message = f"{b_label} никогда не сработает: всё, что он ловит{what}, раньше забирает {a_label}."
        return ProfileOverlap(a.index, b.index, "error", message, shared, tuple(fixes))
    what = f": {_shown(shared)}" if shared else ""
    message = f"Часть трафика {b_label} раньше забирает {a_label}{what}."
    return ProfileOverlap(a.index, b.index, "warning", message, shared, tuple(fixes))


def find_overlaps(preset: ZapretPreset, resolver: ListResolver | None = None) -> tuple[ProfileOverlap, ...]:
    conditions = [profile_conditions(profile, resolver) for profile in preset.profiles]
    result = []
    for later_pos, later in enumerate(conditions):
        for earlier in conditions[:later_pos]:
            overlap = compare_profiles(earlier, later)
            if overlap is not None:
                result.append(overlap)
                if overlap.severity == "error":
                    break  # одного «никогда не сработает» достаточно
    return tuple(result)


# --- «кто сработает первым» -------------------------------------------------------------

@dataclass(frozen=True)
class SimulatedConnection:
    protocol: str  # tcp | udp
    port: int
    host: str = ""
    ip: str = ""
    l7: str = ""  # пусто = по порту

    @property
    def effective_l7(self) -> str:
        return self.l7.strip().lower() or _AUTO_L7.get((self.protocol, self.port), "")


@dataclass(frozen=True)
class SimulationStep:
    index: int
    name: str
    matched: bool | None
    reason: str


@dataclass(frozen=True)
class SimulationResult:
    connection: SimulatedConnection
    winner: int | None
    steps: tuple[SimulationStep, ...] = field(default_factory=tuple)
    globally_excluded: str = ""

    def to_text(self) -> str:
        conn = self.connection
        head = f"{conn.protocol.upper()} {conn.port}" + (f", {conn.host}" if conn.host else "") + (f", {conn.ip}" if conn.ip else "")
        if conn.effective_l7:
            head += f", L7 {conn.effective_l7}"
        lines = [f"Соединение: {head}"]
        if self.globally_excluded:
            lines.append(f"Не обрабатывается: {self.globally_excluded} в общих исключениях.")
            return "\n".join(lines)
        for step in self.steps:
            mark = "✓" if step.matched else ("?" if step.matched is None else "·")
            lines.append(f"{mark} #{step.index + 1} {step.name}: {step.reason}")
        if self.winner is None:
            lines.append("Ни один профиль не подошёл — соединение пройдёт без обработки.")
        else:
            lines.append(f"Сработает #{self.winner + 1}; профили ниже не проверяются.")
        return "\n".join(lines)


def _match(c: ProfileConditions, conn: SimulatedConnection) -> tuple[bool | None, str]:
    if not c.enabled:
        return False, "выключен (--skip)"
    if c.transport:
        ranges = c.transport.get(conn.protocol)
        if ranges is None:
            return False, f"ловит только {c.transport_text()}"
        if not _port_in(ranges, conn.port):
            return False, f"порт {conn.port} не в {conn.protocol.upper()} {_ports_text(ranges)}"
    ip_obj = None
    if conn.ip:
        try:
            ip_obj = ipaddress.ip_address(conn.ip)
        except ValueError:
            return None, f"неверный IP {conn.ip}"
    if c.l3:
        version = f"ipv{ip_obj.version}" if ip_obj is not None else ""
        if version and version not in c.l3:
            return False, f"L3 только {','.join(sorted(c.l3))}"
    if c.l7:
        l7 = conn.effective_l7
        if not l7:
            return False, f"нужен L7 {','.join(sorted(c.l7))}, а протокол не определён"
        if l7 not in c.l7:
            return False, f"L7 {l7} не в {','.join(sorted(c.l7))}"
    if c.unknown:
        return None, "не проверить: " + "; ".join(c.unknown)
    has_lists = c.hosts is not None or bool(c.exclude_hosts.items)
    if has_lists and not conn.host:
        # nfqws2: профиль с любым hostlist (даже только исключающим) без имени хоста не выбирается
        return False, "есть список доменов, а имя хоста не указано (или ещё не известно)"
    if conn.host and c.exclude_hosts.covers(conn.host):
        return False, f"{conn.host} в исключениях профиля"
    if c.hosts is not None and not c.hosts.covers(conn.host):
        return False, f"{conn.host} нет в hostlist"
    if c.nets is not None:
        if ip_obj is None:
            return False, "нужен IP из ipset, а IP не указан"
        if not any(ip_obj in net for net in c.nets):
            return False, f"{conn.ip} нет в ipset"
    if ip_obj is not None and any(ip_obj in net for net in c.exclude_nets):
        return False, f"{conn.ip} в исключениях профиля"
    if c.other:
        return None, "есть фильтры, которые не проверить заранее: " + ", ".join(c.other)
    return True, "все условия совпали"


def simulate_first_match(
    preset: ZapretPreset,
    connection: SimulatedConnection,
    resolver: ListResolver | None = None,
    *,
    global_exclude_hosts: Iterable[str] = (),
    global_exclude_nets: Iterable[str] = (),
) -> SimulationResult:
    excluded_hosts = DomainSet.from_items(global_exclude_hosts)
    if connection.host and excluded_hosts.covers(connection.host):
        return SimulationResult(connection, None, (), connection.host)
    if connection.ip:
        try:
            ip_obj = ipaddress.ip_address(connection.ip)
            if any(ip_obj in net for net in _networks(global_exclude_nets)):
                return SimulationResult(connection, None, (), connection.ip)
        except ValueError:
            pass
    steps = []
    winner = None
    for profile in preset.profiles:
        matched, reason = _match(profile_conditions(profile, resolver), connection)
        steps.append(SimulationStep(profile.index, profile.name, matched, reason))
        if matched:
            winner = profile.index
            break
    return SimulationResult(connection, winner, tuple(steps))


__all__ = [
    "DomainSet",
    "OverlapFix",
    "ProfileConditions",
    "ProfileOverlap",
    "SimulatedConnection",
    "SimulationResult",
    "SimulationStep",
    "compare_profiles",
    "file_list_resolver",
    "find_overlaps",
    "normalize_domain",
    "parse_ports",
    "profile_conditions",
    "simulate_first_match",
]
