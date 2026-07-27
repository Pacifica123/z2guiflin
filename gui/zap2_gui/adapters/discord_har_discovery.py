"""Privacy-aware Discord HAR discovery helpers.

This module reads a user-supplied browser HAR file and writes only a sanitized
host/path/status summary. It never stores headers, cookies, request bodies,
response bodies, query strings or WebSocket payloads. The goal is to compare
observed Discord web hosts with the local service preset/hostlist, not to replay
traffic or extract credentials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
import zipfile

from ..models.service_targets import DISCORD_DESKTOP_TARGETS, service_target_host_token
from ..project_paths import discover_layout
from .discord_endpoint_discovery import DISCOVERY_DIR

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-super-properties",
    "x-discord-token",
    "x-fingerprint",
    "x-context-properties",
    "x-captcha-key",
    "x-captcha-session-id",
}

DISCORD_HAR_SUMMARY_PREFIX = "har-summary-"
MAX_PATH_EXAMPLES_PER_HOST = 12
_SNOWFLAKE_RE = re.compile(r"^\d{10,}$")
_LONG_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{24,}$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]{16,}$")


@dataclass(frozen=True)
class HarHostSummary:
    host: str
    category: str
    request_count: int = 0
    methods: tuple[str, ...] = ()
    statuses: dict[str, int] = field(default_factory=dict)
    path_patterns: tuple[str, ...] = ()
    websocket_count: int = 0
    schemes: tuple[str, ...] = ()
    http_versions: tuple[str, ...] = ()
    l7_hints: tuple[str, ...] = ()
    transport_hints: tuple[str, ...] = ()
    error_count: int = 0
    failed_status_count: int = 0
    error_categories: tuple[str, ...] = ()
    covered_by_discord_preset: bool = False
    covered_by_default_hostlist: bool = False
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "category": self.category,
            "requestCount": self.request_count,
            "methods": list(self.methods),
            "statuses": dict(self.statuses),
            "pathPatterns": list(self.path_patterns),
            "webSocketCount": self.websocket_count,
            "schemes": list(self.schemes),
            "httpVersions": list(self.http_versions),
            "l7Hints": list(self.l7_hints),
            "transportHints": list(self.transport_hints),
            "errorCount": self.error_count,
            "failedStatusCount": self.failed_status_count,
            "errorCategories": list(self.error_categories),
            "coveredByDiscordPreset": self.covered_by_discord_preset,
            "coveredByDefaultHostlist": self.covered_by_default_hostlist,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class DiscordHarSummary:
    created_at: str
    source_name: str
    har_entry_count: int
    discord_related_entry_count: int
    websocket_entry_count: int
    unique_host_count: int
    server_ip_unique_count: int
    sensitive_header_names: tuple[str, ...] = ()
    host_summaries: tuple[HarHostSummary, ...] = ()
    warnings: tuple[str, ...] = ()
    output_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
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
            },
            "counts": {
                "harEntries": self.har_entry_count,
                "discordRelatedEntries": self.discord_related_entry_count,
                "webSocketEntries": self.websocket_entry_count,
                "uniqueHosts": self.unique_host_count,
                "uniqueServerIps": self.server_ip_unique_count,
            },
            "sensitiveHeaderNamesSeen": list(self.sensitive_header_names),
            "hosts": [item.to_dict() for item in self.host_summaries],
            "warnings": list(self.warnings),
        }

    def missing_from_default_hostlist(self) -> tuple[HarHostSummary, ...]:
        return tuple(item for item in self.host_summaries if item.category != "external-other" and not item.covered_by_default_hostlist)

    def optional_discovery_hosts(self) -> tuple[HarHostSummary, ...]:
        return tuple(
            item
            for item in self.missing_from_default_hostlist()
            if item.category in {"attachment-upload", "external-discord-support", "status"}
        )

    def to_text(self) -> str:
        category_counts: dict[str, int] = {}
        for item in self.host_summaries:
            category_counts[item.category] = category_counts.get(item.category, 0) + item.request_count
        lines = [
            "Discord HAR discovery summary",
            f"created at: {self.created_at}",
            f"source: {self.source_name}",
            "executes now: yes, local HAR read only",
            "requires sudo: no",
            "mutates firewall/services: no",
            "stores credentials: no; headers, cookies, query strings, bodies and WebSocket payloads are redacted",
            f"entries: {self.har_entry_count}; discord-related: {self.discord_related_entry_count}; websocket entries: {self.websocket_entry_count}",
            f"unique hosts: {self.unique_host_count}; unique server IPs seen but not stored: {self.server_ip_unique_count}",
        ]
        if self.output_path is not None:
            lines.append(f"summary: {self.output_path}")
        lines.append("")
        lines.append("Categories:")
        if category_counts:
            for category, count in sorted(category_counts.items()):
                lines.append(f"  - {category}: {count} requests")
        else:
            lines.append("  - none")
        lines.append("")
        lines.append("Sensitive header names seen:")
        if self.sensitive_header_names:
            lines.extend(f"  - {name}" for name in self.sensitive_header_names)
        else:
            lines.append("  - none")
        lines.append("")
        lines.append("Host coverage:")
        for item in self.host_summaries:
            preset = "preset=yes" if item.covered_by_discord_preset else "preset=no"
            hostlist = "hostlist=yes" if item.covered_by_default_hostlist else "hostlist=no"
            methods = ",".join(item.methods) or "?"
            statuses = ",".join(f"{status}:{count}" for status, count in sorted(item.statuses.items())) or "?"
            ws = f"; websocket={item.websocket_count}" if item.websocket_count else ""
            l7 = ",".join(item.l7_hints) or "?"
            transport = ",".join(item.transport_hints) or "?"
            failures = f"; errors={item.error_count}; failed-status={item.failed_status_count}" if item.error_count or item.failed_status_count else ""
            lines.append(
                f"  - {item.host} [{item.category}; {preset}; {hostlist}; methods={methods}; "
                f"status={statuses}; L7={l7}; transport={transport}{ws}{failures}]"
            )
            for pattern in item.path_patterns[:4]:
                lines.append(f"      path: {pattern}")
            if len(item.path_patterns) > 4:
                lines.append(f"      path: ... {len(item.path_patterns) - 4} more")
            for note in item.notes:
                lines.append(f"      note: {note}")
        missing = self.missing_from_default_hostlist()
        lines.append("")
        lines.append("Discovery-only hostlist candidates:")
        if missing:
            for item in missing:
                lines.append(f"  - {item.host} [{item.category}]")
        else:
            lines.append("  - none; observed Discord-related hosts are already suffix-covered by default.hosts")
        optional = self.optional_discovery_hosts()
        lines.append("")
        lines.append("Interpretation:")
        lines.append("  - HAR confirms web/API/gateway/CDN surface after the browser already reached HTTP/WebSocket level.")
        lines.append("  - It does not prove an nfqws2 desync strategy for the earlier TCP/TLS ClientHello blocker.")
        if optional:
            lines.append("  - Optional hosts above can improve discovery reports, especially attachment upload/status support, but should not be promoted into the core Discord runtime chain without owner review.")
        if self.server_ip_unique_count:
            lines.append("  - HAR serverIPAddress values are counted but not stored; proxy/VPN captures can make those IPs misleading.")
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"  - {item}" for item in self.warnings)
        return "\n".join(lines)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _discovery_dir(root: Path | None = None) -> Path:
    layout = discover_layout(root)
    return layout.root / DISCOVERY_DIR


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
    if _HEX_RE.fullmatch(stem) or _LONG_TOKEN_RE.fullmatch(stem):
        return "{token}" + suffix
    return value[:80]


def _path_pattern(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    parts = [_safe_segment(part) for part in path.split("/")]
    normalized = "/".join(parts) or "/"
    if len(normalized) > 180:
        return normalized[:177] + "..."
    return normalized


def _host_from_url(url: str) -> str:
    return (urlparse(url).hostname or "").strip().lower().rstrip(".")


def _is_suffix_covered(host: str, entries: tuple[str, ...]) -> bool:
    return any(host == item or host.endswith(f".{item}") for item in entries if item)


def _default_hostlist_entries(root: Path | None) -> tuple[str, ...]:
    layout = discover_layout(root)
    path = layout.profiles_dir / "hostlists" / "default.hosts"
    if not path.exists():
        return ()
    entries: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        token = service_target_host_token(line.split()[0])
        if token and token not in entries:
            entries.append(token)
    return tuple(entries)


def _category_for_host(host: str) -> str:
    if host in {"discord.com", "www.discord.com"}:
        return "app-api"
    if host == "gateway.discord.gg":
        return "gateway"
    if host in {"updates.discord.com", "stable.dl2.discordapp.net"}:
        return "updater"
    if host == "status.discord.com":
        return "status"
    if host.endswith("discord.media"):
        return "media-relay"
    if host in {"cdn.discordapp.com", "media.discordapp.net", "images-ext-1.discordapp.net", "images-ext-2.discordapp.net"}:
        return "cdn-media"
    if host.endswith(".discordapp.com") or host.endswith(".discordapp.net") or host.endswith(".discordcdn.com"):
        return "cdn-media"
    if "discord" in host and host.endswith("storage.googleapis.com"):
        return "attachment-upload"
    if "discord" in host:
        return "external-discord-support"
    return "external-other"


def _host_note(host: str, category: str) -> tuple[str, ...]:
    if category == "attachment-upload":
        return ("pre-signed upload target; useful for attachment coverage reports, not a core login/gateway target",)
    if category == "media-relay":
        return ("dynamic discord.media subdomain; suffix coverage should be checked rather than adding one generated hostname",)
    if category == "status":
        return ("status API is diagnostic/support surface, not a launch requirement",)
    if category == "external-other":
        return ("non-Discord host retained only as aggregate category evidence",)
    return ()


def _error_category(raw_error: object) -> str | None:
    value = str(raw_error or "").strip().lower()
    if not value:
        return None
    if any(token in value for token in ("name not resolved", "dns", "resolve", "host not found")):
        return "dns"
    if any(token in value for token in ("timed out", "timeout", "deadline")):
        return "timeout"
    if any(token in value for token in ("ssl", "tls", "certificate", "handshake")):
        return "tls"
    if any(token in value for token in ("reset", "closed", "eof", "aborted")):
        return "reset-or-closed"
    if any(token in value for token in ("refused", "unreachable")):
        return "refused-or-unreachable"
    if any(token in value for token in ("blocked", "denied", "access")):
        return "blocked-or-denied"
    return "other"


def _entry_http_version(entry: dict[str, Any]) -> str:
    request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    value = str(response.get("httpVersion") or request.get("httpVersion") or "").strip().lower()
    return value[:24]


def _entry_evidence(entry: dict[str, Any], url: str, websocket: bool) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    http_version = _entry_http_version(entry)
    version_token = http_version.replace("/", "").replace("-", "")
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
    return scheme, http_version, tuple(sorted(l7)), tuple(sorted(transports))


def _entry_is_websocket(entry: dict[str, Any]) -> bool:
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
    status = int(response.get("status", 0) or 0)
    url = str(request.get("url", ""))
    return bool(entry.get("_webSocketMessages")) or status == 101 or url.lower().startswith("wss://")


def _header_names(entry: dict[str, Any]) -> tuple[str, ...]:
    names: list[str] = []
    for section_name in ("request", "response"):
        section = entry.get(section_name) if isinstance(entry.get(section_name), dict) else {}
        for header in section.get("headers", []) if isinstance(section.get("headers", []), list) else []:
            if not isinstance(header, dict):
                continue
            name = str(header.get("name", "")).strip().lower()
            if name:
                names.append(name)
    return tuple(names)


def analyze_discord_har(path: str | Path, *, root: Path | None = None) -> DiscordHarSummary:
    source = Path(path).expanduser()
    data, read_warnings = _read_har_payload(source)
    log = data.get("log") if isinstance(data.get("log"), dict) else {}
    entries = log.get("entries", []) if isinstance(log.get("entries", []), list) else []
    default_entries = _default_hostlist_entries(root)
    preset_entries = tuple(service_target_host_token(item) for item in DISCORD_DESKTOP_TARGETS)
    host_acc: dict[str, dict[str, Any]] = {}
    sensitive_seen: set[str] = set()
    server_ips: set[str] = set()
    websocket_entries = 0
    discord_related_entries = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
        response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
        url = str(request.get("url", ""))
        host = _host_from_url(url)
        if not host:
            continue
        category = _category_for_host(host)
        if category != "external-other":
            discord_related_entries += 1
        method = str(request.get("method", "GET") or "GET").upper()[:12]
        status_value = int(response.get("status", 0) or 0)
        status = str(status_value)
        websocket = _entry_is_websocket(entry)
        scheme, http_version, l7_hints, transport_hints = _entry_evidence(entry, url, websocket)
        error_category = _error_category(entry.get("_error"))
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
                "http_versions": set(),
                "l7_hints": set(),
                "transport_hints": set(),
                "error_count": 0,
                "failed_status_count": 0,
                "error_categories": set(),
                "category": category,
            },
        )
        acc["request_count"] += 1
        acc["methods"].add(method)
        acc["statuses"][status] = acc["statuses"].get(status, 0) + 1
        pattern = _path_pattern(url)
        if pattern not in acc["path_patterns"] and len(acc["path_patterns"]) < MAX_PATH_EXAMPLES_PER_HOST:
            acc["path_patterns"].append(pattern)
        if websocket:
            acc["websocket_count"] += 1
        if scheme:
            acc["schemes"].add(scheme)
        if http_version:
            acc["http_versions"].add(http_version)
        acc["l7_hints"].update(l7_hints)
        acc["transport_hints"].update(transport_hints)
        if error_category:
            acc["error_count"] += 1
            acc["error_categories"].add(error_category)
        if status_value == 0 or status_value >= 400:
            acc["failed_status_count"] += 1

    host_summaries: list[HarHostSummary] = []
    for host, acc in sorted(host_acc.items(), key=lambda item: (-int(item[1]["request_count"]), item[0])):
        category = str(acc["category"])
        host_summaries.append(
            HarHostSummary(
                host=host,
                category=category,
                request_count=int(acc["request_count"]),
                methods=tuple(sorted(acc["methods"])),
                statuses=dict(sorted(acc["statuses"].items())),
                path_patterns=tuple(str(item) for item in acc["path_patterns"]),
                websocket_count=int(acc["websocket_count"]),
                schemes=tuple(sorted(acc["schemes"])),
                http_versions=tuple(sorted(acc["http_versions"])),
                l7_hints=tuple(sorted(acc["l7_hints"])),
                transport_hints=tuple(sorted(acc["transport_hints"])),
                error_count=int(acc["error_count"]),
                failed_status_count=int(acc["failed_status_count"]),
                error_categories=tuple(sorted(acc["error_categories"])),
                covered_by_discord_preset=_is_suffix_covered(host, preset_entries),
                covered_by_default_hostlist=_is_suffix_covered(host, default_entries),
                notes=_host_note(host, category),
            )
        )

    return DiscordHarSummary(
        created_at=_now(),
        source_name=source.name,
        har_entry_count=len(entries),
        discord_related_entry_count=discord_related_entries,
        websocket_entry_count=websocket_entries,
        unique_host_count=len(host_summaries),
        server_ip_unique_count=len(server_ips),
        sensitive_header_names=tuple(sorted(sensitive_seen)),
        host_summaries=tuple(host_summaries),
        warnings=tuple(read_warnings),
    )


def write_discord_har_summary(path: str | Path, *, root: Path | None = None) -> DiscordHarSummary:
    summary = analyze_discord_har(path, root=root)
    out_dir = _discovery_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{DISCORD_HAR_SUMMARY_PREFIX}{summary.created_at.replace(':', '').replace('-', '')}.json"
    out_path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return DiscordHarSummary(
        created_at=summary.created_at,
        source_name=summary.source_name,
        har_entry_count=summary.har_entry_count,
        discord_related_entry_count=summary.discord_related_entry_count,
        websocket_entry_count=summary.websocket_entry_count,
        unique_host_count=summary.unique_host_count,
        server_ip_unique_count=summary.server_ip_unique_count,
        sensitive_header_names=summary.sensitive_header_names,
        host_summaries=summary.host_summaries,
        warnings=summary.warnings,
        output_path=out_path,
    )


def _summary_from_payload(path: Path, data: dict[str, Any]) -> DiscordHarSummary:
    counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
    hosts = []
    for item in data.get("hosts", []) if isinstance(data.get("hosts", []), list) else []:
        if not isinstance(item, dict):
            continue
        hosts.append(
            HarHostSummary(
                host=str(item.get("host", "")),
                category=str(item.get("category", "")),
                request_count=int(item.get("requestCount", 0) or 0),
                methods=tuple(str(value) for value in item.get("methods", []) if str(value).strip()),
                statuses={str(key): int(value) for key, value in dict(item.get("statuses", {})).items()},
                path_patterns=tuple(str(value) for value in item.get("pathPatterns", []) if str(value).strip()),
                websocket_count=int(item.get("webSocketCount", 0) or 0),
                schemes=tuple(str(value) for value in item.get("schemes", []) if str(value).strip()),
                http_versions=tuple(str(value) for value in item.get("httpVersions", []) if str(value).strip()),
                l7_hints=tuple(str(value) for value in item.get("l7Hints", []) if str(value).strip()),
                transport_hints=tuple(str(value) for value in item.get("transportHints", []) if str(value).strip()),
                error_count=int(item.get("errorCount", 0) or 0),
                failed_status_count=int(item.get("failedStatusCount", 0) or 0),
                error_categories=tuple(str(value) for value in item.get("errorCategories", []) if str(value).strip()),
                covered_by_discord_preset=bool(item.get("coveredByDiscordPreset", False)),
                covered_by_default_hostlist=bool(item.get("coveredByDefaultHostlist", False)),
                notes=tuple(str(value) for value in item.get("notes", []) if str(value).strip()),
            )
        )
    return DiscordHarSummary(
        created_at=str(data.get("createdAt", "unknown")),
        source_name=str(data.get("sourceName", "unknown")),
        har_entry_count=int(counts.get("harEntries", 0) or 0),
        discord_related_entry_count=int(counts.get("discordRelatedEntries", 0) or 0),
        websocket_entry_count=int(counts.get("webSocketEntries", 0) or 0),
        unique_host_count=int(counts.get("uniqueHosts", len(hosts)) or len(hosts)),
        server_ip_unique_count=int(counts.get("uniqueServerIps", 0) or 0),
        sensitive_header_names=tuple(str(value) for value in data.get("sensitiveHeaderNamesSeen", []) if str(value).strip()),
        host_summaries=tuple(hosts),
        warnings=tuple(str(value) for value in data.get("warnings", []) if str(value).strip()),
        output_path=path,
    )


def latest_discord_har_summary(root: Path | None = None) -> DiscordHarSummary | None:
    out_dir = _discovery_dir(root)
    files = sorted(out_dir.glob(f"{DISCORD_HAR_SUMMARY_PREFIX}*.json"))
    if not files:
        return None
    path = files[-1]
    return _summary_from_payload(path, json.loads(path.read_text(encoding="utf-8")))


def discord_har_plan_to_text() -> str:
    return "\n".join(
        [
            "Discord HAR discovery plan",
            "scope: sanitize a browser HAR into host/path/status coverage evidence",
            "executes now: no",
            "requires sudo: no",
            "mutates firewall/services: no",
            "stores credentials: no",
            "captures payloads: no; the analyzer drops headers values, cookies, query strings, bodies and WebSocket payloads",
            "use when: web Discord works through a browser/proxy and you want to compare observed hosts with z2guiflin service coverage",
            "do not use for: proving a TCP/TLS desync strategy; HAR starts after the browser has already reached HTTP/WebSocket level",
            "",
            "Owner loop:",
            "  1. Export a HAR from the browser only on your own account/test account.",
            "  2. Keep the raw HAR private; it can contain Authorization, cookies and x-super-properties.",
            "  3. Run: PYTHONPATH=gui python -m zap2_gui.app --discord-har-analyze /path/to/discord.har-or.zip",
            "  4. Share only the saved sanitized summary if needed.",
            "  5. Treat missing hosts as discovery/report candidates first, not as runtime strategy changes.",
        ]
    )


def discord_har_analyze_to_text(path: str, *, root: Path | None = None) -> str:
    return write_discord_har_summary(path, root=root).to_text()


def discord_har_report_to_text(*, root: Path | None = None) -> str:
    summary = latest_discord_har_summary(root)
    if summary is None:
        return "\n".join(
            [
                "Discord HAR discovery summary",
                "status: no saved HAR summaries",
                f"expected dir: {_discovery_dir(root)}",
                "next: PYTHONPATH=gui python -m zap2_gui.app --discord-har-analyze /path/to/discord.har-or.zip",
            ]
        )
    return summary.to_text()
