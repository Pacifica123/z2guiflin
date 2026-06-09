"""Read-only Discord DNS edge diagnostics.

Stage 7i uses the Windows GUI DNS idea as a diagnostic rather than a system
mutation: compare current system DNS with a small set of public resolver
families, then test whether any returned IPv4 edge can complete TCP/443.  This
helps decide whether changing DNS/hosts can plausibly help a Discord desktop
updater stuck in SYN-SENT, or whether the blocker is broader than DNS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
from typing import Iterable

from ..project_paths import discover_layout

DNS_EDGE_DIR = ".zap2/discord-discovery"
DEFAULT_DNS_EDGE_HOSTS = (
    "updates.discord.com",
    "discord.com",
    "cdn.discordapp.com",
    "gateway.discord.gg",
    "discord.gg",
)

# The names/servers mirror the Windows GUI DNS provider concept, but this
# Linux stage is intentionally read-only and diagnostic-only.
DNS_EDGE_RESOLVERS: dict[str, tuple[str, ...]] = {
    "system": (),
    "cloudflare": ("1.1.1.1", "1.0.0.1"),
    "google": ("8.8.8.8", "8.8.4.4"),
    "quad9": ("9.9.9.9", "149.112.112.112"),
    "adguard": ("94.140.14.14", "94.140.15.15"),
    "opendns": ("208.67.222.222", "208.67.220.220"),
}
DEFAULT_DNS_EDGE_RESOLVERS = tuple(DNS_EDGE_RESOLVERS)
_ADDRESS_RE = re.compile(r"^(?P<ip>(?:\d{1,3}\.){3}\d{1,3})$")
_GETENT_ADDRESS_RE = re.compile(r"^(?P<ip>(?:\d{1,3}\.){3}\d{1,3})\s+")
_NSLOOKUP_ADDRESS_RE = re.compile(r"Address(?:\s+\d+)?:\s*(?P<ip>(?:\d{1,3}\.){3}\d{1,3})")


@dataclass(frozen=True)
class DnsEdgeResolution:
    """A resolver result for one host."""

    host: str
    resolver: str
    server: str = ""
    addresses: tuple[str, ...] = ()
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "resolver": self.resolver,
            "server": self.server,
            "addresses": list(self.addresses),
            "error": self.error,
        }


@dataclass(frozen=True)
class DnsEdgeProbe:
    """TCP/443 connectivity probe for one IP returned by DNS."""

    host: str
    resolver: str
    server: str
    ip: str
    port: int = 443
    ok: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "resolver": self.resolver,
            "server": self.server,
            "ip": self.ip,
            "port": self.port,
            "ok": self.ok,
            "error": self.error,
        }


@dataclass(frozen=True)
class DnsEdgeDiagnosis:
    """Aggregated resolver/edge report."""

    created_at: str
    hosts: tuple[str, ...]
    resolvers: tuple[str, ...]
    timeout_seconds: float
    resolutions: tuple[DnsEdgeResolution, ...] = field(default_factory=tuple)
    probes: tuple[DnsEdgeProbe, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    output_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "createdAt": self.created_at,
            "hosts": list(self.hosts),
            "resolvers": list(self.resolvers),
            "timeoutSeconds": self.timeout_seconds,
            "warnings": list(self.warnings),
            "resolutions": [item.to_dict() for item in self.resolutions],
            "probes": [item.to_dict() for item in self.probes],
        }

    def host_addresses(self, host: str) -> tuple[str, ...]:
        values: list[str] = []
        for item in self.resolutions:
            if item.host != host:
                continue
            for address in item.addresses:
                if address not in values:
                    values.append(address)
        return tuple(values)

    def host_working_edges(self, host: str) -> tuple[DnsEdgeProbe, ...]:
        return tuple(item for item in self.probes if item.host == host and item.ok)

    def to_text(self) -> str:
        lines = [
            "Discord DNS edge diagnosis",
            f"created at: {self.created_at}",
            "executes now: yes, read-only DNS resolution and TCP connect probes" if self.probes or self.resolutions else "executes now: no",
            "requires sudo: no",
            "mutates DNS settings/hosts/firewall/services: no",
            "stores credentials: no",
        ]
        if self.output_path is not None:
            lines.append(f"snapshot: {self.output_path}")
        lines.extend(
            [
                "",
                "Why DNS is being checked:",
                "  - Windows GUI has DNS tooling, but DNS only helps if another resolver returns a different reachable edge IP.",
                "  - If every resolver returns only TCP-timeout edges, the Discord blocker is pre-TLS/IP-route level, not a resolver-only problem.",
                "",
                f"timeout per edge: {self.timeout_seconds:g}s",
                "resolvers: " + ", ".join(self.resolvers),
                "hosts:",
            ]
        )
        for host in self.hosts:
            addresses = self.host_addresses(host)
            working = self.host_working_edges(host)
            address_text = ", ".join(addresses) if addresses else "no addresses"
            verdict = "dns-edge-can-help" if working else "no-working-edge-observed"
            lines.append(f"  - {host}: {verdict}; addresses={address_text}")
            if working:
                for item in working[:6]:
                    server = f" @{item.server}" if item.server else " system"
                    lines.append(f"      ok: {item.ip}:{item.port} via {item.resolver}{server}")
            else:
                errors = tuple(dict.fromkeys(item.error for item in self.probes if item.host == host and item.error))
                if errors:
                    lines.append("      probe errors: " + "; ".join(errors[:4]))
        lines.append("")
        lines.append("Resolver details:")
        for item in self.resolutions:
            server = f" @{item.server}" if item.server else " system"
            addresses = ", ".join(item.addresses) if item.addresses else "no addresses"
            suffix = f" error={item.error}" if item.error else ""
            lines.append(f"  - {item.host} via {item.resolver}{server}: {addresses}{suffix}")
        lines.append("")
        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"  - {item}" for item in self.warnings)
            lines.append("")
        any_working = any(item.ok for item in self.probes)
        lines.extend(
            [
                "Interpretation:",
                "  - connect-ok edges mean DNS/hosts steering may be worth an owner-confirmed experiment.",
                "  - all-timeout edges mean changing DNS alone is unlikely to fix the Discord updater spinner.",
                "  - SYN-SENT/timeout happens before TLS, so TLS ClientHello desync strategies are not exercised on those sockets.",
                "  - This command does not change DNS; it only decides whether the Windows-GUI DNS concept is relevant here.",
            ]
        )
        if not any_working:
            lines.append("verdict: no reachable Discord Cloudflare edge observed through tested DNS resolvers")
        else:
            lines.append("verdict: at least one reachable edge observed; DNS/hosts steering may be useful")
        return "\n".join(lines)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _diagnostics_dir(root: Path | None = None) -> Path:
    return discover_layout(root).root / DNS_EDGE_DIR


def _run_text(argv: list[str], *, timeout: float = 4.0) -> str:
    try:
        completed = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: {exc}"
    return "\n".join(item for item in (completed.stdout, completed.stderr) if item)


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    for value in values:
        value = value.strip()
        if value and value not in out:
            out.append(value)
    return tuple(out)


def parse_dns_address_output(text: str) -> tuple[str, ...]:
    """Parse IPv4 addresses from getent/dig/nslookup-style output."""

    addresses: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("ERROR:"):
            continue
        exact = _ADDRESS_RE.match(line)
        if exact:
            addresses.append(exact.group("ip"))
            continue
        getent = _GETENT_ADDRESS_RE.match(line)
        if getent:
            addresses.append(getent.group("ip"))
            continue
        nslookup = _NSLOOKUP_ADDRESS_RE.search(line)
        if nslookup:
            addresses.append(nslookup.group("ip"))
    return _dedupe(addresses)


def _resolve_system(host: str) -> DnsEdgeResolution:
    addresses: tuple[str, ...] = ()
    error = ""
    if shutil.which("getent") is not None:
        output = _run_text(["getent", "ahostsv4", host], timeout=3.0)
        addresses = parse_dns_address_output(output)
        if output.startswith("ERROR:") and not addresses:
            error = output
    if not addresses:
        try:
            infos = socket.getaddrinfo(host, 443, family=socket.AF_INET, type=socket.SOCK_STREAM)
            addresses = _dedupe(str(info[4][0]) for info in infos)
        except OSError as exc:
            if not error:
                error = str(exc)
    return DnsEdgeResolution(host=host, resolver="system", addresses=addresses, error=error)


def _resolve_with_server(host: str, resolver: str, server: str) -> DnsEdgeResolution:
    if shutil.which("dig") is not None:
        output = _run_text(["dig", f"@{server}", host, "A", "+short", "+time=3", "+tries=1"], timeout=4.0)
        addresses = parse_dns_address_output(output)
        error = "" if addresses else output.strip()
        return DnsEdgeResolution(host=host, resolver=resolver, server=server, addresses=addresses, error=error)
    if shutil.which("nslookup") is not None:
        output = _run_text(["nslookup", "-type=A", host, server], timeout=4.0)
        addresses = parse_dns_address_output(output)
        error = "" if addresses else output.strip()
        return DnsEdgeResolution(host=host, resolver=resolver, server=server, addresses=addresses, error=error)
    return DnsEdgeResolution(host=host, resolver=resolver, server=server, error="dig/nslookup not found; cannot query this resolver directly")


def resolve_dns_edges(hosts: tuple[str, ...], resolvers: tuple[str, ...]) -> tuple[DnsEdgeResolution, ...]:
    results: list[DnsEdgeResolution] = []
    for host in hosts:
        for resolver in resolvers:
            servers = DNS_EDGE_RESOLVERS.get(resolver)
            if servers is None:
                results.append(DnsEdgeResolution(host=host, resolver=resolver, error="unknown resolver id"))
                continue
            if resolver == "system":
                results.append(_resolve_system(host))
                continue
            for server in servers[:1]:
                results.append(_resolve_with_server(host, resolver, server))
    return tuple(results)


def probe_tcp_edge(host: str, resolver: str, server: str, ip: str, *, port: int = 443, timeout: float = 3.0) -> DnsEdgeProbe:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return DnsEdgeProbe(host=host, resolver=resolver, server=server, ip=ip, port=port, ok=True)
    except OSError as exc:
        return DnsEdgeProbe(host=host, resolver=resolver, server=server, ip=ip, port=port, ok=False, error=str(exc))


def _resolvers_from_csv(value: str | tuple[str, ...] | None) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_DNS_EDGE_RESOLVERS
    if isinstance(value, str):
        raw = tuple(item.strip() for item in value.split(",") if item.strip())
    else:
        raw = tuple(str(item).strip() for item in value if str(item).strip())
    return raw or DEFAULT_DNS_EDGE_RESOLVERS


def _hosts_from_csv(value: str | tuple[str, ...] | None) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_DNS_EDGE_HOSTS
    if isinstance(value, str):
        raw = tuple(item.strip() for item in value.replace(",", " ").split() if item.strip())
    else:
        raw = tuple(str(item).strip() for item in value if str(item).strip())
    return raw or DEFAULT_DNS_EDGE_HOSTS


def run_discord_dns_edge_diagnosis(
    *,
    root: Path | None = None,
    hosts: tuple[str, ...] | str | None = None,
    resolvers: tuple[str, ...] | str | None = None,
    timeout_seconds: float = 3.0,
) -> DnsEdgeDiagnosis:
    """Resolve Discord hosts through several resolvers and TCP-probe returned edges."""

    selected_hosts = _hosts_from_csv(hosts)
    selected_resolvers = _resolvers_from_csv(resolvers)
    timeout_seconds = max(0.5, min(float(timeout_seconds), 15.0))
    warnings: list[str] = []
    if shutil.which("dig") is None and shutil.which("nslookup") is None:
        warnings.append("dig/nslookup were not found; only the system resolver can be queried directly")
    resolutions = resolve_dns_edges(selected_hosts, selected_resolvers)
    seen_probes: set[tuple[str, str, str, str]] = set()
    probes: list[DnsEdgeProbe] = []
    for item in resolutions:
        for ip in item.addresses:
            key = (item.host, item.resolver, item.server, ip)
            if key in seen_probes:
                continue
            seen_probes.add(key)
            probes.append(
                probe_tcp_edge(item.host, item.resolver, item.server, ip, timeout=timeout_seconds)
            )
    diagnosis = DnsEdgeDiagnosis(
        created_at=_now(),
        hosts=selected_hosts,
        resolvers=selected_resolvers,
        timeout_seconds=timeout_seconds,
        resolutions=resolutions,
        probes=tuple(probes),
        warnings=tuple(warnings),
    )
    out_dir = _diagnostics_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"dns-edge-diagnosis-{diagnosis.created_at.replace(':', '').replace('-', '')}.json"
    out_path.write_text(json.dumps(diagnosis.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return DnsEdgeDiagnosis(
        created_at=diagnosis.created_at,
        hosts=diagnosis.hosts,
        resolvers=diagnosis.resolvers,
        timeout_seconds=diagnosis.timeout_seconds,
        resolutions=diagnosis.resolutions,
        probes=diagnosis.probes,
        warnings=diagnosis.warnings,
        output_path=out_path,
    )


def discord_dns_edge_plan_to_text(*, hosts: str | tuple[str, ...] | None = None, resolvers: str | tuple[str, ...] | None = None, timeout_seconds: float = 3.0) -> str:
    selected_hosts = _hosts_from_csv(hosts)
    selected_resolvers = _resolvers_from_csv(resolvers)
    return "\n".join(
        [
            "Discord DNS edge diagnosis plan",
            "scope: test whether changing DNS could route Discord to a reachable TCP/443 edge",
            "executes now: no",
            "requires sudo: no",
            "mutates DNS settings/hosts/firewall/services: no",
            "stores credentials: no",
            "origin: Windows GUI DNS concept, adapted as Linux read-only diagnostics first",
            "",
            "Resolver idea:",
            "  - DNS can help only when another resolver returns different IPs and at least one of those IPs connects on TCP/443.",
            "  - DNS cannot help by itself when every returned edge times out before TLS.",
            "",
            "Hosts: " + ", ".join(selected_hosts),
            "Resolvers: " + ", ".join(selected_resolvers),
            f"TCP timeout per edge: {max(0.5, min(float(timeout_seconds), 15.0)):g}s",
            "",
            "Owner command:",
            "  PYTHONPATH=gui python -m zap2_gui.app --discord-dns-edge-check",
            "",
            "Possible outcomes:",
            "  - at least one connect-ok edge: DNS/hosts steering may be worth an owner-confirmed experiment.",
            "  - all edges timeout: the blocker is broader than DNS poisoning and ordinary TLS Blockcheck strategies will not be exercised yet.",
        ]
    )


def discord_dns_edge_check_to_text(
    *,
    root: Path | None = None,
    hosts: str | tuple[str, ...] | None = None,
    resolvers: str | tuple[str, ...] | None = None,
    timeout_seconds: float = 3.0,
) -> str:
    return run_discord_dns_edge_diagnosis(
        root=root,
        hosts=hosts,
        resolvers=resolvers,
        timeout_seconds=timeout_seconds,
    ).to_text()
