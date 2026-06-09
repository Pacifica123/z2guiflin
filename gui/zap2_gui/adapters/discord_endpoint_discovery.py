"""Read-only Discord desktop endpoint discovery helpers.

This module does not launch Discord, does not request sudo and does not mutate
firewall/services. It gives the owner a small evidence tool for the current
v0.4-alpha dead end: before guessing updater domains, watch which TCP/UDP
endpoints the locally running Discord process actually opens while the splash
screen says "Checking for updates".
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time

from ..project_paths import discover_layout

DISCOVERY_DIR = ".zap2/discord-discovery"
DEFAULT_DISCOVERY_SECONDS = 90
DEFAULT_DISCOVERY_DNS_TARGETS = (
    "updates.discord.com",
    "stable.dl2.discordapp.net",
    "discord.com",
    "gateway.discord.gg",
    "cdn.discordapp.com",
    "media.discordapp.net",
    "discord.media",
    "discordapp.net",
    "discord.gg",
)
_PID_RE = re.compile(r"pid=(?P<pid>\d+)")
_PROCESS_NAME_RE = re.compile(r'"(?P<name>[^"]+)"')
_TIMER_RE = re.compile(r"timer:\((?P<timer>[^)]*)\)")
_STATE_TOKENS = {
    "ESTAB",
    "SYN-SENT",
    "SYN-RECV",
    "FIN-WAIT-1",
    "FIN-WAIT-2",
    "TIME-WAIT",
    "CLOSE-WAIT",
    "LAST-ACK",
    "LISTEN",
    "CLOSING",
    "CLOSED",
    "UNCONN",
    "CONNECTED",
}


@dataclass(frozen=True)
class DnsHostResolution:
    """Best-effort DNS resolution for a Discord-related host during discovery."""

    hostname: str
    addresses: tuple[str, ...] = ()
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"hostname": self.hostname, "addresses": list(self.addresses), "error": self.error}


@dataclass(frozen=True)
class DiscordEndpointObservation:
    """One socket observation sampled from ss(8)."""

    proto: str
    local: str
    peer: str
    state: str = ""
    timer: str = ""
    process: str = ""
    pid: str = ""
    process_name: str = ""
    sightings: int = 1
    matched_hosts: tuple[str, ...] = ()

    @property
    def peer_host(self) -> str:
        value = self.peer.rsplit(":", 1)[0]
        if value.startswith("[") and "]" in value:
            value = value[1:].split("]", 1)[0]
        return value

    @property
    def peer_port(self) -> str:
        if self.peer.startswith("[") and "]:" in self.peer:
            return self.peer.rsplit(":", 1)[-1]
        if ":" in self.peer:
            return self.peer.rsplit(":", 1)[-1]
        return ""

    def key(self) -> tuple[str, str, str, str]:
        return (self.proto.lower(), self.peer_host, self.peer_port, self.pid)

    def to_dict(self) -> dict[str, object]:
        return {
            "proto": self.proto,
            "local": self.local,
            "peer": self.peer,
            "peerHost": self.peer_host,
            "peerPort": self.peer_port,
            "state": self.state,
            "timer": self.timer,
            "process": self.process,
            "pid": self.pid,
            "processName": self.process_name,
            "sightings": self.sightings,
            "matchedHosts": list(self.matched_hosts),
        }


@dataclass(frozen=True)
class DiscordEndpointSnapshot:
    """Aggregated read-only endpoint watch result."""

    created_at: str
    seconds: int
    samples: int
    observations: tuple[DiscordEndpointObservation, ...] = field(default_factory=tuple)
    process_lines: tuple[str, ...] = field(default_factory=tuple)
    dns_map: tuple[DnsHostResolution, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    output_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": 2,
            "createdAt": self.created_at,
            "seconds": self.seconds,
            "samples": self.samples,
            "processLines": list(self.process_lines),
            "dnsMap": [item.to_dict() for item in self.dns_map],
            "warnings": list(self.warnings),
            "observations": [item.to_dict() for item in self.observations],
        }

    def _syn_sent_observations(self) -> tuple[DiscordEndpointObservation, ...]:
        return tuple(
            item
            for item in self.observations
            if item.proto.lower() == "tcp" and item.state.upper() == "SYN-SENT"
        )

    def to_text(self) -> str:
        ports: dict[str, int] = {}
        proto_counts: dict[str, int] = {}
        states: dict[str, int] = {}
        for item in self.observations:
            ports[item.peer_port or "?"] = ports.get(item.peer_port or "?", 0) + max(item.sightings, 1)
            proto_counts[item.proto.lower()] = proto_counts.get(item.proto.lower(), 0) + max(item.sightings, 1)
            if item.state:
                states[item.state] = states.get(item.state, 0) + max(item.sightings, 1)
        syn_sent = self._syn_sent_observations()
        lines = [
            "Discord endpoint discovery snapshot",
            f"created at: {self.created_at}",
            f"duration: {self.seconds}s; samples: {self.samples}",
            "executes now: yes, read-only ss/pgrep/DNS sampling only" if self.samples else "executes now: no",
            "requires sudo: no",
            "mutates firewall/services: no",
            "stores credentials: no",
        ]
        if self.output_path is not None:
            lines.append(f"snapshot: {self.output_path}")
        lines.extend(["", "Observed Discord-like processes:"])
        if self.process_lines:
            lines.extend(f"  - {line}" for line in self.process_lines[:12])
        else:
            lines.append("  - none observed; start Discord while the watch is running")
        lines.append("")
        lines.append("DNS map:")
        if self.dns_map:
            for item in self.dns_map:
                suffix = f" error={item.error}" if item.error else ""
                addresses = ", ".join(item.addresses) if item.addresses else "no addresses"
                lines.append(f"  - {item.hostname}: {addresses}{suffix}")
        else:
            lines.append("  - unavailable")
        lines.append("")
        lines.append("Endpoint summary:")
        if not self.observations:
            lines.append("  - no sockets observed for process names containing discord/Discord")
        else:
            lines.append("  protocols: " + ", ".join(f"{key}={value}" for key, value in sorted(proto_counts.items())))
            lines.append("  ports: " + ", ".join(f"{key}={value}" for key, value in sorted(ports.items())))
            if states:
                lines.append("  states: " + ", ".join(f"{key}={value}" for key, value in sorted(states.items())))
            lines.append("  endpoints:")
            for item in self.observations[:80]:
                name = f" process={item.process_name or '?'} pid={item.pid or '?'}" if item.process or item.pid else ""
                state = f" state={item.state}" if item.state else ""
                timer = f" timer={item.timer}" if item.timer else ""
                hosts = f" hosts={','.join(item.matched_hosts)}" if item.matched_hosts else ""
                count = f" sightings={item.sightings}" if item.sightings > 1 else ""
                lines.append(f"    - {item.proto.upper()} {item.peer_host}:{item.peer_port or '?'}{state}{timer}{count}{hosts}{name}")
            if len(self.observations) > 80:
                lines.append(f"    - ... {len(self.observations) - 80} more")
        lines.append("")
        lines.append("Updater focus:")
        if syn_sent:
            lines.append("  - TCP SYN-SENT was observed for Discord. The updater is blocked before a TLS/HTTP request can complete on that socket.")
            for item in syn_sent[:8]:
                host_label = ",".join(item.matched_hosts) if item.matched_hosts else "unknown host"
                lines.append(f"  - {item.peer_host}:{item.peer_port or '?'} matched={host_label} timer={item.timer or '?'} sightings={item.sightings}")
            lines.append("  - This is a pre-TLS TCP connectivity blocker: first confirm which hostname/IP must be covered and whether another route/edge works.")
        else:
            lines.append("  - no TCP SYN-SENT sockets captured; if the spinner persists, inspect ESTAB sockets or use the netlog plan below.")
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"  - {item}" for item in self.warnings)
        lines.extend(
            [
                "",
                "Interpretation:",
                "  - This discovers where the local Discord process connects during the updater splash; it does not identify SNI/HTTP paths by itself.",
                "  - A TCP SYN-SENT endpoint means the connection is not reaching a completed TCP handshake yet; HTTP/TLS payload strategies are not exercised on that socket.",
                "  - UDP endpoints would be evidence that the current failure path touches a non-TCP layer; record them before changing the v0.4 non-voice scope.",
            ]
        )
        return "\n".join(lines)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _discovery_dir(root: Path | None = None) -> Path:
    layout = discover_layout(root)
    return layout.root / DISCOVERY_DIR


def _run_text(argv: list[str], *, timeout: float = 3.0) -> str:
    try:
        completed = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return "\n".join(item for item in (completed.stdout, completed.stderr) if item)


def _parse_process_lines(text: str) -> tuple[str, ...]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if "discord" in lowered:
            lines.append(line)
    return tuple(dict.fromkeys(lines))


def _split_process_and_timer(tail: str) -> tuple[str, str]:
    timer_match = _TIMER_RE.search(tail)
    timer = timer_match.group("timer") if timer_match else ""
    process = tail
    if "timer:(" in process:
        process = process.split("timer:(", 1)[0].strip()
    return process.strip(), timer


def _parse_ss_output(text: str, *, default_proto: str = "") -> tuple[DiscordEndpointObservation, ...]:
    observations: list[DiscordEndpointObservation] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if "discord" not in lowered:
            continue
        parts = line.split(None, 6)
        if len(parts) < 5:
            continue
        proto = default_proto.lower()
        state = ""
        local = ""
        peer = ""
        tail = ""
        if parts[0].lower() in {"tcp", "udp"} and len(parts) >= 6:
            proto = parts[0].lower()
            state = parts[1]
            local = parts[4]
            peer = parts[5]
            tail = parts[6].strip() if len(parts) > 6 else ""
        elif default_proto and parts[0].upper() in _STATE_TOKENS and len(parts) >= 5:
            state = parts[0]
            local = parts[3]
            peer = parts[4]
            tail = " ".join(parts[5:]).strip() if len(parts) > 5 else ""
        else:
            continue
        if proto not in {"tcp", "udp"}:
            continue
        process, timer = _split_process_and_timer(tail)
        pid_match = _PID_RE.search(process)
        name_match = _PROCESS_NAME_RE.search(process)
        if peer in {"*:*", "0.0.0.0:*", "[::]:*"}:
            continue
        observations.append(
            DiscordEndpointObservation(
                proto=proto,
                local=local,
                peer=peer,
                state=state,
                timer=timer,
                process=process,
                pid=pid_match.group("pid") if pid_match else "",
                process_name=name_match.group("name") if name_match else "",
            )
        )
    return tuple(observations)


def _parse_getent_ahosts(text: str) -> tuple[str, ...]:
    addresses: list[str] = []
    for raw in text.splitlines():
        parts = raw.split()
        if not parts:
            continue
        value = parts[0]
        if value not in addresses:
            addresses.append(value)
    return tuple(addresses)


def resolve_discord_dns_map(targets: tuple[str, ...] = DEFAULT_DISCOVERY_DNS_TARGETS) -> tuple[DnsHostResolution, ...]:
    """Resolve known Discord targets so socket IPs can be matched to likely hostnames."""

    results: list[DnsHostResolution] = []
    for host in targets:
        addresses: tuple[str, ...] = ()
        error = ""
        if shutil.which("getent") is not None:
            addresses = _parse_getent_ahosts(_run_text(["getent", "ahosts", host], timeout=2.5))
        if not addresses:
            try:
                infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
                values: list[str] = []
                for info in infos:
                    address = str(info[4][0])
                    if address not in values:
                        values.append(address)
                addresses = tuple(values)
            except OSError as exc:
                error = str(exc)
        results.append(DnsHostResolution(hostname=host, addresses=addresses, error=error))
    return tuple(results)


def _hosts_for_ip(ip: str, dns_map: tuple[DnsHostResolution, ...]) -> tuple[str, ...]:
    return tuple(item.hostname for item in dns_map if ip in item.addresses)


def _attach_dns_matches(item: DiscordEndpointObservation, dns_map: tuple[DnsHostResolution, ...]) -> DiscordEndpointObservation:
    return replace(item, matched_hosts=_hosts_for_ip(item.peer_host, dns_map))


def _merge_observation(old: DiscordEndpointObservation, new: DiscordEndpointObservation) -> DiscordEndpointObservation:
    return replace(
        old,
        local=new.local or old.local,
        state=new.state or old.state,
        timer=new.timer or old.timer,
        process=new.process or old.process,
        process_name=new.process_name or old.process_name,
        sightings=old.sightings + 1,
        matched_hosts=new.matched_hosts or old.matched_hosts,
    )


def run_discord_endpoint_watch(*, root: Path | None = None, seconds: int = DEFAULT_DISCOVERY_SECONDS, interval: float = 1.0) -> DiscordEndpointSnapshot:
    """Sample ss/pgrep output for a short owner-controlled window."""

    seconds = max(1, min(int(seconds), 600))
    warnings: list[str] = []
    if shutil.which("ss") is None:
        warnings.append("ss binary was not found; endpoint socket sampling is unavailable")
    if shutil.which("pgrep") is None:
        warnings.append("pgrep binary was not found; process listing is limited")
    dns_map = resolve_discord_dns_map()
    seen: dict[tuple[str, str, str, str], DiscordEndpointObservation] = {}
    process_lines: list[str] = []
    samples = 0
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        samples += 1
        if shutil.which("pgrep") is not None:
            process_lines.extend(_parse_process_lines(_run_text(["pgrep", "-af", "[Dd]iscord"], timeout=2.0)))
        if shutil.which("ss") is not None:
            raw_tcp = _run_text(["ss", "-H", "-tanop"], timeout=2.0)
            raw_udp = _run_text(["ss", "-H", "-uanop"], timeout=2.0)
            for item in (*_parse_ss_output(raw_tcp, default_proto="tcp"), *_parse_ss_output(raw_udp, default_proto="udp")):
                item = _attach_dns_matches(item, dns_map)
                key = item.key()
                seen[key] = _merge_observation(seen[key], item) if key in seen else item
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
    out_dir = _discovery_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = DiscordEndpointSnapshot(
        created_at=_now(),
        seconds=seconds,
        samples=samples,
        observations=tuple(seen.values()),
        process_lines=tuple(dict.fromkeys(process_lines)),
        dns_map=dns_map,
        warnings=tuple(warnings),
    )
    out_path = out_dir / f"endpoint-snapshot-{snapshot.created_at.replace(':', '').replace('-', '')}.json"
    out_path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return replace(snapshot, output_path=out_path)


def latest_discord_endpoint_snapshot(root: Path | None = None) -> DiscordEndpointSnapshot | None:
    out_dir = _discovery_dir(root)
    files = sorted(out_dir.glob("endpoint-snapshot-*.json"))
    if not files:
        return None
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    dns_map = tuple(
        DnsHostResolution(
            hostname=str(item.get("hostname", "")),
            addresses=tuple(str(value) for value in item.get("addresses", []) if str(value).strip()),
            error=str(item.get("error", "")),
        )
        for item in data.get("dnsMap", [])
        if isinstance(item, dict)
    )
    observations = tuple(
        DiscordEndpointObservation(
            proto=str(item.get("proto", "")),
            local=str(item.get("local", "")),
            peer=str(item.get("peer", "")),
            state=str(item.get("state", "")),
            timer=str(item.get("timer", "")),
            process=str(item.get("process", "")),
            pid=str(item.get("pid", "")),
            process_name=str(item.get("processName", "")),
            sightings=int(item.get("sightings", 1) or 1),
            matched_hosts=tuple(str(value) for value in item.get("matchedHosts", []) if str(value).strip()),
        )
        for item in data.get("observations", [])
        if isinstance(item, dict)
    )
    return DiscordEndpointSnapshot(
        created_at=str(data.get("createdAt", "unknown")),
        seconds=int(data.get("seconds", 0) or 0),
        samples=int(data.get("samples", 0) or 0),
        observations=observations,
        process_lines=tuple(str(item) for item in data.get("processLines", []) if str(item).strip()),
        dns_map=dns_map,
        warnings=tuple(str(item) for item in data.get("warnings", []) if str(item).strip()),
        output_path=files[-1],
    )


def discord_endpoint_discovery_plan_to_text(*, seconds: int = DEFAULT_DISCOVERY_SECONDS) -> str:
    seconds = max(1, min(int(seconds), 600))
    return "\n".join(
        [
            "Discord updater endpoint discovery plan",
            "scope: observe local Discord desktop sockets during the Checking for updates splash",
            "executes now: no",
            "requires sudo: no",
            "mutates firewall/services: no",
            "stores credentials: no",
            "captures payloads: no; ss/pgrep/DNS metadata only",
            "captures socket state: yes, TCP SYN-SENT/ESTAB/timers when ss exposes them",
            "matches endpoint IPs to known Discord hostnames: best-effort getent/socket DNS map",
            "",
            "Why this exists:",
            "  - Blockcheck guessed updater targets, but the splash may use another endpoint, port or even UDP path.",
            "  - Before adding more Discord domains, capture what the local process actually opens.",
            "",
            "Owner loop:",
            "  1. Stop Default workflow/VPN/other bypasses so observations are not mixed.",
            "  2. Fully close Discord.",
            f"  3. Run: PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-watch --discord-endpoint-seconds {seconds}",
            "  4. During the watch window, start Discord and leave it on Checking for updates.",
            "  5. Run: PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-report",
            "  6. If the report shows SYN-SENT, treat the blocker as pre-TLS TCP connectivity before running more curl/TLS tournaments.",
            "",
            "Notes:",
            "  - This does not discover SNI/HTTP URL paths; it discovers process-owned TCP/UDP endpoints and socket states.",
            "  - If no endpoints are observed, run the watch for longer or use a privileged external packet capture manually.",
        ]
    )


def discord_netlog_plan_to_text(*, output_path: str = "/tmp/discord-netlog.json") -> str:
    return "\n".join(
        [
            "Discord Chromium netlog owner plan",
            "scope: optional owner-run diagnostic for real Discord/Electron URL and socket evidence",
            "executes now: no",
            "requires sudo: no",
            "mutates firewall/services: no",
            "stores credentials: potentially yes if the owner chooses to run it; review/redact before sharing",
            "captures payloads: Chromium netlog metadata may include URLs, headers, cookies or token-like values",
            "",
            "Owner command to try manually:",
            f"  discord --log-net-log={output_path}",
            "",
            "Owner loop:",
            "  1. Close Discord completely.",
            "  2. Run the command above manually, leave the client on Checking for updates for 20-60 seconds, then close it.",
            "  3. Inspect the JSON locally for hostnames around updates/bootstrap/download requests.",
            "  4. Share only a redacted hostname/path summary, not the raw netlog, if credentials or tokens appear.",
            "",
            "Why this is separate from endpoint watch:",
            "  - ss shows IP/state/timer, but not SNI/URL/path.",
            "  - netlog may reveal the exact updater URL if TCP/TLS gets far enough, but it is privacy-sensitive.",
        ]
    )


def discord_endpoint_watch_to_text(*, root: Path | None = None, seconds: int = DEFAULT_DISCOVERY_SECONDS) -> str:
    return run_discord_endpoint_watch(root=root, seconds=seconds).to_text()


def discord_endpoint_report_to_text(*, root: Path | None = None) -> str:
    snapshot = latest_discord_endpoint_snapshot(root)
    if snapshot is None:
        return "\n".join(
            [
                "Discord endpoint discovery snapshot",
                "status: no saved snapshots",
                f"expected dir: {_discovery_dir(root)}",
                "next: PYTHONPATH=gui python -m zap2_gui.app --discord-endpoint-watch --discord-endpoint-seconds 90",
            ]
        )
    return snapshot.to_text()
