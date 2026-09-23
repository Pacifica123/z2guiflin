"""P02 canonical runtime ownership/status projection.

This module is deliberately small: it composes already-proven nft/session
observations into one owner state without inventing a second lifecycle engine.
GUI and CLI should project this same object.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from .privileged_executor import PrivilegedExecutorStatus, privileged_executor_status
from .runtime_apply import CommandRunner, RuntimeOwnerReconciliation, reconcile_runtime_owner_rules
from .runtime_session import RuntimeSessionStatus, runtime_session_status
from .runtime_state import runtime_store_paths
from ..project_paths import discover_layout

OwnershipState = Literal[
    "absent",
    "owned-active",
    "owned-stale",
    "owned-partial",
    "foreign-conflict",
    "unknown",
    "migration-required",
]


@dataclass(frozen=True)
class RuntimeKernelStatus:
    profile_id: str
    ownership_state: OwnershipState
    run_id: str | None
    plan_id: str | None
    plan_hash: str | None
    nft: RuntimeOwnerReconciliation
    session: RuntimeSessionStatus
    executor: PrivilegedExecutorStatus
    next_safe_action: str
    message: str

    def to_text(self) -> str:
        return "\n".join([
            f"P02 runtime kernel status: {self.ownership_state}",
            f"profile: {self.profile_id}",
            f"run id: {self.run_id or 'нет'}",
            f"plan id: {self.plan_id or 'нет'}",
            f"plan hash: {self.plan_hash or 'нет'}",
            f"nft evidence: {self.nft.state}",
            f"session evidence: {self.session.state}",
            f"privileged executor: {self.executor.state}",
            f"next safe action: {self.next_safe_action}",
            f"message: {self.message}",
            "foreign/unknown auto-delete: no",
            "read-only: yes",
            "mutates resources now: no",
        ])


def _workflow_lineage(root: Path, profile_id: str) -> tuple[str | None, str | None, str | None]:
    paths = runtime_store_paths(root)
    path = paths.sessions_dir / f"{profile_id}.default-workflow.json"
    if not path.is_file():
        return None, None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, None, None
    if not isinstance(data, dict):
        return None, None, None
    return (
        str(data.get("runId", "")) or None,
        str(data.get("planId", "")) or None,
        str(data.get("planHash", "")) or None,
    )


def _classify(nft: RuntimeOwnerReconciliation, session: RuntimeSessionStatus) -> tuple[OwnershipState, str, str]:
    if session.state == "migration-required":
        return "migration-required", "run explicit runtime MigrationTxn", "legacy live session needs explicit receipted migration"
    if nft.state == "conflict":
        return "foreign-conflict", "inspect foreign nft table; do not delete automatically", nft.message
    if nft.state == "unknown" or session.state == "unknown":
        return "unknown", "collect ownership evidence; do not mutate unknown resources", "at least one resource cannot be proven owned"
    nft_active = nft.state in {"consistent-applied", "cleanup-required"}
    session_active = session.state == "running"
    if nft.state == "consistent-applied" and session_active:
        return "owned-active", "normal confirmed stop when desired", "owned nft/session resources agree"
    if nft.state == "clean" and session.state in {"not-started", "stopped"}:
        return "absent", "prepare/confirm start plan when desired", "no active owned runtime resources observed"
    if nft.state == "stale-state" or session.state == "stale":
        return "owned-stale", "reconcile only proven owned stale state", "owned state exists but observed resources are stale"
    if nft_active != session_active or nft.state == "cleanup-required":
        return "owned-partial", "use confirmed reconcile/revert; never repair-delete foreign resources", "composite runtime is only partially present"
    return "owned-partial", "inspect composite receipts before mutation", "composite resource state is incomplete"


def runtime_kernel_status(
    root: Path | None = None,
    profile_id: str = "default",
    *,
    nft_runner: CommandRunner | None = None,
    executor_path: Path | None = None,
) -> RuntimeKernelStatus:
    layout = discover_layout(root)
    nft = reconcile_runtime_owner_rules(layout.root, profile_id, runner=nft_runner)
    session = runtime_session_status(layout.root, profile_id)
    run_id, plan_id, plan_hash = _workflow_lineage(layout.root, profile_id)
    executor = privileged_executor_status(layout.root, **({"installed_path": executor_path} if executor_path is not None else {}))
    state, next_action, message = _classify(nft, session)
    return RuntimeKernelStatus(profile_id, state, run_id, plan_id, plan_hash, nft, session, executor, next_action, message)


__all__ = ["OwnershipState", "RuntimeKernelStatus", "runtime_kernel_status"]
