"""Universal privacy-aware HAR discovery.

The analyzer accepts a browser HAR from any service. It keeps only sanitized
host/path/protocol/status/error evidence and compares observed hosts with local
hostlists. Header values, cookies, query strings, bodies, WebSocket payloads and
server IP values are never written to the report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
import zipfile

from ..models.service_targets import hostlist_entries_from_text
from ..project_paths import discover_layout

HAR_DISCOVERY_DIR = Path(".zap2") / "discovery" / "har"
HAR_SUMMARY_PREFIX = "summary-"
MAX_PATH_EXAMPLES_PER_HOST = 12

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "x-api-key",
    "x-auth-token",
    "x-csrf-token",
    "x-xsrf-token",
    "x-super-properties",
    "x-discord-token",
    "x-fingerprint",
    "x-context-properties",
    "x-captcha-key",
    "x-captcha-session-id",
}

_SNOWFLAKE_RE = re.compile(r"^\d{10,}$")
_LONG_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{24,}$")
_OPAQUE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]{10,23}$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]{16,}$")
_ERROR_CODE_RE = re.compile(
    r"(?<![A-Z0-9_])(?:NS|ERR|SEC_ERROR|SSL_ERROR|PR|MOZILLA_PKIX_ERROR)_[A-Z0-9_]{2,}",
    re.IGNORECASE,
)
_MULTI_LABEL_PUBLIC_SUFFIXES = {
    "co.uk", "org.uk", "gov.uk", "ac.uk",
    "com.au", "net.au", "org.au",
    "co.jp", "ne.jp", "or.jp",
    "com.br", "com.tr", "com.cn", "com.hk", "com.tw",
    "co.in", "co.kr", "com.sg", "com.mx", "com.ar",
    "com.ua", "com.ru", "co.nz", "co.za",
}
_BROWSER_CANCEL_CODES = {
    "NS_BINDING_ABORTED",
    "ERR_ABORTED",
    "NS_ERROR_ABORT",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _max_attention(left: str, right: str) -> str:
    rank = {"none": 0, "low": 1, "medium": 2, "high": 3}
    return left if rank.get(left, 0) >= rank.get(right, 0) else right


@dataclass(frozen=True)
class HarHostSummary:
    host: str
    domain_family: str
    request_count: int = 0
    methods: tuple[str, ...] = ()
    statuses: dict[str, int] = field(default_factory=dict)
    path_patterns: tuple[str, ...] = ()
    websocket_count: int = 0
    schemes: tuple[str, ...] = ()
    ports: tuple[str, ...] = ()
    http_versions: tuple[str, ...] = ()
    l7_hints: tuple[str, ...] = ()
    transport_hints: tuple[str, ...] = ()
    error_count: int = 0
    error_codes: tuple[str, ...] = ()
    error_categories: tuple[str, ...] = ()
    status_zero_count: int = 0
    browser_cancel_count: int = 0
    transport_failure_count: int = 0
    http_client_error_count: int = 0
    http_server_error_count: int = 0
    issue_classes: tuple[str, ...] = ()
    attention_level: str = "none"
    covered_by_default_hostlist: bool = False
    covered_by_any_hostlist: bool = False
    covering_hostlists: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def has_attention(self) -> bool:
        return self.attention_level != "none"

    @property
    def is_uncovered(self) -> bool:
        return not self.covered_by_any_hostlist

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "domainFamily": self.domain_family,
            "requestCount": self.request_count,
            "methods": list(self.methods),
            "statuses": dict(self.statuses),
            "pathPatterns": list(self.path_patterns),
            "webSocketCount": self.websocket_count,
            "schemes": list(self.schemes),
            "ports": list(self.ports),
            "httpVersions": list(self.http_versions),
            "l7Hints": list(self.l7_hints),
            "transportHints": list(self.transport_hints),
            "errorCount": self.error_count,
            "errorCodes": list(self.error_codes),
            "errorCategories": list(self.error_categories),
            "statusZeroCount": self.status_zero_count,
            "browserCancelCount": self.browser_cancel_count,
            "transportFailureCount": self.transport_failure_count,
            "httpClientErrorCount": self.http_client_error_count,
            "httpServerErrorCount": self.http_server_error_count,
            "issueClasses": list(self.issue_classes),
            "attentionLevel": self.attention_level,
            "coveredByDefaultHostlist": self.covered_by_default_hostlist,
            "coveredByAnyHostlist": self.covered_by_any_hostlist,
            "coveringHostlists": list(self.covering_hostlists),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class HarSummary:
    created_at: str
    source_name: str
    har_entry_count: int
    websocket_entry_count: int
    unique_host_count: int
    server_ip_unique_count: int
    attention_host_count: int
    uncovered_host_count: int
    sensitive_header_names: tuple[str, ...] = ()
    host_summaries: tuple[HarHostSummary, ...] = ()
    warnings: tuple[str, ...] = ()
    output_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": 2,
            "createdAt": self.created_at,
            "sourceName": self.source_name,
            "redactionPolicy": {
                "storesHeaderValues": False,
                "storesCookies": False,
                "storesAuthorization": False,
                "storesQueryStrings": False,
                "storesRequestBodies": False,
                "storesResponseBodies": False,
                "storesWebSocketPayloads": False,
                "storesServerIpValues": False,
                "storesRawErrorText": False,
                "storesSanitizedErrorCodes": True,
            },
            "counts": {
                "harEntries": self.har_entry_count,
                "webSocketEntries": self.websocket_entry_count,
                "uniqueHosts": self.unique_host_count,
                "uniqueServerIps": self.server_ip_unique_count,
                "attentionHosts": self.attention_host_count,
                "uncoveredHosts": self.uncovered_host_count,
            },
            "sensitiveHeaderNamesSeen": list(self.sensitive_header_names),
            "hosts": [item.to_dict() for item in self.host_summaries],
            "warnings": list(self.warnings),
        }

    def attention_hosts(self) -> tuple[HarHostSummary, ...]:
        return tuple(item for item in self.host_summaries if item.has_attention)

    def uncovered_hosts(self) -> tuple[HarHostSummary, ...]:
        return tuple(item for item in self.host_summaries if item.is_uncovered)

    def to_text(self) -> str:
        lines = [
            "Universal HAR discovery summary",
            f"created at: {self.created_at}",
            f"source: {self.source_name}",
            "scope: any browser-visible resource; no Discord/YouTube filter",
            "executes now: yes, local HAR read only",
            "requires sudo: no",
            "mutates firewall/services: no",
            "stores credentials: no; values, queries, bodies, payloads, raw errors and server IPs are dropped",
            f"entries: {self.har_entry_count}; websocket entries: {self.websocket_entry_count}",
            f"unique hosts: {self.unique_host_count}; attention: {self.attention_host_count}; uncovered: {self.uncovered_host_count}",
            f"unique server IPs seen but not stored: {self.server_ip_unique_count}",
        ]
        if self.output_path is not None:
            lines.append(f"summary: {self.output_path}")

        lines.extend(["", "Hosts requiring attention:"])
        attention = self.attention_hosts()
        if not attention:
            lines.append("  - none")
        for item in attention:
            codes = ",".join(item.error_codes) or "none"
            issues = ",".join(item.issue_classes) or "none"
            coverage = "covered" if item.covered_by_any_hostlist else "uncovered"
            lines.append(
                f"  - {item.host} [family={item.domain_family}; level={item.attention_level}; "
                f"issues={issues}; codes={codes}; hostlist={coverage}]"
            )

        lines.extend(["", "Observed hosts missing from all local hostlists:"])
        uncovered = self.uncovered_hosts()
        if not uncovered:
            lines.append("  - none")
        for item in uncovered:
            marker = "attention" if item.has_attention else "observed"
            lines.append(f"  - {item.host} [family={item.domain_family}; {marker}]")

        lines.extend(["", "Host evidence:"])
        for item in self.host_summaries:
            methods = ",".join(item.methods) or "?"
            statuses = ",".join(f"{status}:{count}" for status, count in sorted(item.statuses.items())) or "?"
            l7 = ",".join(item.l7_hints) or "?"
            transport = ",".join(item.transport_hints) or "?"
            coverage = ",".join(item.covering_hostlists) or "none"
            lines.append(
                f"  - {item.host} [family={item.domain_family}; methods={methods}; status={statuses}; "
                f"L7={l7}; transport={transport}; hostlists={coverage}]"
            )
            for pattern in item.path_patterns[:4]:
                lines.append(f"      path: {pattern}")
            if len(item.path_patterns) > 4:
                lines.append(f"      path: ... {len(item.path_patterns) - 4} more")
            for note in item.notes:
                lines.append(f"      note: {note}")

        lines.extend(
            [
                "",
                "Interpretation:",
                "  - HAR is universal and can reveal exact failed CDN/API hosts that were absent from a preset.",
                "  - A host already suffix-covered by a hostlist can still require a different nfqws2 strategy.",
                "  - NS_BINDING_ABORTED/ERR_ABORTED is kept as browser-cancelled evidence, but alone does not prove DPI blocking.",
                "  - TCP is inferred for HTTP/1.x, HTTP/2 and WebSocket; UDP is inferred only for explicit HTTP/3/QUIC evidence.",
                "  - HAR cannot reveal arbitrary UDP flows such as voice/media packets outside HTTP/3.",
            ]
        )
        if self.warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(f"  - {item}" for item in self.warnings)
        return "\n".join(lines)


def _discovery_dir(root: Path | None = None) -> Path:
    return discover_layout(root).root / HAR_DISCOVERY_DIR


def _read_har_payload(path: Path) -> tuple[dict[str, Any], tuple[str, ...]]:
    warnings: list[str] = []
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".har") and not name.endswith("/")]
            if not names:
                raise ValueError("zip archive does not contain a .har file")
            if len(names) > 1:
                warnings.append(f"zip contains {len(names)} HAR files; using {names[0]}")
            with archive.open(names[0]) as handle:
                return json.loads(handle.read().decode("utf-8", errors="replace")), tuple(warnings)
    return json.loads(path.read_text(encoding="utf-8", errors="replace")), tuple(warnings)


def _safe_segment(segment: str) -> str:
    value = segment.strip()
    if not value:
        return value
    suffix = ""
    stem = value
    if "." in value and not value.startswith("."):
        maybe_stem, maybe_suffix = value.rsplit(".", 1)
        if 1 <= len(maybe_suffix) <= 8 and re.fullmatch(r"[A-Za-z0-9]+", maybe_suffix):
            stem = maybe_stem
            suffix = f".{maybe_suffix}"
    if _SNOWFLAKE_RE.fullmatch(stem):
        return "{id}" + suffix
    opaque = _OPAQUE_SEGMENT_RE.fullmatch(stem) and (any(ch.isdigit() for ch in stem) or "-" in stem or "_" in stem)
    if _HEX_RE.fullmatch(stem) or _LONG_TOKEN_RE.fullmatch(stem) or opaque:
        return "{token}" + suffix
    return value[:80]


def _path_pattern(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    parts = [_safe_segment(part) for part in path.split("/")]
    normalized = "/".join(parts) or "/"
    return normalized if len(normalized) <= 180 else normalized[:177] + "..."


def _host_from_url(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").strip().lower().rstrip(".")
    except ValueError:
        return ""


def domain_family(host: str) -> str:
    value = host.strip().lower().rstrip(".")
    if not value:
        return "unknown"
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    labels = [item for item in value.split(".") if item]
    if len(labels) <= 2:
        return value
    suffix2 = ".".join(labels[-2:])
    if suffix2 in _MULTI_LABEL_PUBLIC_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return suffix2


def _is_suffix_covered(host: str, entries: tuple[str, ...]) -> bool:
    return any(host == item or host.endswith(f".{item}") for item in entries if item)


def _hostlist_catalog(root: Path | None) -> dict[str, tuple[str, ...]]:
    layout = discover_layout(root)
    hostlists_dir = layout.profiles_dir / "hostlists"
    if not hostlists_dir.exists():
        return {}
    catalog: dict[str, tuple[str, ...]] = {}
    for path in sorted(hostlists_dir.glob("*.hosts")):
        entries = hostlist_entries_from_text(path.read_text(encoding="utf-8", errors="replace"))
        catalog[path.name] = entries
    return catalog


def _header_names(entry: dict[str, Any]) -> tuple[str, ...]:
    names: list[str] = []
    for section_name in ("request", "response"):
        section = entry.get(section_name) if isinstance(entry.get(section_name), dict) else {}
        headers = section.get("headers", []) if isinstance(section.get("headers", []), list) else []
        for header in headers:
            if not isinstance(header, dict):
                continue
            name = str(header.get("name", "")).strip().lower()
            if name:
                names.append(name)
    return tuple(names)


def _entry_is_websocket(entry: dict[str, Any]) -> bool:
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
    try:
        status = int(response.get("status", 0) or 0)
    except (TypeError, ValueError):
        status = 0
    url = str(request.get("url", ""))
    return bool(entry.get("_webSocketMessages")) or status == 101 or url.lower().startswith(("ws://", "wss://"))


def _entry_http_version(entry: dict[str, Any]) -> str:
    request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    return str(response.get("httpVersion") or request.get("httpVersion") or "").strip().lower()[:24]


def _entry_evidence(entry: dict[str, Any], url: str, websocket: bool) -> tuple[str, str, str, tuple[str, ...], tuple[str, ...]]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    http_version = _entry_http_version(entry)
    version_token = http_version.replace("/", "").replace("-", "")
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is None:
        port = 443 if scheme in {"https", "wss"} else 80 if scheme in {"http", "ws"} else None
    l7: set[str] = set()
    transports: set[str] = set()
    if "h3" in version_token or "http3" in version_token or "quic" in version_token:
        l7.add("quic")
        transports.add("udp")
    elif websocket:
        l7.add("websocket")
        transports.add("tcp")
        if scheme in {"wss", "https"}:
            l7.add("tls")
    elif scheme in {"https", "wss"}:
        l7.add("tls")
        transports.add("tcp")
    elif scheme in {"http", "ws"}:
        l7.add("http")
        transports.add("tcp")
    return scheme, str(port or ""), http_version, tuple(sorted(l7)), tuple(sorted(transports))


def _entry_error_values(entry: dict[str, Any]) -> tuple[str, ...]:
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    try:
        status = int(response.get("status", 0) or 0)
    except (TypeError, ValueError):
        status = 0
    values = [entry.get("_error"), entry.get("_failureText"), response.get("_error")]
    status_text = str(response.get("statusText", "") or "").strip()
    if status == 0 and status_text:
        values.append(status_text)
    return tuple(str(value).strip() for value in values if str(value or "").strip())


def _extract_error_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    codes: set[str] = set()
    for value in values:
        for match in _ERROR_CODE_RE.findall(value.upper()):
            codes.add(match.upper()[:80])
    return tuple(sorted(codes))


def _error_categories(values: tuple[str, ...], codes: tuple[str, ...]) -> tuple[str, ...]:
    combined = " ".join((*values, *codes)).lower()
    categories: set[str] = set()
    if any(code in _BROWSER_CANCEL_CODES for code in codes) or "binding aborted" in combined:
        categories.add("browser-cancelled")
    if any(token in combined for token in ("name not resolved", "dns", "resolve", "host not found", "unknown host")):
        categories.add("dns")
    if any(token in combined for token in ("timed out", "timeout", "deadline")):
        categories.add("timeout")
    if any(token in combined for token in ("ssl", "tls", "certificate", "handshake", "pkix")):
        categories.add("tls")
    if "quic" in combined:
        categories.add("quic")
    if any(token in combined for token in ("reset", "closed", "eof", "connection aborted")):
        categories.add("reset-or-closed")
    if any(token in combined for token in ("refused", "unreachable", "network changed")):
        categories.add("refused-or-unreachable")
    if any(token in combined for token in ("blocked", "denied", "access denied")):
        categories.add("blocked-or-denied")
    if values and not categories:
        categories.add("other")
    return tuple(sorted(categories))


def _entry_attention(status: int, categories: tuple[str, ...]) -> tuple[tuple[str, ...], str, bool, bool]:
    category_set = set(categories)
    issues: set[str] = set()
    transport_categories = {
        "dns", "timeout", "tls", "quic", "reset-or-closed", "refused-or-unreachable", "blocked-or-denied",
    }
    browser_cancelled = "browser-cancelled" in category_set
    transport_failure = bool(category_set & transport_categories)
    if status == 0:
        issues.add("status-zero")
    if browser_cancelled:
        issues.add("browser-cancelled")
    if transport_failure:
        issues.add("transport-failure")
    if 400 <= status < 500:
        issues.add("http-4xx")
    if status >= 500:
        issues.add("http-5xx")
    level = "none"
    if transport_failure:
        level = "high"
    elif status >= 500 or status == 429:
        level = "medium"
    elif browser_cancelled or 400 <= status < 500 or status == 0:
        level = "low"
    return tuple(sorted(issues)), level, browser_cancelled, transport_failure


def analyze_har(path: str | Path, *, root: Path | None = None) -> HarSummary:
    source = Path(path).expanduser()
    data, read_warnings = _read_har_payload(source)
    log = data.get("log") if isinstance(data.get("log"), dict) else {}
    entries = log.get("entries", []) if isinstance(log.get("entries", []), list) else []
    hostlists = _hostlist_catalog(root)
    default_entries = hostlists.get("default.hosts", ())

    host_acc: dict[str, dict[str, Any]] = {}
    sensitive_seen: set[str] = set()
    server_ips: set[str] = set()
    websocket_entries = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
        response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
        url = str(request.get("url", ""))
        host = _host_from_url(url)
        if not host:
            continue
        method = str(request.get("method", "GET") or "GET").upper()[:12]
        try:
            status = int(response.get("status", 0) or 0)
        except (TypeError, ValueError):
            status = 0
        websocket = _entry_is_websocket(entry)
        scheme, port, http_version, l7_hints, transport_hints = _entry_evidence(entry, url, websocket)
        error_values = _entry_error_values(entry)
        error_codes = _extract_error_codes(error_values)
        error_categories = _error_categories(error_values, error_codes)
        issue_classes, attention, browser_cancelled, transport_failure = _entry_attention(status, error_categories)

        if websocket:
            websocket_entries += 1
        for name in _header_names(entry):
            if name in SENSITIVE_HEADER_NAMES:
                sensitive_seen.add(name)
        server_ip = str(entry.get("serverIPAddress", "")).strip()
        if server_ip:
            server_ips.add(server_ip)

        acc = host_acc.setdefault(
            host,
            {
                "request_count": 0,
                "methods": set(),
                "statuses": {},
                "path_patterns": [],
                "websocket_count": 0,
                "schemes": set(),
                "ports": set(),
                "http_versions": set(),
                "l7_hints": set(),
                "transport_hints": set(),
                "error_count": 0,
                "error_codes": set(),
                "error_categories": set(),
                "status_zero_count": 0,
                "browser_cancel_count": 0,
                "transport_failure_count": 0,
                "http_client_error_count": 0,
                "http_server_error_count": 0,
                "issue_classes": set(),
                "attention_level": "none",
            },
        )
        acc["request_count"] += 1
        acc["methods"].add(method)
        acc["statuses"][str(status)] = acc["statuses"].get(str(status), 0) + 1
        pattern = _path_pattern(url)
        if pattern not in acc["path_patterns"] and len(acc["path_patterns"]) < MAX_PATH_EXAMPLES_PER_HOST:
            acc["path_patterns"].append(pattern)
        acc["websocket_count"] += int(websocket)
        if scheme:
            acc["schemes"].add(scheme)
        if port:
            acc["ports"].add(port)
        if http_version:
            acc["http_versions"].add(http_version)
        acc["l7_hints"].update(l7_hints)
        acc["transport_hints"].update(transport_hints)
        if error_values:
            acc["error_count"] += 1
        acc["error_codes"].update(error_codes)
        acc["error_categories"].update(error_categories)
        acc["status_zero_count"] += int(status == 0)
        acc["browser_cancel_count"] += int(browser_cancelled)
        acc["transport_failure_count"] += int(transport_failure)
        acc["http_client_error_count"] += int(400 <= status < 500)
        acc["http_server_error_count"] += int(status >= 500)
        acc["issue_classes"].update(issue_classes)
        acc["attention_level"] = _max_attention(str(acc["attention_level"]), attention)

    summaries: list[HarHostSummary] = []
    for host, acc in host_acc.items():
        covering = tuple(name for name, values in hostlists.items() if _is_suffix_covered(host, values))
        notes: list[str] = []
        if acc["browser_cancel_count"]:
            notes.append("browser-cancelled may be normal navigation/media cancellation; repeated or combined failures are stronger evidence")
        if acc["transport_failure_count"] and covering:
            notes.append("host is already suffix-covered; inspect strategy/L7 rather than only adding another hostlist entry")
        if not covering:
            notes.append("host is absent from all local hostlists and is a discovery candidate")
        attention_level = str(acc["attention_level"])
        if int(acc["browser_cancel_count"]) >= 2 and not int(acc["transport_failure_count"]):
            attention_level = _max_attention(attention_level, "medium")
        summaries.append(
            HarHostSummary(
                host=host,
                domain_family=domain_family(host),
                request_count=int(acc["request_count"]),
                methods=tuple(sorted(acc["methods"])),
                statuses=dict(sorted(acc["statuses"].items())),
                path_patterns=tuple(str(item) for item in acc["path_patterns"]),
                websocket_count=int(acc["websocket_count"]),
                schemes=tuple(sorted(acc["schemes"])),
                ports=tuple(sorted(acc["ports"], key=lambda value: int(value) if value.isdigit() else value)),
                http_versions=tuple(sorted(acc["http_versions"])),
                l7_hints=tuple(sorted(acc["l7_hints"])),
                transport_hints=tuple(sorted(acc["transport_hints"])),
                error_count=int(acc["error_count"]),
                error_codes=tuple(sorted(acc["error_codes"])),
                error_categories=tuple(sorted(acc["error_categories"])),
                status_zero_count=int(acc["status_zero_count"]),
                browser_cancel_count=int(acc["browser_cancel_count"]),
                transport_failure_count=int(acc["transport_failure_count"]),
                http_client_error_count=int(acc["http_client_error_count"]),
                http_server_error_count=int(acc["http_server_error_count"]),
                issue_classes=tuple(sorted(acc["issue_classes"])),
                attention_level=attention_level,
                covered_by_default_hostlist=_is_suffix_covered(host, default_entries),
                covered_by_any_hostlist=bool(covering),
                covering_hostlists=covering,
                notes=tuple(notes),
            )
        )

    summaries.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2, "none": 3}.get(item.attention_level, 3),
            item.covered_by_any_hostlist,
            -item.request_count,
            item.host,
        )
    )
    return HarSummary(
        created_at=_now(),
        source_name=source.name,
        har_entry_count=len(entries),
        websocket_entry_count=websocket_entries,
        unique_host_count=len(summaries),
        server_ip_unique_count=len(server_ips),
        attention_host_count=sum(item.has_attention for item in summaries),
        uncovered_host_count=sum(item.is_uncovered for item in summaries),
        sensitive_header_names=tuple(sorted(sensitive_seen)),
        host_summaries=tuple(summaries),
        warnings=tuple(read_warnings),
    )


def write_har_summary(path: str | Path, *, root: Path | None = None) -> HarSummary:
    summary = analyze_har(path, root=root)
    out_dir = _discovery_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = summary.created_at.replace(":", "").replace("-", "")
    out_path = out_dir / f"{HAR_SUMMARY_PREFIX}{stamp}.json"
    out_path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return HarSummary(**{**summary.__dict__, "output_path": out_path})


def _host_from_payload(item: dict[str, Any]) -> HarHostSummary:
    return HarHostSummary(
        host=str(item.get("host", "")),
        domain_family=str(item.get("domainFamily", "unknown")),
        request_count=int(item.get("requestCount", 0) or 0),
        methods=tuple(str(value) for value in item.get("methods", []) if str(value).strip()),
        statuses={str(key): int(value) for key, value in dict(item.get("statuses", {})).items()},
        path_patterns=tuple(str(value) for value in item.get("pathPatterns", []) if str(value).strip()),
        websocket_count=int(item.get("webSocketCount", 0) or 0),
        schemes=tuple(str(value) for value in item.get("schemes", []) if str(value).strip()),
        ports=tuple(str(value) for value in item.get("ports", []) if str(value).strip()),
        http_versions=tuple(str(value) for value in item.get("httpVersions", []) if str(value).strip()),
        l7_hints=tuple(str(value) for value in item.get("l7Hints", []) if str(value).strip()),
        transport_hints=tuple(str(value) for value in item.get("transportHints", []) if str(value).strip()),
        error_count=int(item.get("errorCount", 0) or 0),
        error_codes=tuple(str(value) for value in item.get("errorCodes", []) if str(value).strip()),
        error_categories=tuple(str(value) for value in item.get("errorCategories", []) if str(value).strip()),
        status_zero_count=int(item.get("statusZeroCount", 0) or 0),
        browser_cancel_count=int(item.get("browserCancelCount", 0) or 0),
        transport_failure_count=int(item.get("transportFailureCount", 0) or 0),
        http_client_error_count=int(item.get("httpClientErrorCount", 0) or 0),
        http_server_error_count=int(item.get("httpServerErrorCount", 0) or 0),
        issue_classes=tuple(str(value) for value in item.get("issueClasses", []) if str(value).strip()),
        attention_level=str(item.get("attentionLevel", "none")),
        covered_by_default_hostlist=bool(item.get("coveredByDefaultHostlist", False)),
        covered_by_any_hostlist=bool(item.get("coveredByAnyHostlist", False)),
        covering_hostlists=tuple(str(value) for value in item.get("coveringHostlists", []) if str(value).strip()),
        notes=tuple(str(value) for value in item.get("notes", []) if str(value).strip()),
    )


def load_har_summary(path: str | Path) -> HarSummary:
    summary_path = Path(path)
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
    hosts = tuple(_host_from_payload(item) for item in data.get("hosts", []) if isinstance(item, dict))
    return HarSummary(
        created_at=str(data.get("createdAt", "unknown")),
        source_name=str(data.get("sourceName", "unknown")),
        har_entry_count=int(counts.get("harEntries", 0) or 0),
        websocket_entry_count=int(counts.get("webSocketEntries", 0) or 0),
        unique_host_count=int(counts.get("uniqueHosts", len(hosts)) or len(hosts)),
        server_ip_unique_count=int(counts.get("uniqueServerIps", 0) or 0),
        attention_host_count=int(counts.get("attentionHosts", 0) or 0),
        uncovered_host_count=int(counts.get("uncoveredHosts", 0) or 0),
        sensitive_header_names=tuple(str(value) for value in data.get("sensitiveHeaderNamesSeen", []) if str(value).strip()),
        host_summaries=hosts,
        warnings=tuple(str(value) for value in data.get("warnings", []) if str(value).strip()),
        output_path=summary_path,
    )


def latest_har_summary(*, root: Path | None = None) -> HarSummary | None:
    out_dir = _discovery_dir(root)
    files = sorted(out_dir.glob(f"{HAR_SUMMARY_PREFIX}*.json"))
    return load_har_summary(files[-1]) if files else None


def har_plan_to_text() -> str:
    return "\n".join(
        [
            "Universal HAR discovery plan",
            "scope: sanitize a browser HAR from any resource into host/path/status/L7/error evidence",
            "executes now: no",
            "requires sudo: no",
            "mutates firewall/services: no",
            "stores credentials: no",
            "captures payloads: no; values, queries, bodies, WebSocket payloads, server IPs and raw errors are dropped",
            "keeps: exact hostnames, sanitized paths, status counts, HTTP version, safe error codes and hostlist coverage",
            "boundary: HAR infers UDP only for explicit HTTP/3/QUIC; arbitrary UDP such as voice is outside HAR",
            "next: PYTHONPATH=gui python -m zap2_gui.app --har-analyze /path/to/capture.har-or.zip",
        ]
    )


def har_analyze_to_text(path: str, *, root: Path | None = None) -> str:
    return write_har_summary(path, root=root).to_text()


def har_report_to_text(*, root: Path | None = None) -> str:
    summary = latest_har_summary(root=root)
    if summary is None:
        return "\n".join(
            [
                "Universal HAR discovery summary",
                "status: no saved HAR summaries",
                f"expected dir: {_discovery_dir(root)}",
                "next: PYTHONPATH=gui python -m zap2_gui.app --har-analyze /path/to/capture.har-or.zip",
            ]
        )
    return summary.to_text()
