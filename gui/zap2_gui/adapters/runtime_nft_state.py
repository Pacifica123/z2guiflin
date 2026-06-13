"""Read-only nftables/NFQUEUE observability helpers for pre-TLS diagnostics.

Stage 7n introduced explicit ``capturePolicy`` and nft counters.  Stage 7n1
makes the snapshot active-state aware: it prefers the owner-confirmed applied
rules/session state over the currently selected strategy so the owner can debug
what is actually running.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime_apply import create_runtime_apply_plan
from .runtime_session import runtime_session_status
from .runtime_state import ensure_runtime_store
from ..project_paths import discover_layout


@dataclass(frozen=True)
class RuntimeNftStateSnapshot:
    """Read-only summary of the active/generated nft capture plan."""

    profile_id: str
    selected_strategy_id: str
    active_strategy_id: str
    nft_table: str
    nfqueue_num: int
    queued_tcp_ports: tuple[str, ...]
    queued_udp_ports: tuple[str, ...]
    queued_edge_ips: tuple[str, ...]
    capture_policy_kind: str
    queue_input_syn_ack: bool
    queue_input_fin_rst: bool
    owner_uid: int
    owner_uid_source: str
    state_path: Path
    state_exists: bool
    saved_state: str
    state_source: str
    session_state: str
    session_message: str
    session_pid: int | None
    session_path: Path
    session_plan_id: str | None
    session_args_path: Path | None
    session_stdout_path: Path | None
    session_stderr_path: Path | None
    session_debug_path: Path | None
    session_strategy_mismatch: bool

    def to_text(self) -> str:
        edge_text = ", ".join(self.queued_edge_ips) if self.queued_edge_ips else "нет / runtime-derived hostlist"
        tcp_text = ", ".join(self.queued_tcp_ports) if self.queued_tcp_ports else "нет"
        udp_text = ", ".join(self.queued_udp_ports) if self.queued_udp_ports else "нет"
        mismatch = "yes" if self.session_strategy_mismatch else "no"
        pid_text = str(self.session_pid) if self.session_pid is not None else "нет"
        lines = [
            "Runtime nft/NFQUEUE state snapshot",
            f"profile: {self.profile_id}",
            f"selected strategy: {self.selected_strategy_id}",
            f"active/applied strategy: {self.active_strategy_id}",
            f"strategy mismatch: {mismatch}",
            f"nft table: inet {self.nft_table}",
            f"nfqueue: {self.nfqueue_num}",
            f"queued TCP ports: {tcp_text}",
            f"queued UDP ports: {udp_text}",
            f"queued edge IPs: {edge_text}",
            f"capture policy: {self.capture_policy_kind}",
            f"input SYN+ACK queue: {'yes' if self.queue_input_syn_ack else 'no'}",
            f"input FIN/RST queue: {'yes' if self.queue_input_fin_rst else 'no'}",
            "nft counters: generated rules include counter",
            f"owner uid scope: {self.owner_uid} ({self.owner_uid_source})",
            f"owner-rules state: {self.saved_state}",
            f"owner-rules state source: {self.state_source}",
            f"owner-rules state path: {self.state_path}",
            f"nfqws2 session state: {self.session_state}",
            f"nfqws2 session pid: {pid_text}",
            f"nfqws2 session path: {self.session_path}",
        ]
        if self.session_message:
            lines.append(f"nfqws2 session message: {self.session_message}")
        if self.session_plan_id:
            lines.append(f"nfqws2 session plan id: {self.session_plan_id}")
        if self.session_args_path is not None:
            lines.append(f"nfqws2 args file: {self.session_args_path}")
        if self.session_stdout_path is not None:
            lines.append(f"nfqws2 stdout log: {self.session_stdout_path}")
        if self.session_stderr_path is not None:
            lines.append(f"nfqws2 stderr log: {self.session_stderr_path}")
        if self.session_debug_path is not None:
            lines.append(f"nfqws2 debug log: {self.session_debug_path}")
        lines.extend(
            [
                "manual counter check:",
                f"  sudo nft -a list table inet {self.nft_table}",
                "manual synchronized probe:",
                "  Prefer the guided probe instead:",
                "    PYTHONPATH=gui python -m zap2_gui.app --runtime-discord-pretls-guided-probe",
                "  SHELL COMMAND if you still need raw nft output:",
                f"    sudo nft -a list table inet {self.nft_table}",
                "  MANUAL ACTION — do not type into shell:",
                "    Open Discord from the desktop menu and wait until Checking for updates.",
                "interpretation:",
                "  - tcpdump sees Discord SYN but counters stay 0 => nft scope/hook/UID/port/IP match is wrong.",
                "  - counters move but nfqws2 session is stale/not-running => queue bypasses userspace; fix session health first.",
                "  - counters move and nfqws2 is running but debug is silent => queue/session mismatch or debug/profile visibility gap.",
                "  - nfqws2 debug sees packet but profile is wrong => classification needs IP-edge/ipcache work.",
                "read-only: yes",
                "executes now: no",
                "mutates services/firewall now: no",
            ]
        )
        return "\n".join(lines)


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _tuple_from_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _path_or_none(value: object) -> Path | None:
    if not value:
        return None
    return Path(str(value))


def runtime_nft_state_snapshot(root: Path | None = None, profile_id: str = "default") -> RuntimeNftStateSnapshot:
    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    generated_plan = create_runtime_apply_plan(paths.root, action="apply", profile_id=profile_id)
    state_path = paths.sessions_dir / f"{profile_id}.owner-rules.json"
    state = _read_state(state_path)
    saved_state = str(state.get("state") or "not-applied") if state else "not-applied"
    state_source = "owner-rules-state" if state and saved_state == "applied" else "generated-plan"

    if state_source == "owner-rules-state":
        strategy_id = str(state.get("strategyId") or generated_plan.strategy_id)
        nft_table = str(state.get("nftTable") or generated_plan.nft_table)
        nfqueue_num = int(state.get("nfqueueNum") or generated_plan.nfqueue_num)
        queued_tcp_ports = _tuple_from_list(state.get("queuedTcpPorts")) or generated_plan.queued_tcp_ports
        queued_udp_ports = _tuple_from_list(state.get("queuedUdpPorts")) or generated_plan.queued_udp_ports
        queued_edge_ips = _tuple_from_list(state.get("queuedEdgeIps")) or generated_plan.queued_edge_ips
        capture_policy = state.get("capturePolicy") if isinstance(state.get("capturePolicy"), dict) else generated_plan.capture_policy or {}
        queue_input_syn_ack = bool(state.get("queueInputSynAck", generated_plan.queue_input_syn_ack))
        queue_input_fin_rst = bool(state.get("queueInputFinRst", generated_plan.queue_input_fin_rst))
        owner_uid = int(state.get("ownerUid", generated_plan.owner_uid))
        owner_uid_source = str(state.get("ownerUidSource", generated_plan.owner_uid_source))
    else:
        strategy_id = generated_plan.strategy_id
        nft_table = generated_plan.nft_table
        nfqueue_num = generated_plan.nfqueue_num
        queued_tcp_ports = generated_plan.queued_tcp_ports
        queued_udp_ports = generated_plan.queued_udp_ports
        queued_edge_ips = generated_plan.queued_edge_ips
        capture_policy = generated_plan.capture_policy or {}
        queue_input_syn_ack = generated_plan.queue_input_syn_ack
        queue_input_fin_rst = generated_plan.queue_input_fin_rst
        owner_uid = generated_plan.owner_uid
        owner_uid_source = generated_plan.owner_uid_source

    session_status = runtime_session_status(paths.root, profile_id=profile_id)
    session_record = _read_state(paths.sessions_dir / f"{profile_id}.session.json")
    session_strategy_mismatch = bool(strategy_id != generated_plan.strategy_id)
    return RuntimeNftStateSnapshot(
        profile_id=profile_id,
        selected_strategy_id=generated_plan.strategy_id,
        active_strategy_id=strategy_id,
        nft_table=nft_table,
        nfqueue_num=nfqueue_num,
        queued_tcp_ports=queued_tcp_ports,
        queued_udp_ports=queued_udp_ports,
        queued_edge_ips=queued_edge_ips,
        capture_policy_kind=str(capture_policy.get("kind") or "runtime-derived") if isinstance(capture_policy, dict) else "runtime-derived",
        queue_input_syn_ack=queue_input_syn_ack,
        queue_input_fin_rst=queue_input_fin_rst,
        owner_uid=owner_uid,
        owner_uid_source=owner_uid_source,
        state_path=state_path,
        state_exists=state_path.exists(),
        saved_state=saved_state,
        state_source=state_source,
        session_state=session_status.state,
        session_message=session_status.message,
        session_pid=session_status.pid,
        session_path=session_status.session_path,
        session_plan_id=session_status.plan_id,
        session_args_path=_path_or_none(session_record.get("argsPath")),
        session_stdout_path=_path_or_none(session_record.get("stdoutLogPath")),
        session_stderr_path=_path_or_none(session_record.get("stderrLogPath")),
        session_debug_path=_path_or_none(session_record.get("debugLogPath")),
        session_strategy_mismatch=session_strategy_mismatch,
    )


def runtime_nft_state_to_text(root: Path | None = None, profile_id: str = "default") -> str:
    return runtime_nft_state_snapshot(root=root, profile_id=profile_id).to_text()


def runtime_pretls_probe_to_text(root: Path | None = None, profile_id: str = "default") -> str:
    snapshot = runtime_nft_state_snapshot(root=root, profile_id=profile_id)
    verdict_lines: list[str] = [
        "Runtime pre-TLS probe checklist",
        f"profile: {snapshot.profile_id}",
        f"active/applied strategy: {snapshot.active_strategy_id}",
        f"nfqws2 session: {snapshot.session_state}",
        f"nfqws2 pid: {snapshot.session_pid if snapshot.session_pid is not None else 'нет'}",
        f"nft table: inet {snapshot.nft_table}",
        f"nfqueue: {snapshot.nfqueue_num}",
    ]
    if snapshot.saved_state != "applied":
        verdict_lines.append("verdict: owner-rules are not applied; start Default workflow before probing Discord SYN.")
    elif snapshot.session_state != "running":
        verdict_lines.append("verdict: nft rules may be applied, but nfqws2 is not running; queue bypass can hide userspace diagnostics.")
    else:
        verdict_lines.append("verdict: ready for synchronized Discord SYN probe; compare nft counters before/after launching Discord.")
    verdict_lines.extend(
        [
            "next guided command:",
            "  PYTHONPATH=gui python -m zap2_gui.app --runtime-discord-pretls-guided-probe",
            "manual action warning:",
            "  Open Discord from the desktop/menu only when the guided probe asks for MANUAL ACTION.",
            "  Do not type 'launch Discord' into the shell; it is not a command.",
            "raw nft command, only while workflow is running:",
            f"  sudo nft -a list table inet {snapshot.nft_table}",
            "read-only: yes",
            "executes now: no",
            "mutates services/firewall now: no",
        ]
    )
    return "\n".join(verdict_lines)
