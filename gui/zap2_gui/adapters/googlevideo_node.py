"""Read-only discovery of GoogleVideo CDN nodes for the current network.

``googlevideo.com`` in an nfqws2 hostlist covers its subdomains, but a
Blockcheck run needs an actual rr*/r* hostname. Discovery consults fixed
Google endpoints and NEVER sends signed video URLs, credentials or cookies to
logs or to Blockcheck. No probing of candidate TCP/TLS accessibility: a
blocked node is precisely the target that Blockcheck is supposed to test.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable
from urllib.parse import unquote

REPORT_MAPPING_URL = "https://redirector.googlevideo.com/report_mapping?di=no"
REPORT_MAPPING_URLS = (
    REPORT_MAPPING_URL,
    "https://redirector.gvt1.com/report_mapping?di=no",
)
REDIRECTOR_HOST = "redirector.googlevideo.com"
WATCH_URLS = (
    "https://www.youtube.com/watch?v=jNQXAC9IVRw&hl=en",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&hl=en",
)
DEFAULT_TIMEOUT_SECONDS = 3.0
DISCOVERY_BUDGET_SECONDS = 9.0
MAX_CANDIDATES = 4
_MAX_MAPPING_BODY = 16 * 1024
_MAX_WATCH_BODY = 2 * 1024 * 1024

# Cluster IDs such as muc12s10 are encoded character-by-character into the
# sn-* shard name. This alphabet is a documented technique from GoodCheck /
# zapretgui, not a list of static CDN nodes. Never invent rr2/rr3 aliases.
_CLUSTER_FROM = "uzpkfa50vqlgb61wrmhc72xsnid83ytoje94-"
_CLUSTER_TO = "0123456789abcdefghijklmnopqrstuvwxyz-"
_CLUSTER_TABLE = str.maketrans(_CLUSTER_FROM, _CLUSTER_TO)
_CLUSTER_RE = re.compile(r"[a-z]{3}\d{1,3}[a-z]\d{1,3}")
_REPORT_TOKEN_RE = re.compile(r"=>\s*([a-z0-9-]{3,80})\b", re.IGNORECASE)
_NODE_RE = re.compile(r"sn-[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_CDN_HOST_RE = re.compile(r"(?:rr|r)\d{1,3}---sn-[a-z0-9]+(?:-[a-z0-9]+)*\.googlevideo\.com\Z")
_CDN_IN_PAGE_RE = re.compile(r"(?<![a-z0-9-])((?:rr|r)\d{1,3}---sn-[a-z0-9]+(?:-[a-z0-9]+)*\.googlevideo\.com)(?![a-z0-9.-])", re.IGNORECASE)
_STREAMING_RE = re.compile(
    r'"serverAbrStreamingUrl"\s*:\s*"https?:(?:\\?/){2}((?:rr|r)\d{1,3}---sn-[a-z0-9]+(?:-[a-z0-9]+)*\.googlevideo\.com)',
    re.IGNORECASE,
)

Fetcher = Callable[[str, float], str]
DnsCheck = Callable[[str, float], bool | None]


@dataclass(frozen=True)
class GooglevideoNode:
    """Compatibility with the original one-node report_mapping API."""

    node: str = ""
    host: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.host)

    def to_text(self) -> str:
        if self.ok:
            return (
                f"googlevideo: узел {self.node} → {self.host}\n"
                f"источник: {REPORT_MAPPING_URL}\n"
                "В hostlist достаточно строки googlevideo.com: она покрывает все узлы."
            )
        return (
            f"googlevideo: узел не определён ({self.error}).\n"
            f"Остаётся статическая альтернатива {REDIRECTOR_HOST}; это не проверка настоящего видеосервера."
        )


@dataclass(frozen=True)
class GooglevideoCandidate:
    host: str
    source: str  # player | redirector
    dns: str  # resolved | unchecked


@dataclass(frozen=True)
class GooglevideoDiscovery:
    candidates: tuple[GooglevideoCandidate, ...] = ()
    rejected_dns: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def hosts(self) -> tuple[str, ...]:
        return tuple(candidate.host for candidate in self.candidates)

    @property
    def ok(self) -> bool:
        return bool(self.candidates)

    def to_text(self) -> str:
        lines = ["GoogleVideo CDN discovery (без sudo; текущая сеть; без кеша):"]
        if self.candidates:
            for item in self.candidates:
                source = "страница YouTube" if item.source == "player" else "report_mapping"
                dns = "DNS разрешён" if item.dns == "resolved" else "DNS не удалось проверить"
                lines.append(f"  - {item.host} [{source}; {dns}]")
        else:
            lines.append("  реальных видеосерверов не обнаружено; используются статические альтернативы пресета")
        if self.rejected_dns:
            lines.append("  DNS не разрешил (не добавлены): " + ", ".join(self.rejected_dns))
        for note in self.notes:
            lines.append(f"  {note}")
        lines.append("Страница YouTube — тестовый ролик, не открытая вкладка пользователя; обнаруженные узлы не кешируются.")
        lines.append(
            "DNS не доказывает доступность TCP/TLS/QUIC; доступность и стратегии проверит Blockcheck. "
            "redirector.googlevideo.com — запасной служебный адрес, не доказательство работы видеопотока."
        )
        return "\n".join(lines)


def normalize_googlevideo_host(value: str) -> str:
    host = str(value or "").strip().lower().rstrip(".")
    return host if len(host) <= 253 and _CDN_HOST_RE.fullmatch(host) else ""


def cluster_to_node(cluster: str) -> str:
    token = str(cluster or "").strip().lower()
    if not _CLUSTER_RE.fullmatch(token) or any(char not in _CLUSTER_FROM for char in token):
        return ""
    node = "sn-" + token.translate(_CLUSTER_TABLE)
    return node if _NODE_RE.fullmatch(node) else ""


def parse_report_mapping(text: str) -> str:
    """Return sn-* from a mapping response; accept explicit node or encoded cluster."""
    for line in str(text or "").splitlines():
        match = _REPORT_TOKEN_RE.search(line)
        if match is None:
            continue
        token = match.group(1).lower()
        if _NODE_RE.fullmatch(token):
            return token
        node = cluster_to_node(token)
        if node:
            return node
    return ""


def node_host(node: str, index: int = 1) -> str:
    """Format a reported node. Other rr indices must not be assumed live."""
    return f"rr{index}---{node}.googlevideo.com"


def extract_googlevideo_hosts(page: str) -> tuple[str, ...]:
    """Extract real hostnames only; never retain signed URL paths or tokens."""
    decoded = html.unescape(str(page or ""))
    # YouTube sometimes embeds percent-encoded and JSON-escaped URLs.
    for _ in range(2):
        updated = unquote(decoded)
        if updated == decoded:
            break
        decoded = updated
    decoded = re.sub(r"\\u00(2e|2d)", lambda m: "." if m.group(1).lower() == "2e" else "-", decoded, flags=re.I)
    decoded = decoded.replace("\\/", "/")
    stream = _STREAMING_RE.search(decoded)
    matches = ([stream.group(1)] if stream else []) + [m.group(1) for m in _CDN_IN_PAGE_RE.finditer(decoded)]
    return tuple(dict.fromkeys(host for item in matches if (host := normalize_googlevideo_host(item))))


def _urllib_fetch(url: str, timeout: float) -> str:
    # This function is private and called only for the fixed endpoints above.
    is_watch = url in WATCH_URLS
    if url not in REPORT_MAPPING_URLS and not is_watch:
        raise ValueError("Googlevideo discovery URL is not allowed")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html" if is_watch else "text/plain",
    }
    request = urllib.request.Request(url, headers=headers)
    max_bytes = _MAX_WATCH_BODY if is_watch else _MAX_MAPPING_BODY
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    remaining = max_bytes
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed endpoints
        while remaining > 0 and time.monotonic() < deadline:
            chunk = response.read(min(32 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _dns_resolves(host: str, timeout: float) -> bool | None:
    """Bounded NSS resolution on Linux; no TCP/TLS probes or external DNS APIs.

    Return None when unavailable/timed out (unknown), False only for definite
    resolver failure. Do not block a GUI worker forever on socket.getaddrinfo.
    """
    binary = shutil.which("getent")
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "ahosts", host],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=max(0.1, timeout), check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return result.returncode == 0


def resolve_googlevideo_node(fetch: Fetcher | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> GooglevideoNode:
    """Original single-report API, including encoded cluster support."""
    try:
        body = (fetch or _urllib_fetch)(REPORT_MAPPING_URL, timeout)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return GooglevideoNode(error=f"redirector не ответил: {type(exc).__name__}")
    node = parse_report_mapping(body)
    if not node:
        return GooglevideoNode(error="в ответе redirector нет допустимого узла/кластера")
    return GooglevideoNode(node=node, host=node_host(node))


def discover_googlevideo_candidates(
    fetch: Fetcher | None = None,
    dns_check: DnsCheck | None = None,
    *,
    budget_seconds: float = DISCOVERY_BUDGET_SECONDS,
    max_candidates: int = MAX_CANDIDATES,
    cancelled: Callable[[], bool] | None = None,
) -> GooglevideoDiscovery:
    """Discover up to max_candidates on demand, prefer actual player nodes.

    The only network input is from fixed HTTPS endpoints. No remote data is
    executed. DNS resolution excludes definitively unresolved names but keeps
    unknown/time-limited results, since DNS interception is itself possible.
    """
    fetcher = fetch or _urllib_fetch
    checker = dns_check or _dns_resolves
    is_cancelled = cancelled or (lambda: False)
    deadline = time.monotonic() + max(0.1, float(budget_seconds))
    limit = min(MAX_CANDIDATES, max(1, int(max_candidates)))
    notes: list[str] = []
    mapped = ""
    player: list[str] = []

    # Mapping is inexpensive and still works when the YouTube watch page is blocked.
    for url in REPORT_MAPPING_URLS:
        if is_cancelled() or deadline <= time.monotonic():
            break
        try:
            node = parse_report_mapping(fetcher(url, min(DEFAULT_TIMEOUT_SECONDS, max(0.1, deadline - time.monotonic()))))
        except (OSError, ValueError, urllib.error.URLError):
            continue
        if node:
            mapped = normalize_googlevideo_host(node_host(node))
            if mapped:
                break

    # A watch page is a source of multiple actual hosts; no URLs or query values are retained.
    for url in WATCH_URLS:
        if is_cancelled() or deadline <= time.monotonic() or len(player) >= limit:
            break
        try:
            hosts = extract_googlevideo_hosts(fetcher(url, min(DEFAULT_TIMEOUT_SECONDS, max(0.1, deadline - time.monotonic()))))
        except (OSError, ValueError, urllib.error.URLError):
            continue
        for host in hosts:
            if host not in player:
                player.append(host)
        if player:
            break  # Another video is a fallback, not an extra network request.

    if is_cancelled():
        return GooglevideoDiscovery(notes=("обнаружение отменено",))
    if not player:
        notes.append("страница YouTube не предоставила CDN-хосты")
    if not mapped:
        notes.append("report_mapping не предоставил узел")

    # Reserve a slot for an independent mapping node, but keep the next page
    # candidate as fallback if DNS definitively rejects the mapped address.
    found = [(host, "player") for host in player[:limit]]
    if mapped and mapped not in player:
        if len(found) == limit:
            found.insert(limit - 1, (mapped, "redirector"))
        else:
            found.append((mapped, "redirector"))
    elif mapped in player:
        notes.append("узел report_mapping совпал с узлом страницы")

    accepted: list[GooglevideoCandidate] = []
    rejected: list[str] = []
    for host, source in found:
        if len(accepted) >= limit:
            break
        if is_cancelled():
            return GooglevideoDiscovery(notes=("обнаружение отменено",))
        if time.monotonic() >= deadline:
            accepted.append(GooglevideoCandidate(host, source, "unchecked"))
            continue
        dns = checker(host, min(1.25, max(0.1, deadline - time.monotonic())))
        if dns is False:
            rejected.append(host)
            continue
        accepted.append(GooglevideoCandidate(host, source, "resolved" if dns is True else "unchecked"))
    return GooglevideoDiscovery(tuple(accepted), tuple(rejected), tuple(notes))


def googlevideo_node_to_text(fetch: Fetcher | None = None) -> str:
    return resolve_googlevideo_node(fetch).to_text()


if __name__ == "__main__":  # pragma: no cover
    print(discover_googlevideo_candidates().to_text())


__all__ = [
    "GooglevideoCandidate", "GooglevideoDiscovery", "GooglevideoNode", "REDIRECTOR_HOST",
    "REPORT_MAPPING_URL", "REPORT_MAPPING_URLS", "WATCH_URLS", "cluster_to_node",
    "discover_googlevideo_candidates", "extract_googlevideo_hosts", "googlevideo_node_to_text",
    "node_host", "normalize_googlevideo_host", "parse_report_mapping", "resolve_googlevideo_node",
]
