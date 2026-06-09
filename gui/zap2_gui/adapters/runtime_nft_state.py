"""Read-only nftables/NFQUEUE observability helpers for pre-TLS diagnostics.

Stage 7n intentionally does not mutate nftables.  It renders the owner-visible
capture plan and, when state from a previous owner-confirmed apply exists,
shows where to inspect counters.  The actual counter reads remain manual unless
the owner runs nft themselves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .runtime_apply import create_runtime_apply_plan
from .runtime_state import ensure_runtime_store
from ..project_paths import discover_layout


@dataclass(frozen=True)
class RuntimeNftStateSnapshot:
    """Read-only summary of the generated nft capture plan."""

    profile_id: str
    strategy_id: str
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

    def to_text(self) -> str:
        edge_text = ", ".join(self.queued_edge_ips) if self.queued_edge_ips else "нет / runtime-derived hostlist"
        tcp_text = ", ".join(self.queued_tcp_ports) if self.queued_tcp_ports else "нет"
        udp_text = ", ".join(self.queued_udp_ports) if self.queued_udp_ports else "нет"
        return "\n".join(
            [
                "Runtime nft/NFQUEUE state snapshot",
                f"profile: {self.profile_id}",
                f"strategy: {self.strategy_id}",
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
                f"owner-rules state path: {self.state_path}",
                "manual counter check:",
                f"  sudo nft list table inet {self.nft_table} -a",
                "interpretation:",
                "  - tcpdump sees Discord SYN but counters stay 0 => nft scope/hook/UID/port/IP match is wrong.",
                "  - counters move but nfqws2 debug is silent => queue/session mismatch or nfqws2 is not attached.",
                "  - nfqws2 debug sees packet but profile is wrong => classification needs IP-edge/ipcache work.",
                "read-only: yes",
                "executes now: no",
                "mutates services/firewall now: no",
            ]
        )


def _read_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def runtime_nft_state_snapshot(root: Path | None = None, profile_id: str = "default") -> RuntimeNftStateSnapshot:
    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    plan = create_runtime_apply_plan(paths.root, action="apply", profile_id=profile_id)
    state_path = paths.sessions_dir / f"{profile_id}.owner-rules.json"
    state = _read_state(state_path)
    saved_state = str(state.get("state") or "not-applied") if state else "not-applied"
    capture_policy = plan.capture_policy or {}
    return RuntimeNftStateSnapshot(
        profile_id=profile_id,
        strategy_id=plan.strategy_id,
        nft_table=plan.nft_table,
        nfqueue_num=plan.nfqueue_num,
        queued_tcp_ports=plan.queued_tcp_ports,
        queued_udp_ports=plan.queued_udp_ports,
        queued_edge_ips=plan.queued_edge_ips,
        capture_policy_kind=str(capture_policy.get("kind") or "runtime-derived"),
        queue_input_syn_ack=plan.queue_input_syn_ack,
        queue_input_fin_rst=plan.queue_input_fin_rst,
        owner_uid=plan.owner_uid,
        owner_uid_source=plan.owner_uid_source,
        state_path=state_path,
        state_exists=state_path.exists(),
        saved_state=saved_state,
    )


def runtime_nft_state_to_text(root: Path | None = None, profile_id: str = "default") -> str:
    return runtime_nft_state_snapshot(root=root, profile_id=profile_id).to_text()
