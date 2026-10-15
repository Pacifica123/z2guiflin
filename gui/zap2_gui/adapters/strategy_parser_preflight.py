"""Read-only nfqws2 parser preflight for the selected workspace strategy.

The check deliberately uses upstream ``nfqws2 --dry-run``. It validates command
line syntax and referenced files without creating an NFQUEUE listener or
modifying nftables. Upstream Zapret2 documents one important limitation: on
Linux this mode does not initialize Lua, so Lua syntax/runtime errors remain a
separate class of failure.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .workspace_profiles import load_workspace_catalog
from .preset_editor import validate_new_filter_args
from .runtime_queue import resolve_runtime_queue
from .strategy_file_inputs import strategy_file_dependency_blockers
from ..project_paths import discover_layout

STRATEGY_PREFLIGHT_STAGE = "v0.4-alpha_stage8h"
DEFAULT_PREFLIGHT_TIMEOUT_SECONDS = 15.0


def _default_nfqws2_binary(root: Path) -> Path:
    return root / "core" / "zapret2" / "nfq2" / "nfqws2"


def _tail(text: str, *, max_chars: int = 1600) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def strategy_parser_preflight_to_text(
    *,
    profile_id: str = "default",
    nfqws2_binary: str | None = None,
    timeout_seconds: float = DEFAULT_PREFLIGHT_TIMEOUT_SECONDS,
    root: Path | None = None,
) -> str:
    """Run ``nfqws2 --dry-run`` for the currently selected strategy.

    No sudo is requested, no process is left running, and no firewall/NFQUEUE
    state is changed. The function executes only the parser validation mode of
    the already-built local nfqws2 binary.
    """

    if timeout_seconds <= 0 or timeout_seconds > 120:
        raise ValueError("strategy parser preflight timeout должен быть >0 и <=120 секунд")

    layout = discover_layout(root)
    catalog = load_workspace_catalog(layout.root)
    profiles = catalog.profile_by_id()
    strategies = catalog.strategy_by_id()
    if profile_id not in profiles:
        raise ValueError(f"Неизвестный workspace-профиль: {profile_id}")
    profile = profiles[profile_id]
    if profile.strategy_id not in strategies:
        raise ValueError(f"Для profile {profile_id} не найдена strategy {profile.strategy_id}")
    strategy = strategies[profile.strategy_id]
    queue = resolve_runtime_queue(root=layout.root, profile_id=profile_id)

    binary = Path(nfqws2_binary).expanduser() if nfqws2_binary else _default_nfqws2_binary(layout.root)
    binary_ready = binary.is_file() and os.access(binary, os.X_OK)
    hostlist_missing = tuple(
        item.path
        for item in profile.hostlists
        if not (layout.root / item.path).is_file()
    )
    strategy_file_blockers = strategy_file_dependency_blockers(layout.root, strategy.runtime_args)

    lines = [
        "Strategy parser preflight",
        f"stage: {STRATEGY_PREFLIGHT_STAGE}",
        f"profile: {profile_id}",
        f"strategy: {strategy.strategy_id}",
        f"nfqueue qnum: {queue.qnum}",
        f"nfqueue source: {queue.source}",
        f"binary: {binary}",
        f"binary exists/executable: {'yes' if binary_ready else 'no'}",
        f"runtime args: {len(strategy.runtime_args)}",
        f"profile hostlists present: {'yes' if not hostlist_missing else 'no'}",
        f"strategy file dependencies present: {'yes' if not strategy_file_blockers else 'no'}",
        "mode: nfqws2 --dry-run",
        "requires sudo: no",
        "mutates nftables/NFQUEUE: no",
        "starts persistent nfqws2: no",
    ]
    if hostlist_missing:
        lines.append("missing hostlists: " + ", ".join(hostlist_missing))
    if strategy_file_blockers:
        lines.append("strategy file blockers:")
        lines.extend(f"  - {item.message}" for item in strategy_file_blockers)
        lines.extend(
            [
                "verdict: MISSING_STRATEGY_FILE_DEPENDENCIES",
                "next: добавьте referenced hostlist/ipset files или повторите TXT import с каталогом зависимостей",
                "limitation: --dry-run не запускался, потому что обязательные file inputs отсутствуют",
            ]
        )
        return "\n".join(lines)
    filter_errors = validate_new_filter_args(strategy.runtime_args)
    if filter_errors:
        lines.append("filter option errors (nfqws2 1.0.5+ --filter-mark/--filter-ssid-neg):")
        lines.extend(f"  - {item}" for item in filter_errors)
        lines.extend(
            [
                "verdict: INVALID_FILTER_OPTIONS",
                "next: исправьте --filter-mark=mark[/mask] или --filter-ssid-neg[=0|1] в стратегии",
                "limitation: --dry-run не запускался, потому что статическая проверка фильтров не прошла",
            ]
        )
        return "\n".join(lines)
    if not binary_ready:
        lines.extend(
            [
                "verdict: UNAVAILABLE_NFQWS2",
                "next: build local target nfqws2, then repeat this preflight",
                "limitation: --dry-run validates CLI/files but does not initialize Lua on Linux",
            ]
        )
        return "\n".join(lines)

    argv = (str(binary), "--dry-run", f"--qnum={queue.qnum}", *strategy.runtime_args)
    try:
        result = subprocess.run(
            argv,
            cwd=layout.root,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _tail(exc.stdout if isinstance(exc.stdout, str) else "")
        stderr = _tail(exc.stderr if isinstance(exc.stderr, str) else "")
        lines.extend([f"verdict: TIMEOUT", f"timeout seconds: {timeout_seconds:g}"])
        if stdout:
            lines.extend(["stdout tail:", stdout])
        if stderr:
            lines.extend(["stderr tail:", stderr])
        lines.append("limitation: --dry-run validates CLI/files but does not initialize Lua on Linux")
        return "\n".join(lines)

    stdout = _tail(result.stdout)
    stderr = _tail(result.stderr)
    lines.extend(
        [
            f"exit code: {result.returncode}",
            f"verdict: {'PASS' if result.returncode == 0 else 'FAIL'}",
        ]
    )
    if stdout:
        lines.extend(["stdout tail:", stdout])
    if stderr:
        lines.extend(["stderr tail:", stderr])
    lines.append("limitation: --dry-run validates CLI/files but does not initialize Lua on Linux")
    return "\n".join(lines)
