#!/usr/bin/env python3
"""Сетевой вердикт: куда смотреть — локальная сеть, провайдер, DNS или DPI.

Модуль работает и как ``zap2_gui.adapters.net_verdict`` (кнопка в Blockcheck lab),
и как отдельный скрипт (``python3 net_verdict.py``). Нужна только стандартная
библиотека Python >= 3.8; внешние команды (ping, ip, getent, dig, curl) вызываются
без sudo, отсутствие любой из них пропускается с пометкой в отчёте.

Структура:

* collectors — запускают команды и сокеты (``collect_*``);
* pure parsers — ``parse_ping``, ``parse_curl_metrics``, ``classify_https_probe``;
* pure classifier — ``classify(measurements)`` → ``Verdict``; детерминирован, без сети.

Вердикт — гипотеза для текущего момента, а не доказательство. Активный zapret
меняет результат DPI-проверок, поэтому его статус пишется в отчёт.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence, Tuple

TOOL_NAME = "net-verdict"
TOOL_VERSION = "1.0.0"

# ---------------------------------------------------------------- thresholds
PING_COUNT = 30
PING_INTERVAL_S = 0.3
JUMP_MS = 30.0                 # перепад RTT между соседними ответами, считающийся скачком
GW_LOSS_BAD_PCT = 3.0          # шлюз в LAN почти никогда не теряет пакеты
GW_MDEV_BAD_MS = 15.0          # джиттер до шлюза: Wi-Fi/помехи/перегруженный роутер
GW_LOSS_RUN_BAD = 3            # серия подряд потерянных ответов шлюза — обрыв линка
GW_JUMPS_BAD = 3               # число скачков >= JUMP_MS до шлюза
EXT_LOSS_BAD_PCT = 5.0         # потери до внешних адресов
EXT_RTT_AVG_BAD_MS = 250.0     # средний RTT до anycast 1.1.1.1/8.8.8.8
EXT_MDEV_BAD_MS = 60.0
TCP_TIMEOUT_S = 4.0
CURL_CONNECT_TIMEOUT_S = 5
CURL_MAX_TIME_S = 10

DEFAULT_EXTERNAL_PING = ("1.1.1.1", "8.8.8.8")
DEFAULT_DNS_NAMES = ("example.com", "archlinux.org", "www.wikipedia.org")
PUBLIC_RESOLVER = "1.1.1.1"
CONTROL_TARGET = "example.com"
_FALLBACK_BLOCKED_TARGETS = ("www.youtube.com", "discord.com")

VERDICT_OK = "OK"
VERDICT_LOCAL_NO_ROUTE = "LOCAL_NO_ROUTE"
VERDICT_LOCAL_LINK = "LOCAL_LINK_OR_ROUTER"
VERDICT_ISP_UPLINK = "ISP_UPLINK"
VERDICT_DNS = "DNS"
VERDICT_DPI_SELECTIVE = "DPI_SELECTIVE"
VERDICT_IP_BLOCK = "IP_BLOCK"
VERDICT_INCONCLUSIVE = "INCONCLUSIVE"

PROBE_OK = "ok"
PROBE_DNS_FAIL = "dns_fail"
PROBE_TCP_FAIL = "tcp_fail"          # TCP не устанавливается: IP-блок/маршрут
PROBE_TLS_FAIL = "tls_fail"          # TCP есть, TLS не завершился: типичный SNI-DPI
PROBE_HTTP_FAIL = "http_fail"        # TLS есть, ответа нет/обрыв после handshake
PROBE_SKIPPED = "skipped"

NEXT_STEPS: Dict[str, Tuple[str, ...]] = {
    VERDICT_LOCAL_NO_ROUTE: (
        "Проверьте, что интерфейс поднят и получил адрес: `ip -br addr`, `nmcli dev status`.",
        "Переподключите Wi-Fi/кабель; проверьте DHCP и не остался ли маршрут от выключенного VPN/туннеля.",
        "zapret здесь не поможет: трафику просто некуда идти.",
    ),
    VERDICT_LOCAL_LINK: (
        "Повторите замер по кабелю или ближе к роутеру — если шлюз станет чистым, виноват Wi-Fi (помехи, канал, энергосбережение).",
        "Перезагрузите роутер, проверьте его загрузку и прошивку; посмотрите `iw dev <if> link` (сигнал, bitrate).",
        "Не меняйте стратегии zapret, пока линк до шлюза теряет пакеты: любые тесты будут шумом.",
    ),
    VERDICT_ISP_UPLINK: (
        "Шлюз чистый, проблемы дальше: проверьте `mtr -n 1.1.1.1`, где начинаются потери.",
        "Сравните с другим временем суток; при стабильных потерях — обращение к провайдеру с замерами.",
        "Это не DPI: пресеты zapret не исправят потери на канале.",
    ),
    VERDICT_DNS: (
        "Сравните ответы системного резолвера и публичного: `dig example.com`, `dig @1.1.1.1 example.com`.",
        "Проверьте /etc/resolv.conf, systemd-resolved (`resolvectl status`), DNS роутера.",
        "Если провайдер подменяет ответы — включите DoH/DoT в системе или браузере; zapret DNS не чинит.",
    ),
    VERDICT_DPI_SELECTIVE: (
        "Контроль работает, TCP до IP заблокированного хоста открывается, а TLS обрывается — признак SNI/TLS-DPI.",
        "Это зона zapret: запустите Blockcheck для этих хостов и проверьте стратегию на свежем соединении.",
        "Повторите вердикт несколько раз: одна успешная проверка ≠ устойчивая стратегия.",
    ),
    VERDICT_IP_BLOCK: (
        "TCP до IP заблокированного хоста не устанавливается — блок по IP/маршруту, а не по SNI.",
        "Десинхронизация zapret тут обычно бесполезна: нужен туннель/прокси или другие IP (CDN, IPv6).",
        "Проверьте, что адреса не подменены DNS (сравните с публичным резолвером).",
    ),
    VERDICT_OK: (
        "Явных проблем не найдено на этом наборе целей; это снимок текущего момента.",
        "Если конкретный сервис не работает — добавьте его хосты в цели и повторите, либо проверьте QUIC/UDP отдельно.",
    ),
    VERDICT_INCONCLUSIVE: (
        "Данных недостаточно или признаки противоречат друг другу; смотрите строки evidence.",
        "Повторите замер (желательно с выключенным zapret), установите недостающие утилиты (ping, curl, dig).",
    ),
}

VERDICT_TITLES = {
    VERDICT_OK: "Всё в порядке",
    VERDICT_LOCAL_NO_ROUTE: "Нет маршрута/линка",
    VERDICT_LOCAL_LINK: "Локальная сеть: Wi-Fi/кабель/роутер",
    VERDICT_ISP_UPLINK: "Провайдер/канал",
    VERDICT_DNS: "DNS",
    VERDICT_DPI_SELECTIVE: "Избирательная блокировка DPI (зона zapret)",
    VERDICT_IP_BLOCK: "Блокировка по IP",
    VERDICT_INCONCLUSIVE: "Не удалось определить",
}


# ---------------------------------------------------------------- data model
@dataclass
class PingStats:
    target: str
    label: str = ""
    transmitted: int = 0
    received: int = 0
    loss_pct: Optional[float] = None
    duplicates: int = 0
    rtt_min: Optional[float] = None
    rtt_avg: Optional[float] = None
    rtt_max: Optional[float] = None
    rtt_mdev: Optional[float] = None
    max_jump_ms: float = 0.0
    jump_count: int = 0
    longest_loss_run: int = 0
    error: str = ""

    @property
    def has_summary(self) -> bool:
        return self.loss_pct is not None

    def describe(self) -> str:
        if not self.has_summary:
            return f"{self.label or self.target} ({self.target}): нет статистики ping {self.error}".rstrip()
        rtt = "RTT нет" if self.rtt_avg is None else (
            f"RTT avg {self.rtt_avg:.1f} ms, mdev {self.rtt_mdev or 0:.1f} ms, max {self.rtt_max or 0:.1f} ms")
        return (f"{self.label or self.target} ({self.target}): потери {self.loss_pct:g}%, дубликаты {self.duplicates}, "
                f"{rtt}, макс. скачок {self.max_jump_ms:.1f} ms (≥{JUMP_MS:g} ms: {self.jump_count}), "
                f"серия потерь {self.longest_loss_run}")


@dataclass
class CurlMetrics:
    rc: int
    http_code: int = 0
    time_namelookup: float = 0.0
    time_connect: float = 0.0
    time_appconnect: float = 0.0
    time_starttransfer: float = 0.0
    remote_ip: str = ""


@dataclass
class TargetProbe:
    host: str
    role: str                       # "control" | "blocked"
    addresses: List[str] = field(default_factory=list)
    tcp_ok: Optional[bool] = None   # прямой socket connect к первому IP:443
    tcp_error: str = ""
    curl: Optional[CurlMetrics] = None
    outcome: str = PROBE_SKIPPED

    def describe(self) -> str:
        parts = [f"{self.host} [{self.role}]: {self.outcome}"]
        if self.addresses:
            parts.append("IP " + ",".join(self.addresses[:3]))
        if self.tcp_ok is not None:
            parts.append("TCP:443 " + ("ok" if self.tcp_ok else f"fail {self.tcp_error}".rstrip()))
        if self.curl is not None:
            parts.append(f"curl rc={self.curl.rc} http={self.curl.http_code} "
                         f"connect={self.curl.time_connect * 1000:.0f}ms tls={self.curl.time_appconnect * 1000:.0f}ms")
        return "; ".join(parts)


@dataclass
class DnsCheck:
    name: str
    system: List[str] = field(default_factory=list)
    public: Optional[List[str]] = None   # None — сравнение не делалось (нет dig)
    error: str = ""

    @property
    def resolved(self) -> bool:
        return bool(self.system)

    @property
    def bogons(self) -> List[str]:
        return [a for a in self.system if is_bogon(a)]

    @property
    def suspicious(self) -> bool:
        # Системный ответ с частными/bogon IP для публичного имени — признак подмены
        # (провайдерская заглушка, DNS-sinkhole). Чистый ответ публичного резолвера усиливает вывод.
        return bool(self.bogons)


@dataclass
class Measurements:
    route_v4: Optional[bool] = None
    route_v6: Optional[bool] = None
    gateway: str = ""
    gateway_ping: Optional[PingStats] = None
    external_pings: List[PingStats] = field(default_factory=list)
    dns: List[DnsCheck] = field(default_factory=list)
    probes: List[TargetProbe] = field(default_factory=list)
    zapret_status: str = "unknown"
    missing_tools: List[str] = field(default_factory=list)
    started_at: str = ""


@dataclass
class Verdict:
    code: str
    confidence: str          # low | medium | high
    evidence: List[str]
    next_steps: List[str]
    notes: List[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return VERDICT_TITLES.get(self.code, self.code)


# ---------------------------------------------------------------- pure parsers
_REPLY_RE = re.compile(r"icmp_seq=(\d+).*?time[=<]\s*([0-9]+(?:\.[0-9]+)?)")
_LOSS_RE = re.compile(r"(\d+) packets transmitted, (\d+) (?:packets )?received.*?([0-9.]+)% packet loss")
_RTT_RE = re.compile(r"(?:rtt|round-trip) min/avg/max/(?:mdev|stddev) = ([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+)")


def parse_ping(text: str, target: str = "", label: str = "", count: Optional[int] = None,
               jump_ms: float = JUMP_MS) -> PingStats:
    """Разбирает вывод iputils/busybox ping: потери, дубликаты, RTT, скачки, серии потерь."""

    stats = PingStats(target=target, label=label)
    match = _LOSS_RE.search(text)
    if match:
        stats.transmitted = int(match.group(1))
        stats.received = int(match.group(2))
        stats.loss_pct = float(match.group(3))
    match = _RTT_RE.search(text)
    if match:
        stats.rtt_min, stats.rtt_avg, stats.rtt_max, stats.rtt_mdev = (float(match.group(i)) for i in range(1, 5))

    replies: List[Tuple[int, float]] = []
    seen = set()
    for line in text.splitlines():
        if "DUP!" in line:
            stats.duplicates += 1
            continue
        reply = _REPLY_RE.search(line)
        if reply:
            seq = int(reply.group(1))
            if seq in seen:
                continue
            seen.add(seq)
            replies.append((seq, float(reply.group(2))))

    replies.sort()
    for (prev_seq, prev_rtt), (seq, rtt) in zip(replies, replies[1:]):
        if seq == prev_seq + 1:
            delta = abs(rtt - prev_rtt)
            stats.max_jump_ms = max(stats.max_jump_ms, delta)
            if delta >= jump_ms:
                stats.jump_count += 1

    total = count if count is not None else (stats.transmitted or None)
    if total is None:
        total = replies[-1][0] if replies else 0
    if not replies:
        stats.longest_loss_run = total
    else:
        first_seq = 0 if replies[0][0] == 0 else 1   # iputils начинает с 1, некоторые ping — с 0
        prev = first_seq - 1
        run = 0
        for seq, _rtt in replies:
            run = max(run, seq - prev - 1)
            prev = seq
        last_expected = first_seq + total - 1
        run = max(run, last_expected - prev)
        stats.longest_loss_run = max(run, 0)
    if stats.loss_pct is None and not replies:
        stats.error = "нет ответов и итоговой строки"
    return stats


def parse_curl_metrics(text: str, rc: int) -> CurlMetrics:
    """Разбирает строку `-w '%{http_code} %{time_namelookup} %{time_connect} %{time_appconnect} %{time_starttransfer} %{remote_ip}'`."""

    metrics = CurlMetrics(rc=rc)
    parts = text.strip().split()
    try:
        metrics.http_code = int(parts[0]) if parts else 0
        floats = [float(p) for p in parts[1:5]]
    except ValueError:
        return metrics
    floats += [0.0] * (4 - len(floats))
    metrics.time_namelookup, metrics.time_connect, metrics.time_appconnect, metrics.time_starttransfer = floats
    if len(parts) > 5:
        metrics.remote_ip = parts[5]
    return metrics


def classify_https_probe(curl: Optional[CurlMetrics], tcp_ok: Optional[bool], resolved: bool) -> str:
    """Определяет, на какой фазе сломалось HTTPS-соединение.

    Ключевое различие: TCP connect к IP проходит, а TLS — нет (SNI-DPI) против
    TCP не проходит вообще (IP-блок). curl rc: 6 — DNS, 7 — connect refused,
    28 — timeout, 35 — TLS handshake error, 56 — recv failure (часто RST).
    """

    if not resolved:
        return PROBE_DNS_FAIL
    if curl is None:
        if tcp_ok is False:
            return PROBE_TCP_FAIL
        return PROBE_SKIPPED
    if curl.rc == 0 and curl.http_code > 0:
        return PROBE_OK
    if curl.rc == 6:
        return PROBE_DNS_FAIL
    if curl.time_appconnect > 0:
        return PROBE_HTTP_FAIL
    if curl.time_connect > 0 or tcp_ok:
        return PROBE_TLS_FAIL
    return PROBE_TCP_FAIL


def is_bogon(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_unspecified or ip.is_link_local or ip.is_reserved or ip.is_multicast


def _ping_bad_external(stats: PingStats) -> List[str]:
    reasons = []
    if not stats.has_summary:
        return ["нет статистики"]
    if stats.loss_pct is not None and stats.loss_pct >= EXT_LOSS_BAD_PCT:
        reasons.append(f"потери {stats.loss_pct:g}% ≥ {EXT_LOSS_BAD_PCT:g}%")
    if stats.rtt_avg is not None and stats.rtt_avg >= EXT_RTT_AVG_BAD_MS:
        reasons.append(f"RTT avg {stats.rtt_avg:.0f} ≥ {EXT_RTT_AVG_BAD_MS:g} ms")
    if stats.rtt_mdev is not None and stats.rtt_mdev >= EXT_MDEV_BAD_MS:
        reasons.append(f"mdev {stats.rtt_mdev:.0f} ≥ {EXT_MDEV_BAD_MS:g} ms")
    return reasons


def _ping_bad_gateway(stats: PingStats) -> List[str]:
    reasons = []
    if stats.loss_pct is not None and stats.loss_pct >= GW_LOSS_BAD_PCT:
        reasons.append(f"потери {stats.loss_pct:g}% ≥ {GW_LOSS_BAD_PCT:g}%")
    if stats.rtt_mdev is not None and stats.rtt_mdev >= GW_MDEV_BAD_MS:
        reasons.append(f"mdev {stats.rtt_mdev:.1f} ≥ {GW_MDEV_BAD_MS:g} ms")
    if stats.longest_loss_run >= GW_LOSS_RUN_BAD and (stats.loss_pct or 0) < 100:
        reasons.append(f"серия потерь {stats.longest_loss_run} ≥ {GW_LOSS_RUN_BAD}")
    if stats.jump_count >= GW_JUMPS_BAD:
        reasons.append(f"скачков RTT ≥{JUMP_MS:g} ms: {stats.jump_count}")
    return reasons


# ---------------------------------------------------------------- classifier
def classify(m: Measurements) -> Verdict:
    """Чистый детерминированный классификатор: слои снизу вверх, первый сработавший побеждает."""

    evidence: List[str] = []
    notes = ["Вердикт — гипотеза для текущего момента, не доказательство."]
    if m.zapret_status not in ("not-started", "stopped", "unknown"):
        notes.append(f"zapret runtime: {m.zapret_status} — активный zapret меняет результаты DPI-проверок.")
    elif m.zapret_status == "unknown":
        notes.append("Статус zapret неизвестен; если он запущен, DPI-часть может быть искажена.")
    if m.missing_tools:
        notes.append("Нет утилит: " + ", ".join(sorted(set(m.missing_tools))))

    def make(code: str, confidence: str) -> Verdict:
        return Verdict(code, confidence, evidence, list(NEXT_STEPS[code]), notes)

    # 1. Маршрут.
    if m.route_v4 is False and m.route_v6 is not True:
        evidence.append("Нет маршрута по умолчанию IPv4" + (" и IPv6" if m.route_v6 is False else ""))
        return make(VERDICT_LOCAL_NO_ROUTE, "high")

    ext_measured = [p for p in m.external_pings if p.has_summary]
    ext_bad = {p.target: _ping_bad_external(p) for p in ext_measured}
    ext_all_bad = bool(ext_measured) and all(ext_bad.values())
    ext_all_dead = bool(ext_measured) and all((p.loss_pct or 0) >= 100 for p in ext_measured)

    # 2. Линк до шлюза.
    gw = m.gateway_ping
    gw_clean: Optional[bool] = None
    if gw is not None and gw.has_summary:
        if (gw.loss_pct or 0) >= 100:
            evidence.append(f"Шлюз {m.gateway} не отвечает на ICMP (может быть фильтр ICMP на роутере)")
        else:
            reasons = _ping_bad_gateway(gw)
            gw_clean = not reasons
            if reasons:
                evidence.append(f"Шлюз {m.gateway}: " + "; ".join(reasons))
                evidence.append(gw.describe())
                return make(VERDICT_LOCAL_LINK, "high" if ext_all_bad or len(reasons) > 1 else "medium")
            evidence.append(f"Шлюз {m.gateway} чистый: {gw.describe()}")

    # 3. Канал провайдера.
    if ext_all_bad:
        for target, reasons in ext_bad.items():
            evidence.append(f"{target}: " + "; ".join(reasons))
        if ext_all_dead and gw_clean is None:
            evidence.append("Внешние адреса не отвечают, состояние шлюза неизвестно")
        return make(VERDICT_ISP_UPLINK, "high" if gw_clean else "medium")
    for p in ext_measured:
        evidence.append(p.describe())
    if any(ext_bad.values()):
        notes.append("Часть внешних целей деградирована: " + ", ".join(t for t, r in ext_bad.items() if r))

    # 4. DNS.
    dns_failed = [d for d in m.dns if not d.resolved]
    dns_suspicious = [d for d in m.dns if d.resolved and d.suspicious]
    if m.dns and (dns_suspicious or len(dns_failed) == len(m.dns) or (dns_failed and ext_measured)):
        for d in dns_failed:
            evidence.append(f"DNS {d.name}: не разрешается {d.error}".rstrip())
        for d in dns_suspicious:
            pub = "" if d.public is None else f"; публичный резолвер: {', '.join(d.public) or '—'}"
            evidence.append(f"DNS {d.name}: системный ответ содержит bogon/частные IP {', '.join(d.bogons)}{pub}")
        confident = dns_suspicious or (ext_measured and not ext_all_bad)
        return make(VERDICT_DNS, "high" if confident and len(dns_failed) + len(dns_suspicious) > 1 else "medium")
    if m.dns:
        evidence.append(f"DNS: {len(m.dns)} имён разрешаются без подозрительных ответов")

    # 5. HTTPS: контроль против заблокированных целей.
    control = [p for p in m.probes if p.role == "control" and p.outcome != PROBE_SKIPPED]
    blocked = [p for p in m.probes if p.role == "blocked" and p.outcome != PROBE_SKIPPED]
    for p in control + blocked:
        evidence.append(p.describe())
    control_ok = bool(control) and all(p.outcome == PROBE_OK for p in control)
    if control and not control_ok:
        evidence.append("Контрольная цель HTTPS не прошла при рабочем ping/DNS")
        return make(VERDICT_INCONCLUSIVE, "low")
    tls_fail = [p for p in blocked if p.outcome in (PROBE_TLS_FAIL, PROBE_HTTP_FAIL)]
    tcp_fail = [p for p in blocked if p.outcome == PROBE_TCP_FAIL]
    dns_fail_b = [p for p in blocked if p.outcome == PROBE_DNS_FAIL]
    if control_ok and tls_fail:
        strong = [p for p in tls_fail if p.tcp_ok]
        return make(VERDICT_DPI_SELECTIVE, "high" if strong else "medium")
    if control_ok and tcp_fail:
        return make(VERDICT_IP_BLOCK, "medium")
    if control_ok and dns_fail_b:
        evidence.append("Заблокированные цели не разрешаются при рабочем DNS для контроля")
        return make(VERDICT_DNS, "medium")

    if not ext_measured and not control:
        evidence.append("Недостаточно данных: нет ни ping, ни HTTPS-замеров")
        return make(VERDICT_INCONCLUSIVE, "low")
    if control_ok and blocked and all(p.outcome == PROBE_OK for p in blocked):
        return make(VERDICT_OK, "medium" if m.zapret_status == "running" else "high")
    if control_ok or (ext_measured and not any(ext_bad.values())):
        return make(VERDICT_OK, "medium")
    return make(VERDICT_INCONCLUSIVE, "low")


# ---------------------------------------------------------------- collectors
def _run(cmd: Sequence[str], timeout: float) -> Tuple[int, str]:
    try:
        proc = subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout,
                              env={"LC_ALL": "C", "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"})
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        return 124, out if isinstance(out, str) else out.decode("utf-8", "replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def collect_routes(m: Measurements) -> None:
    if not shutil.which("ip"):
        m.missing_tools.append("ip")
        return
    rc4, out4 = _run(["ip", "-4", "route", "show", "default"], 5)
    rc6, out6 = _run(["ip", "-6", "route", "show", "default"], 5)
    m.route_v4 = bool(out4.strip()) if rc4 == 0 else None
    m.route_v6 = bool(out6.strip()) if rc6 == 0 else None
    for line in out4.splitlines():
        parts = line.split()
        if "via" in parts:
            m.gateway = parts[parts.index("via") + 1]
            break


def collect_ping(target: str, label: str, count: int = PING_COUNT, interval: float = PING_INTERVAL_S) -> PingStats:
    _rc, out = _run(["ping", "-n", "-c", str(count), "-i", str(interval), "-W", "2", target],
                    timeout=count * max(interval, 0.2) + 15)
    return parse_ping(out, target=target, label=label, count=count)


def collect_pings(m: Measurements, count: int = PING_COUNT, interval: float = PING_INTERVAL_S,
                  external: Sequence[str] = DEFAULT_EXTERNAL_PING) -> None:
    if not shutil.which("ping"):
        m.missing_tools.append("ping")
        return
    jobs = [(t, f"Внешний {i + 1}") for i, t in enumerate(external)]
    if m.gateway:
        jobs.insert(0, (m.gateway, "Шлюз"))
    # Параллельно, чтобы сравнивать один и тот же период времени.
    with ThreadPoolExecutor(max_workers=len(jobs) or 1) as pool:
        results = list(pool.map(lambda job: collect_ping(job[0], job[1], count, interval), jobs))
    for (target, _label), stats in zip(jobs, results):
        if m.gateway and target == m.gateway and m.gateway_ping is None:
            m.gateway_ping = stats
        else:
            m.external_pings.append(stats)


def resolve_system(name: str) -> Tuple[List[str], str]:
    try:
        infos = socket.getaddrinfo(name, 443, socket.AF_INET, socket.SOCK_STREAM)
    except OSError as exc:
        return [], str(exc)
    addresses: List[str] = []
    for info in infos:
        address = str(info[4][0])
        if address not in addresses:
            addresses.append(address)
    return addresses, ""


def resolve_public(name: str, resolver: str = PUBLIC_RESOLVER) -> Optional[List[str]]:
    if not shutil.which("dig"):
        return None
    rc, out = _run(["dig", "+short", "+time=3", "+tries=1", "A", name, f"@{resolver}"], 10)
    if rc != 0:
        return []
    return [line.strip() for line in out.splitlines() if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", line.strip())]


def collect_dns(m: Measurements, names: Sequence[str] = DEFAULT_DNS_NAMES) -> None:
    if not shutil.which("dig"):
        m.missing_tools.append("dig (сравнение с публичным резолвером пропущено)")
    for name in names:
        system, error = resolve_system(name)
        m.dns.append(DnsCheck(name=name, system=system, public=resolve_public(name), error=error))


def tcp_connect(address: str, port: int = 443, timeout: float = TCP_TIMEOUT_S) -> Tuple[bool, str]:
    try:
        with socket.create_connection((address, port), timeout=timeout):
            return True, ""
    except OSError as exc:
        return False, exc.__class__.__name__


def curl_https(host: str, address: str = "", timeout: int = CURL_CONNECT_TIMEOUT_S) -> Optional[CurlMetrics]:
    if not shutil.which("curl"):
        return None
    cmd = ["curl", "-4", "-sS", "-o", "/dev/null", "--connect-timeout", str(timeout), "--max-time", str(CURL_MAX_TIME_S),
           "-w", "%{http_code} %{time_namelookup} %{time_connect} %{time_appconnect} %{time_starttransfer} %{remote_ip}\\n"]
    if address:
        cmd += ["--resolve", f"{host}:443:{address}"]
    rc, out = _run(cmd + [f"https://{host}/"], CURL_MAX_TIME_S + 5)
    # stderr идёт после -w строки; берём первую строку.
    return parse_curl_metrics(out.splitlines()[0] if out else "", rc)


def probe_target(host: str, role: str) -> TargetProbe:
    probe = TargetProbe(host=host, role=role)
    probe.addresses, _error = resolve_system(host)
    if probe.addresses:
        probe.tcp_ok, probe.tcp_error = tcp_connect(probe.addresses[0])
        probe.curl = curl_https(host, probe.addresses[0])
    probe.outcome = classify_https_probe(probe.curl, probe.tcp_ok, bool(probe.addresses))
    return probe


def collect_probes(m: Measurements, control: Sequence[str], blocked: Sequence[str]) -> None:
    if not shutil.which("curl"):
        m.missing_tools.append("curl")
    jobs = [(h, "control") for h in control] + [(h, "blocked") for h in blocked if h not in control]
    with ThreadPoolExecutor(max_workers=min(6, len(jobs) or 1)) as pool:
        m.probes.extend(pool.map(lambda job: probe_target(*job), jobs))


def default_blocked_targets() -> Tuple[str, ...]:
    """Цели DPI-сравнения из реестра service targets проекта (если доступен)."""

    try:
        from ..models.service_targets import SERVICE_TARGET_PRESETS  # type: ignore
    except Exception:
        return _FALLBACK_BLOCKED_TARGETS
    hosts: List[str] = []
    for preset in SERVICE_TARGET_PRESETS.values():
        for target in preset.targets[:2]:
            if "/" not in target and target not in hosts:
                hosts.append(target)
    return tuple(hosts) or _FALLBACK_BLOCKED_TARGETS


def zapret_runtime_status(root: Optional[Path] = None) -> str:
    try:
        from .runtime_session import runtime_session_status  # type: ignore
    except Exception:
        return "unknown"
    try:
        return str(runtime_session_status(root).state)
    except Exception:
        return "unknown"


def collect_all(control: Sequence[str] = (CONTROL_TARGET,), blocked: Optional[Sequence[str]] = None,
                count: int = PING_COUNT, interval: float = PING_INTERVAL_S, root: Optional[Path] = None) -> Measurements:
    m = Measurements(started_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat())
    m.zapret_status = zapret_runtime_status(root)
    collect_routes(m)
    collect_pings(m, count, interval)
    collect_dns(m)
    collect_probes(m, control, default_blocked_targets() if blocked is None else blocked)
    return m


# ---------------------------------------------------------------- report
def report_dict(m: Measurements, v: Verdict) -> Dict[str, Any]:
    return {
        "tool": TOOL_NAME, "version": TOOL_VERSION,
        "disclaimer": "Гипотеза для текущего момента, не доказательство.",
        "verdict": {"code": v.code, "title": v.title, "confidence": v.confidence,
                    "evidence": v.evidence, "nextSteps": v.next_steps, "notes": v.notes},
        "measurements": asdict(m),
    }


def verdict_to_text(m: Measurements, v: Verdict) -> str:
    lines = [f"Сетевой вердикт: {v.code} — {v.title}", f"Уверенность: {v.confidence}", f"Время: {m.started_at}",
             f"zapret runtime: {m.zapret_status}", "", "Evidence:"]
    lines += [f"  - {e}" for e in v.evidence] or ["  (нет)"]
    lines += ["", "Что проверить дальше:"] + [f"  {i}. {s}" for i, s in enumerate(v.next_steps, 1)]
    lines += ["", "Примечания:"] + [f"  - {n}" for n in v.notes]
    return "\n".join(lines)


def save_report(m: Measurements, v: Verdict, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = reports_dir / f"net-verdict-{stamp}.json"
    path.write_text(json.dumps(report_dict(m, v), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def default_reports_dir(root: Optional[Path] = None) -> Path:
    try:
        from .runtime_state import ensure_runtime_store  # type: ignore
        return ensure_runtime_store(root).root / ".zap2" / "runtime" / "reports"
    except Exception:
        return Path.cwd() / ".zap2" / "runtime" / "reports"


def run_and_report(root: Optional[Path] = None, blocked: Optional[Sequence[str]] = None,
                   count: int = PING_COUNT) -> Tuple[str, Path]:
    m = collect_all(blocked=blocked, count=count, root=root)
    v = classify(m)
    path = save_report(m, v, default_reports_dir(root))
    return verdict_to_text(m, v) + f"\n\nJSON-отчёт: {path}", path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Сетевой вердикт: локальная сеть / провайдер / DNS / DPI.")
    parser.add_argument("--count", type=int, default=PING_COUNT, help="пакетов ping на цель")
    parser.add_argument("--control", nargs="*", default=[CONTROL_TARGET], help="нейтральные контрольные хосты")
    parser.add_argument("--blocked", nargs="*", default=None, help="хосты для DPI-сравнения")
    parser.add_argument("--json", type=Path, default=None, help="сохранить JSON-отчёт в файл")
    args = parser.parse_args(argv)
    m = collect_all(control=args.control, blocked=args.blocked, count=args.count)
    v = classify(m)
    print(verdict_to_text(m, v))
    if args.json:
        args.json.write_text(json.dumps(report_dict(m, v), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
