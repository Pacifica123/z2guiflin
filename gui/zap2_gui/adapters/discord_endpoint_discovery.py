"""Read-only Discord desktop endpoint discovery helpers.

This module does not launch Discord, does not request sudo and does not mutate
firewall/services. It gives the owner a small evidence tool for the current
v0.4-alpha dead end: before guessing updater domains, watch which TCP/UDP
endpoints the locally running Discord process actually opens while the splash
screen says "Checking for updates".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from ..project_paths import discover_layout

DISCOVERY_DIR = ".zap2/discord-discovery"
DEFAULT_DISCOVERY_SECONDS = 90
_SS_LINE_RE = re.compile(
    r"^(?P<proto>tcp|udp)\s+\S+\s+\S+\s+(?P<local>\S+)\s+(?P<peer>\S+)(?:\s+(?P<process>.*))?$",
    re.IGNORECASE,
)
_PID_RE = re.compile(r"pid=(?P<pid>\d+)")
_PROCESS_NAME_RE = re.compile(r'"(?P<name>[^"]+)"')


@dataclass(frozen=True)
class DiscordEndpointObservation:
    """One socket observation sampled from ss(8)."""

    proto: str
    local: str
    peer: str
    process: str = ""
    pid: str = ""
    process_name: str = ""

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

    def to_dict(self) -> dict[str, str]:
        return {
            "proto": self.proto,
            "local": self.local,
            "peer": self.peer,
            "peerHost": self.peer_host,
            "peerPort": self.peer_port,
            "process": self.process,
            "pid": self.pid,
            "processName": self.process_name,
        }


@dataclass(frozen=True)
class DiscordEndpointSnapshot:
    """Aggregated read-only endpoint watch result."""

    created_at: str
    seconds: int
    samples: int
    observations: tuple[DiscordEndpointObservation, ...] = field(default_factory=tuple)
    process_lines: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    output_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "createdAt": self.created_at,
            "seconds": self.seconds,
            "samples": self.samples,
            "processLines": list(self.process_lines),
            "warnings": list(self.warnings),
            "observations": [item.to_dict() for item in self.observations],
        }

    def to_text(self) -> str:
        ports: dict[str, int] = {}
        proto_counts: dict[str, int] = {}
        for item in self.observations:
            ports[item.peer_port or "?"] = ports.get(item.peer_port or "?", 0) + 1
            proto_counts[item.proto.lower()] = proto_counts.get(item.proto.lower(), 0) + 1
        lines = [
            "Discord endpoint discovery snapshot",
            f"created at: {self.created_at}",
            f"duration: {self.seconds}s; samples: {self.samples}",
            "executes now: yes, read-only ss/pgrep sampling only" if self.samples else "executes now: no",
            "requires sudo: no",
            "mutates firewall/services: no",
            "stores credentials: no",
        ]
        if self.output_path is not None:
            lines.append(f"snapshot: {self.output_path}")
        lines.extend([
            "",
            "Observed Discord-like processes:",
        ])
        if self.process_lines:
            lines.extend(f"  - {line}" for line in self.process_lines[:12])
        else:
            lines.append("  - none observed; start Discord while the watch is running")
        lines.append("")
        lines.append("Endpoint summary:")
        if not self.observations:
            lines.append("  - no sockets observed for process names containing discord/Discord")
        else:
            lines.append("  protocols: " + ", ".join(f"{key}={value}" for key, value in sorted(proto_counts.items())))
            lines.append("  ports: " + ", ".join(f"{key}={value}" for key, value in sorted(ports.items())))
            lines.append("  endpoints:")
            for item in self.observations[:80]:
                name = f" process={item.process_name or '?'} pid={item.pid or '?'}" if item.process or item.pid else ""
                lines.append(f"    - {item.proto.upper()} {item.peer_host}:{item.peer_port or '?'}{name}")
            if len(self.observations) > 80:
                lines.append(f"    - ... {len(self.observations) - 80} more")
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"  - {item}" for item in self.warnings)
        lines.extend(
            [
                "",
                "Interpretation:",
                "  - This discovers where the local Discord process connects during the updater splash; it does not identify SNI/HTTP paths by itself.",
                "  - TCP/443 endpoints point to updater/app/CDN candidates for Blockcheck/hostlist review.",
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


def _parse_ss_output(text: str) -> tuple[DiscordEndpointObservation, ...]:
    observations: list[DiscordEndpointObservation] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if "discord" not in lowered:
            continue
        parts = line.split(None, 6)
        if len(parts) < 6:
            continue
        proto = parts[0].lower()
        if proto not in {"tcp", "udp"}:
            continue
        # ss -H -tunp can print either:
        #   tcp ESTAB Recv-Q Send-Q Local Peer Process
        # or for some UDP rows:
        #   udp UNCONN Recv-Q Send-Q Local Peer Process
        local = parts[4]
        peer = parts[5]
        process = parts[6].strip() if len(parts) > 6 else ""
        pid_match = _PID_RE.search(process)
        name_match = _PROCESS_NAME_RE.search(process)
        if peer in {"*:*", "0.0.0.0:*", "[::]:*"}:
            continue
        observations.append(
            DiscordEndpointObservation(
                proto=proto,
                local=local,
                peer=peer,
                process=process,
                pid=pid_match.group("pid") if pid_match else "",
                process_name=name_match.group("name") if name_match else "",
            )
        )
    return tuple(observations)


def run_discord_endpoint_watch(*, root: Path | None = None, seconds: int = DEFAULT_DISCOVERY_SECONDS, interval: float = 1.0) -> DiscordEndpointSnapshot:
    """Sample ss/pgrep output for a short owner-controlled window."""

    seconds = max(1, min(int(seconds), 600))
    warnings: list[str] = []
    if shutil.which("ss") is None:
        warnings.append("ss binary was not found; endpoint socket sampling is unavailable")
    if shutil.which("pgrep") is None:
        warnings.append("pgrep binary was not found; process listing is limited")
    seen: dict[tuple[str, str, str, str], DiscordEndpointObservation] = {}
    process_lines: list[str] = []
    samples = 0
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        samples += 1
        if shutil.which("pgrep") is not None:
            process_lines.extend(_parse_process_lines(_run_text(["pgrep", "-af", "[Dd]iscord"], timeout=2.0)))
        if shutil.which("ss") is not None:
            # -t/-u TCP+UDP, -n numeric endpoints, -p process info when visible.
            for item in _parse_ss_output(_run_text(["ss", "-H", "-tunp"], timeout=2.0)):
                seen.setdefault(item.key(), item)
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
        warnings=tuple(warnings),
    )
    out_path = out_dir / f"endpoint-snapshot-{snapshot.created_at.replace(':', '').replace('-', '')}.json"
    out_path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return DiscordEndpointSnapshot(
        created_at=snapshot.created_at,
        seconds=snapshot.seconds,
        samples=snapshot.samples,
        observations=snapshot.observations,
        process_lines=snapshot.process_lines,
        warnings=snapshot.warnings,
        output_path=out_path,
    )


def latest_discord_endpoint_snapshot(root: Path | None = None) -> DiscordEndpointSnapshot | None:
    out_dir = _discovery_dir(root)
    files = sorted(out_dir.glob("endpoint-snapshot-*.json"))
    if not files:
        return None
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    observations = tuple(
        DiscordEndpointObservation(
            proto=str(item.get("proto", "")),
            local=str(item.get("local", "")),
            peer=str(item.get("peer", "")),
            process=str(item.get("process", "")),
            pid=str(item.get("pid", "")),
            process_name=str(item.get("processName", "")),
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
            "captures payloads: no; ss/pgrep metadata only",
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
            "  6. Feed observed TCP/UDP endpoints back into the Discord target registry/tournament plan.",
            "",
            "Notes:",
            "  - This does not discover SNI/HTTP URL paths; it discovers process-owned TCP/UDP endpoints.",
            "  - If no endpoints are observed, run the watch for longer or use a privileged external packet capture manually.",
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
