"""NFQUEUE number policy for Zap2 runtime.

Fixed NFQUEUE number 200 was convenient while the runtime was still plan-only.
During GUI single-button testing it became a practical problem: a previous
manually-started/stale nfqws2 process can keep queue 200 bound outside the
current workspace state. The next GUI start then reaches nfq_create_queue() and
fails with EPERM, while apply/revert still works correctly.

This module gives every runtime owner identity (desktop UID + workspace + profile)
a deterministic queue number in a small private range. The number is stable for
that identity, appears in both nftables apply plan and nfqws2 session args, and
can be overridden explicitly with ZAP2_NFQUEUE_NUM for local diagnostics.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..project_paths import discover_layout
from .runtime_owner import runtime_owner_identity

NFQUEUE_BASE = 200
NFQUEUE_SPAN = 400
NFQUEUE_MIN = 0
NFQUEUE_MAX = 65535
NFQUEUE_ENV = "ZAP2_NFQUEUE_NUM"


@dataclass(frozen=True)
class RuntimeQueueSelection:
    """Resolved NFQUEUE number and metadata for diagnostics."""

    profile_id: str
    qnum: int
    source: str
    base: int = NFQUEUE_BASE
    span: int = NFQUEUE_SPAN
    env_name: str = NFQUEUE_ENV

    def to_dict(self) -> dict[str, object]:
        return {
            "profileId": self.profile_id,
            "qnum": self.qnum,
            "source": self.source,
            "base": self.base,
            "span": self.span,
            "envName": self.env_name,
        }

    def to_text(self) -> str:
        return "\n".join(
            [
                f"Runtime NFQUEUE для profile: {self.profile_id}",
                f"qnum: {self.qnum}",
                f"source: {self.source}",
                f"range: {self.base}..{self.base + self.span - 1}",
                f"override env: {self.env_name}",
            ]
        )


def _parse_env_qnum(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        qnum = int(value.strip(), 10)
    except ValueError as exc:
        raise ValueError(f"{NFQUEUE_ENV} должен быть целым числом NFQUEUE") from exc
    if not (NFQUEUE_MIN <= qnum <= NFQUEUE_MAX):
        raise ValueError(f"{NFQUEUE_ENV} вне допустимого диапазона {NFQUEUE_MIN}..{NFQUEUE_MAX}: {qnum}")
    return qnum


def _stable_workspace_qnum(root: Path, profile_id: str) -> int:
    identity = runtime_owner_identity(root, profile_id)
    key = identity.owner_key.encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()
    return NFQUEUE_BASE + (int(digest[:12], 16) % NFQUEUE_SPAN)


def resolve_runtime_queue(root: Path | None = None, profile_id: str = "default") -> RuntimeQueueSelection:
    """Resolve stable NFQUEUE number for one runtime owner identity.

    The default is no longer the global queue 200. This intentionally avoids
    collisions with older experimental sessions that may still be bound to 200
    but are invisible to the current workspace state.
    """

    env_qnum = _parse_env_qnum(os.environ.get(NFQUEUE_ENV))
    if env_qnum is not None:
        return RuntimeQueueSelection(profile_id=profile_id, qnum=env_qnum, source="env")
    layout = discover_layout(root)
    return RuntimeQueueSelection(profile_id=profile_id, qnum=_stable_workspace_qnum(layout.root, profile_id), source="owner-workspace-hash")


def resolve_nfqueue_num(root: Path | None = None, profile_id: str = "default") -> int:
    return resolve_runtime_queue(root=root, profile_id=profile_id).qnum


def _read_cmdline(pid: int) -> tuple[str, ...] | None:
    path = Path("/proc") / str(pid) / "cmdline"
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if not raw:
        return ()
    return tuple(part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part)


def _iter_proc_pids() -> Iterable[int]:
    proc = Path("/proc")
    if not proc.is_dir():
        return ()
    pids: list[int] = []
    for item in proc.iterdir():
        if item.name.isdigit():
            try:
                pids.append(int(item.name))
            except ValueError:
                continue
    return pids


def _args_file_contains_qnum(args_path: Path, qnum: int) -> bool:
    try:
        text = args_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    needle = f"--qnum={qnum}"
    return any(line.strip() == needle for line in text.splitlines())


def find_nfqueue_processes(qnum: int) -> tuple[dict[str, object], ...]:
    """Best-effort read-only diagnostic for nfqws2 processes using qnum.

    It is intentionally advisory only. Some /proc entries or args files may be
    unreadable; runtime must not depend on this scan for safety.
    """

    matches: list[dict[str, object]] = []
    needle = f"--qnum={qnum}"
    for pid in _iter_proc_pids():
        cmdline = _read_cmdline(pid)
        if not cmdline:
            continue
        executable = " ".join(cmdline[:2])
        if "nfqws2" not in executable and not any(part.endswith("nfqws2") for part in cmdline):
            continue
        direct = needle in cmdline
        via_args = False
        for part in cmdline:
            if not part.startswith("@"):
                continue
            args_path = Path(part[1:])
            if _args_file_contains_qnum(args_path, qnum):
                via_args = True
                break
        if direct or via_args:
            matches.append({"pid": pid, "cmdline": list(cmdline), "match": "direct" if direct else "args-file"})
    return tuple(matches)


def ensure_nfqueue_available(qnum: int) -> None:
    """Fail before launch when another nfqws2 already owns the queue.

    The /proc scan is best-effort, but a positive match is actionable evidence.
    We intentionally do not allocate a random replacement queue because queue
    identity is part of the confirmed runtime plan.
    """

    conflicts = find_nfqueue_processes(qnum)
    if not conflicts:
        return
    details = "; ".join(
        f"pid={item.get('pid')} ({item.get('match')})" for item in conflicts[:8]
    )
    raise ValueError(
        f"NFQUEUE {qnum} уже используется другим nfqws2 process: {details}. "
        "Остановите внешний/старый runtime или выберите явный ZAP2_NFQUEUE_NUM и заново подтвердите plan."
    )
