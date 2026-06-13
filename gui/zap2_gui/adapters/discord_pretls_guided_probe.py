"""Guided Discord pre-TLS probe harness.

Stage 7n/7n1 made the Discord SYN path observable in pieces: nft counters,
active strategy snapshots, and nfqws2 PID health.  Stage 7n2 turned those pieces
into one guided, owner-facing probe. Stage 7n3 adds endpoint/socket correlation
so a zero counter delta can be distinguished from a missed observation window.  The helper is deliberately diagnostic:
it reads runtime state, nft counters, process health, and log deltas; it never
starts Discord, never applies firewall rules, and never changes services.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .discord_endpoint_discovery import DiscordEndpointSnapshot, run_discord_endpoint_watch
from .runtime_nft_state import runtime_nft_state_snapshot
from .runtime_session import runtime_session_status
from .runtime_state import ensure_runtime_store
from ..project_paths import discover_layout

DEFAULT_GUIDED_PROBE_WAIT_SECONDS = 30
PRETLS_DIAGNOSTIC_STRATEGY_ID = "community-discord-pretls-diagnostic-pktdebug"

Emit = Callable[[str], None]
InputFunc = Callable[[str], str]
SleepFunc = Callable[[float], None]
NftRunner = Callable[[str], tuple[int, str, str]]
EndpointWatchRunner = Callable[[Path | None, int], DiscordEndpointSnapshot | None]


@dataclass(frozen=True)
class CounterValue:
    packets: int
    bytes: int

    def to_dict(self) -> dict[str, int]:
        return {"packets": self.packets, "bytes": self.bytes}


@dataclass(frozen=True)
class ProbeNftCounters:
    table_exists: bool
    read_ok: bool
    error: str
    tcp_out: CounterValue
    tcp_in_synack: CounterValue
    tcp_in_fin_rst: CounterValue
    raw_length: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "tableExists": self.table_exists,
            "readOk": self.read_ok,
            "error": self.error,
            "tcpOut": self.tcp_out.to_dict(),
            "tcpInSynAck": self.tcp_in_synack.to_dict(),
            "tcpInFinRst": self.tcp_in_fin_rst.to_dict(),
            "rawLength": self.raw_length,
        }


@dataclass(frozen=True)
class ProbeLogSizes:
    stdout_size: int | None
    stderr_size: int | None
    debug_size: int | None

    def to_dict(self) -> dict[str, int | None]:
        return {"stdout": self.stdout_size, "stderr": self.stderr_size, "debug": self.debug_size}




@dataclass(frozen=True)
class ProbeEndpointSummary:
    snapshot_path: Path | None
    samples: int
    observations: int
    process_lines: int
    states: dict[str, int]
    ports: dict[str, int]
    capture_matches: int
    capture_misses: int
    established: int
    syn_sent: int
    established_with_sendq: int
    primary_endpoint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshotPath": None if self.snapshot_path is None else str(self.snapshot_path),
            "samples": self.samples,
            "observations": self.observations,
            "processLines": self.process_lines,
            "states": dict(self.states),
            "ports": dict(self.ports),
            "captureMatches": self.capture_matches,
            "captureMisses": self.capture_misses,
            "established": self.established,
            "synSent": self.syn_sent,
            "establishedWithSendQ": self.established_with_sendq,
            "primaryEndpoint": self.primary_endpoint,
        }


@dataclass(frozen=True)
class ProbeDelta:
    before: int | None
    after: int | None
    delta: int | None

    def to_dict(self) -> dict[str, int | None]:
        return {"before": self.before, "after": self.after, "delta": self.delta}


@dataclass(frozen=True)
class DiscordPretlsGuidedProbeReport:
    profile_id: str
    selected_strategy_id: str
    active_strategy_id: str
    workflow_state: str
    session_state_before: str
    session_state_after: str
    session_pid_before: int | None
    session_pid_after: int | None
    nfqueue_snapshot: int
    nfqueue_session: int | None
    nfqueue_match: bool
    nft_table: str
    capture_policy_kind: str
    strategy_compatible: bool
    owner_rules_applied: bool
    counters_before: ProbeNftCounters | None
    counters_after: ProbeNftCounters | None
    counter_deltas: dict[str, ProbeDelta]
    log_sizes_before: ProbeLogSizes
    log_sizes_after: ProbeLogSizes
    log_deltas: dict[str, ProbeDelta]
    endpoint_summary: ProbeEndpointSummary | None
    args_path: Path | None
    args_hash: str | None
    stdout_path: Path | None
    stderr_path: Path | None
    debug_path: Path | None
    report_json_path: Path
    report_md_path: Path
    verdict: str
    meaning: str
    next_branch: str
    manual_action_mode: str
    waited_seconds: int
    created_at: str
    notes: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "stage": "v0.4-alpha_stage7n3",
            "kind": "discord-pretls-guided-probe-report",
            "createdAt": self.created_at,
            "profileId": self.profile_id,
            "selectedStrategyId": self.selected_strategy_id,
            "activeStrategyId": self.active_strategy_id,
            "strategyCompatible": self.strategy_compatible,
            "workflowState": self.workflow_state,
            "sessionStateBefore": self.session_state_before,
            "sessionStateAfter": self.session_state_after,
            "sessionPidBefore": self.session_pid_before,
            "sessionPidAfter": self.session_pid_after,
            "nfqueueSnapshot": self.nfqueue_snapshot,
            "nfqueueSession": self.nfqueue_session,
            "nfqueueMatch": self.nfqueue_match,
            "nftTable": self.nft_table,
            "capturePolicyKind": self.capture_policy_kind,
            "ownerRulesApplied": self.owner_rules_applied,
            "countersBefore": None if self.counters_before is None else self.counters_before.to_dict(),
            "countersAfter": None if self.counters_after is None else self.counters_after.to_dict(),
            "counterDeltas": {key: value.to_dict() for key, value in self.counter_deltas.items()},
            "logSizesBefore": self.log_sizes_before.to_dict(),
            "logSizesAfter": self.log_sizes_after.to_dict(),
            "logDeltas": {key: value.to_dict() for key, value in self.log_deltas.items()},
            "endpointSummary": None if self.endpoint_summary is None else self.endpoint_summary.to_dict(),
            "argsPath": None if self.args_path is None else str(self.args_path),
            "argsHash": self.args_hash,
            "stdoutPath": None if self.stdout_path is None else str(self.stdout_path),
            "stderrPath": None if self.stderr_path is None else str(self.stderr_path),
            "debugPath": None if self.debug_path is None else str(self.debug_path),
            "reportJsonPath": str(self.report_json_path),
            "reportMdPath": str(self.report_md_path),
            "verdict": self.verdict,
            "meaning": self.meaning,
            "nextBranch": self.next_branch,
            "manualActionMode": self.manual_action_mode,
            "waitedSeconds": self.waited_seconds,
            "notes": list(self.notes),
            "execution": {
                "readOnly": True,
                "executesDiscordNow": False,
                "appliesFirewallNow": False,
                "mutatesServicesNow": False,
                "writesReportFiles": True,
            },
        }

    def to_markdown(self) -> str:
        delta = self.counter_deltas
        logs = self.log_deltas
        lines = [
            "# Discord pre-TLS guided probe report",
            "",
            f"createdAt: `{self.created_at}`",
            f"profile: `{self.profile_id}`",
            f"selected strategy: `{self.selected_strategy_id}`",
            f"active/applied strategy: `{self.active_strategy_id}`",
            f"strategy compatible: `{'yes' if self.strategy_compatible else 'no'}`",
            f"workflow/owner rules applied: `{'yes' if self.owner_rules_applied else 'no'}`",
            f"nft table: `inet {self.nft_table}`",
            f"nfqueue snapshot/session: `{self.nfqueue_snapshot}` / `{self.nfqueue_session if self.nfqueue_session is not None else 'нет'}`",
            f"nfqueue match: `{'yes' if self.nfqueue_match else 'no'}`",
            "",
            "## Session",
            "",
            f"before: `{self.session_state_before}` pid `{self.session_pid_before if self.session_pid_before is not None else 'нет'}`",
            f"after: `{self.session_state_after}` pid `{self.session_pid_after if self.session_pid_after is not None else 'нет'}`",
            "",
            "## Counter deltas",
            "",
            "| rule | before packets | after packets | delta packets | before bytes | after bytes | delta bytes |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for key, label in (("tcpOut", "tcp-out"), ("tcpInSynAck", "tcp-in-synack"), ("tcpInFinRst", "tcp-in-fin-rst")):
            packets = delta.get(f"{key}Packets", ProbeDelta(None, None, None))
            bytes_ = delta.get(f"{key}Bytes", ProbeDelta(None, None, None))
            lines.append(
                f"| {label} | {packets.before if packets.before is not None else 'n/a'} | {packets.after if packets.after is not None else 'n/a'} | {packets.delta if packets.delta is not None else 'n/a'} | "
                f"{bytes_.before if bytes_.before is not None else 'n/a'} | {bytes_.after if bytes_.after is not None else 'n/a'} | {bytes_.delta if bytes_.delta is not None else 'n/a'} |"
            )
        lines.extend(
            [
                "",
                "## Log deltas",
                "",
                "| log | before bytes | after bytes | delta bytes |",
                "|---|---:|---:|---:|",
                f"| stdout | {_fmt_delta(logs.get('stdout'))} |",
                f"| stderr | {_fmt_delta(logs.get('stderr'))} |",
                f"| debug | {_fmt_delta(logs.get('debug'))} |",
                "",
                "## Endpoint correlation",
                "",
                *_endpoint_markdown_lines(self.endpoint_summary),
                "",
                "## Verdict",
                "",
                f"verdict: `{self.verdict}`",
                "",
                self.meaning,
                "",
                "next branch:",
                "",
                self.next_branch,
                "",
                "## Files",
                "",
                f"args: `{self.args_path if self.args_path is not None else 'нет'}`",
                f"args hash: `{self.args_hash if self.args_hash else 'нет'}`",
                f"stdout: `{self.stdout_path if self.stdout_path is not None else 'нет'}`",
                f"stderr: `{self.stderr_path if self.stderr_path is not None else 'нет'}`",
                f"debug: `{self.debug_path if self.debug_path is not None else 'нет'}`",
                "",
                "## Notes",
                "",
            ]
        )
        lines.extend(f"- {note}" for note in self.notes)
        return "\n".join(lines) + "\n"

    def to_text(self) -> str:
        delta = self.counter_deltas
        logs = self.log_deltas
        out_packets = delta.get("tcpOutPackets")
        synack_packets = delta.get("tcpInSynAckPackets")
        finrst_packets = delta.get("tcpInFinRstPackets")
        lines = [
            "Discord pre-TLS guided probe result",
            f"profile: {self.profile_id}",
            f"selected strategy: {self.selected_strategy_id}",
            f"active/applied strategy: {self.active_strategy_id}",
            f"strategy compatible: {'yes' if self.strategy_compatible else 'no'}",
            f"owner-rules applied: {'yes' if self.owner_rules_applied else 'no'}",
            f"nft table: inet {self.nft_table}",
            f"nfqueue snapshot/session: {self.nfqueue_snapshot} / {self.nfqueue_session if self.nfqueue_session is not None else 'нет'}",
            f"nfqueue match: {'yes' if self.nfqueue_match else 'no'}",
            f"nfqws2 before: {self.session_state_before}; pid: {self.session_pid_before if self.session_pid_before is not None else 'нет'}",
            f"nfqws2 after: {self.session_state_after}; pid: {self.session_pid_after if self.session_pid_after is not None else 'нет'}",
            "counter deltas:",
            f"  tcp-out packets: {_delta_text(out_packets)}",
            f"  tcp-in-synack packets: {_delta_text(synack_packets)}",
            f"  tcp-in-fin-rst packets: {_delta_text(finrst_packets)}",
            "log byte deltas:",
            f"  stdout: {_delta_text(logs.get('stdout'))}",
            f"  stderr: {_delta_text(logs.get('stderr'))}",
            f"  debug: {_delta_text(logs.get('debug'))}",
            *_endpoint_text_lines(self.endpoint_summary),
            f"verdict: {self.verdict}",
            f"meaning: {self.meaning}",
            f"next branch: {self.next_branch}",
            f"report json: {self.report_json_path}",
            f"report md: {self.report_md_path}",
            "read-only: yes",
            "executes Discord now: no",
            "applies firewall/services now: no",
            "writes report files: yes",
        ]
        return "\n".join(lines)


def _fmt_delta(value: ProbeDelta | None) -> str:
    if value is None:
        return "n/a | n/a | n/a"
    return f"{value.before if value.before is not None else 'n/a'} | {value.after if value.after is not None else 'n/a'} | {value.delta if value.delta is not None else 'n/a'}"


def _delta_text(value: ProbeDelta | None) -> str:
    if value is None or value.delta is None:
        return "n/a"
    return f"{value.before} -> {value.after} (delta {value.delta})"




def _to_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _summarize_endpoints(snapshot: DiscordEndpointSnapshot | None, *, capture_ips: tuple[str, ...], capture_ports: tuple[str, ...]) -> ProbeEndpointSummary | None:
    if snapshot is None:
        return None
    states: dict[str, int] = {}
    ports: dict[str, int] = {}
    capture_ip_set = set(capture_ips)
    capture_port_set = set(capture_ports)
    capture_matches = 0
    capture_misses = 0
    established = 0
    syn_sent = 0
    established_with_sendq = 0
    primary = "нет"
    best_sightings = -1
    for item in snapshot.observations:
        sightings = max(item.sightings, 1)
        state_key = item.state or "?"
        port_key = item.peer_port or "?"
        states[state_key] = states.get(state_key, 0) + sightings
        ports[port_key] = ports.get(port_key, 0) + sightings
        matches_capture = (not capture_ip_set or item.peer_host in capture_ip_set) and (not capture_port_set or item.peer_port in capture_port_set)
        if matches_capture:
            capture_matches += sightings
        else:
            capture_misses += sightings
        if item.state.upper() == "ESTAB":
            established += sightings
            if _to_int(item.send_q) > 0:
                established_with_sendq += sightings
        if item.state.upper() == "SYN-SENT":
            syn_sent += sightings
        if sightings > best_sightings:
            best_sightings = sightings
            queues = f" recvq={item.recv_q or '?'} sendq={item.send_q or '?'}" if item.recv_q or item.send_q else ""
            hosts = f" hosts={','.join(item.matched_hosts)}" if item.matched_hosts else ""
            primary = f"{item.proto.upper()} {item.peer_host}:{item.peer_port or '?'} state={item.state or '?'}{queues}{hosts} pid={item.pid or '?'}"
    return ProbeEndpointSummary(
        snapshot_path=snapshot.output_path,
        samples=snapshot.samples,
        observations=len(snapshot.observations),
        process_lines=len(snapshot.process_lines),
        states=dict(sorted(states.items())),
        ports=dict(sorted(ports.items())),
        capture_matches=capture_matches,
        capture_misses=capture_misses,
        established=established,
        syn_sent=syn_sent,
        established_with_sendq=established_with_sendq,
        primary_endpoint=primary,
    )


def _endpoint_text_lines(summary: ProbeEndpointSummary | None) -> list[str]:
    if summary is None:
        return ["endpoint correlation: n/a"]
    states = ", ".join(f"{key}={value}" for key, value in summary.states.items()) or "нет"
    ports = ", ".join(f"{key}={value}" for key, value in summary.ports.items()) or "нет"
    return [
        "endpoint correlation:",
        f"  samples: {summary.samples}; observations: {summary.observations}; process lines: {summary.process_lines}",
        f"  states: {states}",
        f"  ports: {ports}",
        f"  capture policy matches/misses: {summary.capture_matches}/{summary.capture_misses}",
        f"  ESTAB/SYN-SENT/ESTAB-with-SendQ: {summary.established}/{summary.syn_sent}/{summary.established_with_sendq}",
        f"  primary endpoint: {summary.primary_endpoint}",
        f"  snapshot: {summary.snapshot_path if summary.snapshot_path is not None else 'нет'}",
    ]


def _endpoint_markdown_lines(summary: ProbeEndpointSummary | None) -> list[str]:
    if summary is None:
        return ["endpoint correlation: `n/a`"]
    lines = [
        f"snapshot: `{summary.snapshot_path if summary.snapshot_path is not None else 'нет'}`",
        f"samples: `{summary.samples}`",
        f"observations: `{summary.observations}`",
        f"process lines: `{summary.process_lines}`",
        f"capture matches/misses: `{summary.capture_matches}` / `{summary.capture_misses}`",
        f"ESTAB / SYN-SENT / ESTAB-with-SendQ: `{summary.established}` / `{summary.syn_sent}` / `{summary.established_with_sendq}`",
        f"primary endpoint: `{summary.primary_endpoint}`",
        "",
        "| kind | values |",
        "|---|---|",
        "| states | " + (", ".join(f"`{key}={value}`" for key, value in summary.states.items()) or "нет") + " |",
        "| ports | " + (", ".join(f"`{key}={value}`" for key, value in summary.ports.items()) or "нет") + " |",
    ]
    return lines


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_size(path: Path | None) -> int | None:
    if path is None or not path.exists():
        return None
    return path.stat().st_size


def _sha256_file(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _counter_delta(before: CounterValue | None, after: CounterValue | None, field: str) -> ProbeDelta:
    if before is None or after is None:
        return ProbeDelta(None, None, None)
    b = getattr(before, field)
    a = getattr(after, field)
    return ProbeDelta(b, a, a - b)


def _size_delta(before: int | None, after: int | None) -> ProbeDelta:
    if before is None or after is None:
        return ProbeDelta(before, after, None)
    return ProbeDelta(before, after, after - before)


def _zero_counter() -> CounterValue:
    return CounterValue(0, 0)


def _find_rule_counter_from_json(payload: dict[str, Any], marker: str) -> CounterValue:
    for item in payload.get("nftables", []):
        rule = item.get("rule") if isinstance(item, dict) else None
        if not isinstance(rule, dict):
            continue
        expr = rule.get("expr")
        if not isinstance(expr, list):
            continue
        has_marker = any(isinstance(part, dict) and part.get("comment") == marker for part in expr)
        if not has_marker:
            continue
        for part in expr:
            if isinstance(part, dict) and isinstance(part.get("counter"), dict):
                counter = part["counter"]
                return CounterValue(int(counter.get("packets", 0)), int(counter.get("bytes", 0)))
    return _zero_counter()


def _find_rule_counter_from_text(text: str, marker: str) -> CounterValue:
    for line in text.splitlines():
        if marker not in line:
            continue
        match = re.search(r"counter\s+packets\s+(\d+)\s+bytes\s+(\d+)", line)
        if match:
            return CounterValue(int(match.group(1)), int(match.group(2)))
    return _zero_counter()


def _parse_nft_counters(stdout: str, table_name: str) -> ProbeNftCounters:
    markers = {
        "tcp_out": f"zap2:{table_name}:tcp-out",
        "tcp_in_synack": f"zap2:{table_name}:tcp-in-synack",
        "tcp_in_fin_rst": f"zap2:{table_name}:tcp-in-fin-rst",
    }
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return ProbeNftCounters(
            table_exists=True,
            read_ok=True,
            error="",
            tcp_out=_find_rule_counter_from_text(stdout, markers["tcp_out"]),
            tcp_in_synack=_find_rule_counter_from_text(stdout, markers["tcp_in_synack"]),
            tcp_in_fin_rst=_find_rule_counter_from_text(stdout, markers["tcp_in_fin_rst"]),
            raw_length=len(stdout),
        )
    return ProbeNftCounters(
        table_exists=True,
        read_ok=True,
        error="",
        tcp_out=_find_rule_counter_from_json(payload, markers["tcp_out"]),
        tcp_in_synack=_find_rule_counter_from_json(payload, markers["tcp_in_synack"]),
        tcp_in_fin_rst=_find_rule_counter_from_json(payload, markers["tcp_in_fin_rst"]),
        raw_length=len(stdout),
    )


def default_nft_runner(table_name: str) -> tuple[int, str, str]:
    commands = (
        ("nft", "-j", "-a", "list", "table", "inet", table_name),
        ("nft", "-a", "list", "table", "inet", table_name),
    )
    last_result: tuple[int, str, str] | None = None
    for command in commands:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        last_result = (completed.returncode, completed.stdout, completed.stderr)
        if completed.returncode == 0:
            return last_result
    return last_result or (127, "", "nft command unavailable")


def read_nft_counters(table_name: str, runner: NftRunner = default_nft_runner) -> ProbeNftCounters:
    rc, stdout, stderr = runner(table_name)
    combined_error = (stderr or stdout).strip()
    if rc != 0:
        missing = "No such file" in combined_error or "No such file or directory" in combined_error
        return ProbeNftCounters(
            table_exists=not missing,
            read_ok=False,
            error=combined_error or f"nft exited with code {rc}",
            tcp_out=_zero_counter(),
            tcp_in_synack=_zero_counter(),
            tcp_in_fin_rst=_zero_counter(),
            raw_length=len(stdout),
        )
    return _parse_nft_counters(stdout, table_name)


def _session_nfqueue(root: Path, profile_id: str) -> int | None:
    paths = ensure_runtime_store(root)
    record = _read_json(paths.sessions_dir / f"{profile_id}.session.json")
    value = record.get("nfqueueNum")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _log_sizes(snapshot: Any) -> ProbeLogSizes:
    return ProbeLogSizes(
        stdout_size=_safe_size(snapshot.session_stdout_path),
        stderr_size=_safe_size(snapshot.session_stderr_path),
        debug_size=_safe_size(snapshot.session_debug_path),
    )


def _report_paths(root: Path, profile_id: str, created_at: str) -> tuple[Path, Path]:
    safe_stamp = re.sub(r"[^0-9TZ]", "", created_at).replace("T", "-").replace("Z", "") or "unknown"
    reports_dir = ensure_runtime_store(root).root / ".zap2" / "runtime" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    base = reports_dir / f"discord-pretls-guided-probe-{profile_id}-{safe_stamp}"
    return base.with_suffix(".json"), base.with_suffix(".md")


def _make_counter_deltas(before: ProbeNftCounters | None, after: ProbeNftCounters | None) -> dict[str, ProbeDelta]:
    if before is None or after is None or not before.read_ok or not after.read_ok:
        none = ProbeDelta(None, None, None)
        return {
            "tcpOutPackets": none,
            "tcpOutBytes": none,
            "tcpInSynAckPackets": none,
            "tcpInSynAckBytes": none,
            "tcpInFinRstPackets": none,
            "tcpInFinRstBytes": none,
        }
    return {
        "tcpOutPackets": _counter_delta(before.tcp_out, after.tcp_out, "packets"),
        "tcpOutBytes": _counter_delta(before.tcp_out, after.tcp_out, "bytes"),
        "tcpInSynAckPackets": _counter_delta(before.tcp_in_synack, after.tcp_in_synack, "packets"),
        "tcpInSynAckBytes": _counter_delta(before.tcp_in_synack, after.tcp_in_synack, "bytes"),
        "tcpInFinRstPackets": _counter_delta(before.tcp_in_fin_rst, after.tcp_in_fin_rst, "packets"),
        "tcpInFinRstBytes": _counter_delta(before.tcp_in_fin_rst, after.tcp_in_fin_rst, "bytes"),
    }


def _make_log_deltas(before: ProbeLogSizes, after: ProbeLogSizes) -> dict[str, ProbeDelta]:
    return {
        "stdout": _size_delta(before.stdout_size, after.stdout_size),
        "stderr": _size_delta(before.stderr_size, after.stderr_size),
        "debug": _size_delta(before.debug_size, after.debug_size),
    }


def _delta_int(deltas: dict[str, ProbeDelta], key: str) -> int | None:
    value = deltas.get(key)
    return None if value is None else value.delta


def _verdict(
    *,
    snapshot_before: Any,
    snapshot_after: Any,
    counters_before: ProbeNftCounters | None,
    counters_after: ProbeNftCounters | None,
    counter_deltas: dict[str, ProbeDelta],
    log_deltas: dict[str, ProbeDelta],
    endpoint_summary: ProbeEndpointSummary | None,
    nfqueue_match: bool,
    strategy_compatible: bool,
) -> tuple[str, str, str]:
    if snapshot_before.saved_state != "applied":
        return (
            "V0_WORKFLOW_NOT_RUNNING",
            "owner-rules are not applied; the probe cannot validate Discord SYN while the runtime funnel is absent.",
            "Start Default workflow through the owner-confirmed path, then rerun the guided probe.",
        )
    if not strategy_compatible:
        return (
            "V0_STRATEGY_NOT_PRETLS_DIAGNOSTIC",
            "the active strategy is not marked as the Discord pre-TLS diagnostic profile; this run would not answer the intended unknown.",
            f"Select {PRETLS_DIAGNOSTIC_STRATEGY_ID}, start Default workflow, then rerun the guided probe.",
        )
    if counters_before is not None and not counters_before.read_ok:
        if not counters_before.table_exists:
            return (
                "V1_NFT_TABLE_MISSING",
                "workflow state says the runtime should be applied, but the nft table is missing or unreadable.",
                "Fix owner-rules/session state consistency before debugging Discord strategies.",
            )
        return (
            "V1_NFT_COUNTER_READ_FAILED",
            f"nft counters could not be read: {counters_before.error}",
            "Run the guided probe with sufficient privileges for read-only nft inspection, or capture manual nft output.",
        )
    if snapshot_before.session_state != "running" or snapshot_before.session_pid is None:
        return (
            "V2_NFQWS2_DEAD_BEFORE",
            "owner-rules may be present, but nfqws2 is not alive before the Discord manual action.",
            "Fix session lifecycle, stale PID, or silent nfqws2 exit before any desync tuning.",
        )
    if not nfqueue_match:
        return (
            "V2_QNUM_MISMATCH",
            "the nft queue number and session-record queue number do not match, so packets may be queued to a different listener.",
            "Fix runtime queue/session consistency before interpreting packet counters.",
        )
    out_delta = _delta_int(counter_deltas, "tcpOutPackets")
    synack_delta = _delta_int(counter_deltas, "tcpInSynAckPackets")
    if out_delta is None:
        return (
            "V1_NFT_COUNTER_READ_FAILED",
            "before/after counters are unavailable, so the guided run did not reduce the capture unknown.",
            "Fix nft counter reading or attach manual before/after output.",
        )
    if out_delta <= 0:
        if endpoint_summary is not None and endpoint_summary.established > 0:
            return (
                "V3_NO_OUT_COUNTER_DELTA_WITH_ESTAB_ENDPOINT",
                "Discord reached an ESTAB endpoint during the observation window, but the pre-TLS capture counter did not grow; the capturePolicy may not cover the actual endpoint or the counter window/state is mismatched.",
                "Correlate endpoint IP/port/UID with capturePolicy before changing desync flags.",
            )
        return (
            "V3_NO_OUT_COUNTER_DELTA",
            "Discord launch did not increase the outbound pre-TLS capture counter in this guided run.",
            "Investigate capture scope: UID, Discord process owner, edge IP list, ports, hook, or selected/applied strategy mismatch.",
        )
    if snapshot_after.session_state != "running" or snapshot_after.session_pid is None:
        return (
            "V4_NFQWS2_DIED_AFTER_HIT",
            "Discord packets hit the nft rule, but nfqws2 was not alive after the manual action.",
            "Investigate session supervision, silent exit, crash visibility, or queue lifecycle before tuning flags.",
        )
    if endpoint_summary is not None and endpoint_summary.established_with_sendq > 0:
        return (
            "V9_ESTAB_WITH_SENDQ",
            "Discord reached ESTAB during the observation window, but at least one established socket had non-zero Send-Q; the current blocker may be after TCP handshake, around first payload/TLS/updater data.",
            "Move to first-payload/TLS-stage observability instead of treating this as pure SYN-SENT only.",
        )
    if endpoint_summary is not None and endpoint_summary.established > 0:
        return (
            "V8_TCP_ESTABLISHED",
            "Discord reached an ESTAB TCP endpoint during the observation window; pure pre-TLS SYN failure is not the only current failure mode.",
            "Preserve this report and move to first-payload/TLS/updater-stage correlation.",
        )
    if synack_delta is not None and synack_delta > 0:
        return (
            "V7_SYNACK_SEEN",
            "the inbound SYN+ACK diagnostic counter increased; the remote edge responded during this run.",
            "Move to socket-state/Discord-updater/TLS-stage analysis and preserve this report.",
        )
    log_changed = any((value.delta or 0) > 0 for value in log_deltas.values())
    if log_changed:
        return (
            "V6_LOG_ACTIVITY_WITH_OUT_HIT",
            "Discord packets hit nft, nfqws2 stayed alive, and nfqws2 log files changed during the probe window.",
            "Inspect the log/debug delta and prepare a profile-selection/action proof patch if receive is still ambiguous.",
        )
    return (
        "V5_OUT_HIT_ALIVE_LOGS_SILENT",
        "Discord packets hit nft and nfqws2 stayed alive, but stdout/stderr/debug sizes did not change during the probe window.",
        "Build an nfqws2 receive/profile proof primitive; do not add more Discord presets yet.",
    )


def _default_endpoint_watch_runner(root: Path | None, seconds: int) -> DiscordEndpointSnapshot | None:
    if seconds <= 0:
        return None
    return run_discord_endpoint_watch(root=root, seconds=seconds, interval=1.0)


def _write_report(report: DiscordPretlsGuidedProbeReport) -> None:
    report.report_json_path.write_text(json.dumps(report.to_payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report.report_md_path.write_text(report.to_markdown(), encoding="utf-8")


def run_discord_pretls_guided_probe(
    root: Path | None = None,
    profile_id: str = "default",
    *,
    wait_seconds: int = DEFAULT_GUIDED_PROBE_WAIT_SECONDS,
    interactive: bool = True,
    nft_runner: NftRunner = default_nft_runner,
    endpoint_watch_runner: EndpointWatchRunner | None = _default_endpoint_watch_runner,
    emit: Emit | None = None,
    input_func: InputFunc = input,
    sleep_func: SleepFunc = time.sleep,
) -> DiscordPretlsGuidedProbeReport:
    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    created_at = _utc_now()
    report_json_path, report_md_path = _report_paths(paths.root, profile_id, created_at)
    wait_seconds = max(0, min(int(wait_seconds), 600))

    snapshot_before = runtime_nft_state_snapshot(paths.root, profile_id=profile_id)
    session_record = _read_json(paths.sessions_dir / f"{profile_id}.session.json")
    nfqueue_session = _session_nfqueue(paths.root, profile_id)
    nfqueue_match = nfqueue_session == snapshot_before.nfqueue_num if nfqueue_session is not None else False
    strategy_compatible = (
        snapshot_before.active_strategy_id == PRETLS_DIAGNOSTIC_STRATEGY_ID
        or snapshot_before.capture_policy_kind in {"desktop-early-flow-v1", "external-reference-first-data-v1"}
    )
    log_before = _log_sizes(snapshot_before)
    counters_before: ProbeNftCounters | None = None
    counters_after: ProbeNftCounters | None = None
    endpoint_snapshot: DiscordEndpointSnapshot | None = None
    endpoint_summary: ProbeEndpointSummary | None = None
    notes: list[str] = []

    if emit is not None:
        emit("Discord pre-TLS guided probe")
        emit("Purpose: validate one chain, not fix Discord: Discord SYN -> nft counter -> live nfqws2 -> log/debug delta -> verdict.")
        emit("SHELL COMMANDS are printed as shell commands. MANUAL ACTIONS are human steps and must not be typed into the shell.")

    if snapshot_before.saved_state == "applied" and snapshot_before.session_state == "running" and nfqueue_match and strategy_compatible:
        counters_before = read_nft_counters(snapshot_before.nft_table, runner=nft_runner)
        if counters_before.read_ok and emit is not None:
            emit(f"Baseline counters read: tcp-out packets={counters_before.tcp_out.packets}, bytes={counters_before.tcp_out.bytes}")
        if counters_before.read_ok:
            if interactive:
                if emit is not None:
                    emit("")
                    emit("MANUAL ACTION — do not type this into shell:")
                    emit("  Close Discord if it is open, then open Discord from your desktop menu and wait until it says Checking for updates.")
                    emit("  Return here and press Enter after the updater spinner is visible.")
                input_func("Press Enter after the MANUAL ACTION is complete: ")
                if wait_seconds > 0 and emit is not None:
                    emit(f"Observation window: keeping Discord open and sampling endpoints/counters for {wait_seconds} seconds...")
            elif wait_seconds > 0:
                if emit is not None:
                    emit("")
                    emit("MANUAL ACTION WINDOW — do not type this into shell:")
                    emit(f"  Open Discord now. The probe will observe endpoints for {wait_seconds} seconds before reading after-counters.")
            if wait_seconds > 0:
                if endpoint_watch_runner is not None:
                    endpoint_snapshot = endpoint_watch_runner(paths.root, wait_seconds)
                else:
                    sleep_func(wait_seconds)
            counters_after = read_nft_counters(snapshot_before.nft_table, runner=nft_runner)
    else:
        if snapshot_before.saved_state != "applied":
            notes.append("owner-rules are not applied; the guided probe stopped before manual Discord action.")
        if snapshot_before.session_state != "running":
            notes.append("nfqws2 session is not running; queue bypass can make packet counters misleading.")
        if not nfqueue_match:
            notes.append("nfqueue number from active snapshot does not match session record or session record has no nfqueue.")
        if not strategy_compatible:
            notes.append("active strategy is not the pre-TLS diagnostic strategy/capturePolicy.")

    snapshot_after = runtime_nft_state_snapshot(paths.root, profile_id=profile_id)
    session_status_after = runtime_session_status(paths.root, profile_id=profile_id)
    # runtime_nft_state_snapshot already embeds current session status, but keep an
    # explicit status read so tests can reason about the after-state source.
    del session_status_after
    log_after = _log_sizes(snapshot_after)
    counter_deltas = _make_counter_deltas(counters_before, counters_after)
    log_deltas = _make_log_deltas(log_before, log_after)
    endpoint_summary = _summarize_endpoints(endpoint_snapshot, capture_ips=snapshot_before.queued_edge_ips, capture_ports=snapshot_before.queued_tcp_ports)
    verdict, meaning, next_branch = _verdict(
        snapshot_before=snapshot_before,
        snapshot_after=snapshot_after,
        counters_before=counters_before,
        counters_after=counters_after,
        counter_deltas=counter_deltas,
        log_deltas=log_deltas,
        endpoint_summary=endpoint_summary,
        nfqueue_match=nfqueue_match,
        strategy_compatible=strategy_compatible,
    )
    if counters_before is not None and not counters_before.read_ok:
        notes.append(f"before nft read failed: {counters_before.error}")
    if counters_after is not None and not counters_after.read_ok:
        notes.append(f"after nft read failed: {counters_after.error}")
    if endpoint_summary is not None:
        notes.append(f"endpoint observations: {endpoint_summary.observations}; states={endpoint_summary.states}")
    if session_record.get("runtimeArgs"):
        notes.append(f"runtime args count: {len(session_record.get('runtimeArgs', []))}")
    notes.append("The probe never launches Discord by itself and never mutates firewall/service state.")

    report = DiscordPretlsGuidedProbeReport(
        profile_id=profile_id,
        selected_strategy_id=snapshot_before.selected_strategy_id,
        active_strategy_id=snapshot_before.active_strategy_id,
        workflow_state=snapshot_before.saved_state,
        session_state_before=snapshot_before.session_state,
        session_state_after=snapshot_after.session_state,
        session_pid_before=snapshot_before.session_pid,
        session_pid_after=snapshot_after.session_pid,
        nfqueue_snapshot=snapshot_before.nfqueue_num,
        nfqueue_session=nfqueue_session,
        nfqueue_match=nfqueue_match,
        nft_table=snapshot_before.nft_table,
        capture_policy_kind=snapshot_before.capture_policy_kind,
        strategy_compatible=strategy_compatible,
        owner_rules_applied=snapshot_before.saved_state == "applied",
        counters_before=counters_before,
        counters_after=counters_after,
        counter_deltas=counter_deltas,
        log_sizes_before=log_before,
        log_sizes_after=log_after,
        log_deltas=log_deltas,
        endpoint_summary=endpoint_summary,
        args_path=snapshot_before.session_args_path,
        args_hash=_sha256_file(snapshot_before.session_args_path),
        stdout_path=snapshot_before.session_stdout_path,
        stderr_path=snapshot_before.session_stderr_path,
        debug_path=snapshot_before.session_debug_path,
        report_json_path=report_json_path,
        report_md_path=report_md_path,
        verdict=verdict,
        meaning=meaning,
        next_branch=next_branch,
        manual_action_mode="interactive-enter" if interactive else f"timed-wait-{wait_seconds}s",
        waited_seconds=wait_seconds if not interactive else 0,
        created_at=created_at,
        notes=tuple(notes),
    )
    _write_report(report)
    return report


def runtime_discord_pretls_guided_probe_to_text(
    root: Path | None = None,
    profile_id: str = "default",
    *,
    wait_seconds: int = DEFAULT_GUIDED_PROBE_WAIT_SECONDS,
    interactive: bool = True,
    emit: Emit | None = None,
) -> str:
    return run_discord_pretls_guided_probe(
        root=root,
        profile_id=profile_id,
        wait_seconds=wait_seconds,
        interactive=interactive,
        emit=emit,
    ).to_text()
