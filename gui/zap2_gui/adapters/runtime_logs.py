"""GUI/CLI runtime log aggregation helpers.

Этот слой только читает `.zap2/runtime` и не выполняет privileged actions. Он
нужен, чтобы вкладка «Логи» показывала причины падений, успешные запуски и
важные stderr-tail без необходимости искать файлы вручную.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime_state import ensure_runtime_store
from ..project_paths import discover_layout


@dataclass(frozen=True)
class RuntimeLogSnapshot:
    """Read-only snapshot runtime logs for one profile."""

    profile_id: str
    runtime_log_path: Path
    stdout_log_path: Path
    stderr_log_path: Path
    debug_log_path: Path
    runtime_events: tuple[dict[str, Any], ...]
    stdout_tail: str
    stderr_tail: str
    debug_tail: str
    debug_size_bytes: int | None

    def to_text(self) -> str:
        lines = [
            f"Runtime logs для profile: {self.profile_id}",
            f"runtime log: {self.runtime_log_path}",
            f"stdout log: {self.stdout_log_path}",
            f"stderr log: {self.stderr_log_path}",
            f"debug log: {self.debug_log_path}",
            f"debug size bytes: {self.debug_size_bytes if self.debug_size_bytes is not None else 'нет'}",
            "",
            "Последние runtime events:",
        ]
        if self.runtime_events:
            for event in self.runtime_events:
                created = event.get("createdAt", "?")
                level = event.get("level", "?")
                etype = event.get("eventType", "?")
                message = str(event.get("message", "")).strip()
                lines.append(f"- {created} [{level}] {etype}: {message}")
        else:
            lines.append("- нет событий")
        if self.stderr_tail:
            lines.extend(["", "stderr tail:", self.stderr_tail])
        if self.stdout_tail:
            lines.extend(["", "stdout tail:", self.stdout_tail])
        if self.debug_tail:
            lines.extend(["", "debug tail:", self.debug_tail])
        lines.extend(["", "read-only: yes", "executes now: no", "mutates services/firewall now: no"])
        return "\n".join(lines)


def _tail(path: Path, max_chars: int) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:].strip()


def _read_jsonl_tail(path: Path, max_events: int) -> tuple[dict[str, Any], ...]:
    if not path.exists():
        return ()
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            parsed = {"eventType": "unparsed-log-line", "level": "warning", "message": line}
        rows.append(parsed)
    return tuple(rows[-max_events:])


def runtime_log_snapshot(root: Path | None = None, profile_id: str = "default", *, max_events: int = 12, max_tail_chars: int = 2400) -> RuntimeLogSnapshot:
    """Read latest runtime logs without executing anything."""

    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    runtime_log_path = paths.logs_dir / f"{profile_id}.runtime.jsonl"
    stdout_log_path = paths.logs_dir / f"{profile_id}.nfqws2.stdout.log"
    stderr_log_path = paths.logs_dir / f"{profile_id}.nfqws2.stderr.log"
    debug_log_path = paths.logs_dir / f"{profile_id}.nfqws2.debug.log"
    debug_size = debug_log_path.stat().st_size if debug_log_path.exists() else None
    return RuntimeLogSnapshot(
        profile_id=profile_id,
        runtime_log_path=runtime_log_path,
        stdout_log_path=stdout_log_path,
        stderr_log_path=stderr_log_path,
        debug_log_path=debug_log_path,
        runtime_events=_read_jsonl_tail(runtime_log_path, max_events=max_events),
        stdout_tail=_tail(stdout_log_path, max_tail_chars),
        stderr_tail=_tail(stderr_log_path, max_tail_chars),
        debug_tail=_tail(debug_log_path, max_tail_chars),
        debug_size_bytes=debug_size,
    )


def runtime_log_snapshot_to_text(root: Path | None = None, profile_id: str = "default") -> str:
    return runtime_log_snapshot(root=root, profile_id=profile_id).to_text()
