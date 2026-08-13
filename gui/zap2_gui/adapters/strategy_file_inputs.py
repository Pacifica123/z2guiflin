"""Read-only file dependencies embedded in nfqws2 strategy runtime args.

Workspace profile hostlists are tracked separately by ``profiles/*.json``.  A
full imported Zapret2 preset can additionally contain per-profile
``--hostlist``/``--ipset`` file arguments.  Those inputs must be validated and
copied to the public per-session input directory before privileged nfqws2 start.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


READ_ONLY_STRATEGY_FILE_OPTIONS = (
    "--hostlist",
    "--hostlist-exclude",
    "--ipset",
    "--ipset-exclude",
)


@dataclass(frozen=True)
class StrategyFileDependency:
    option: str
    value: str
    source_path: Path | None
    state: str
    message: str

    @property
    def ready(self) -> bool:
        return self.state == "ready"


def split_strategy_file_arg(arg: str) -> tuple[str, str] | None:
    for option in READ_ONLY_STRATEGY_FILE_OPTIONS:
        prefix = option + "="
        if arg.startswith(prefix):
            return option, arg[len(prefix) :].strip()
    return None


def _resolve_project_relative(root: Path, value: str) -> tuple[Path | None, str | None]:
    raw = value.lstrip("@").replace("\\", "/").strip()
    if not raw:
        return None, "пустой путь"
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        return None, "путь выходит за пределы workspace"
    resolved_root = root.resolve()
    resolved = (resolved_root / path).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return None, "путь выходит за пределы workspace"
    return resolved, None


def inspect_strategy_file_dependencies(root: Path, runtime_args: Iterable[str]) -> tuple[StrategyFileDependency, ...]:
    """Inspect unique read-only list/ipset dependencies without executing nfqws2."""

    root = root.resolve()
    result: list[StrategyFileDependency] = []
    seen: set[tuple[str, str]] = set()
    for arg in runtime_args:
        parsed = split_strategy_file_arg(str(arg))
        if parsed is None:
            continue
        option, value = parsed
        key = (option, value)
        if key in seen:
            continue
        seen.add(key)
        source, error = _resolve_project_relative(root, value)
        if error is not None:
            result.append(
                StrategyFileDependency(
                    option=option,
                    value=value,
                    source_path=None,
                    state="unsafe",
                    message=f"{option}={value}: {error}",
                )
            )
            continue
        assert source is not None
        if not source.is_file():
            result.append(
                StrategyFileDependency(
                    option=option,
                    value=value,
                    source_path=source,
                    state="missing",
                    message=f"{option}={value}: файл не найден",
                )
            )
            continue
        result.append(
            StrategyFileDependency(
                option=option,
                value=value,
                source_path=source,
                state="ready",
                message=f"{option}={value}: ready",
            )
        )
    return tuple(result)


def strategy_file_dependency_blockers(root: Path, runtime_args: Iterable[str]) -> tuple[StrategyFileDependency, ...]:
    return tuple(item for item in inspect_strategy_file_dependencies(root, runtime_args) if not item.ready)


def strategy_file_dependency_error_text(root: Path, runtime_args: Iterable[str], *, max_items: int = 8) -> str:
    blockers = strategy_file_dependency_blockers(root, runtime_args)
    if not blockers:
        return ""
    shown = [item.message for item in blockers[:max_items]]
    if len(blockers) > max_items:
        shown.append(f"… ещё {len(blockers) - max_items}")
    return (
        "strategy file dependencies не готовы: "
        + "; ".join(shown)
        + ". Импортированный TXT с внешними lists/ipset нельзя запускать, пока файлы не добавлены или не импортированы вместе с preset."
    )


__all__ = [
    "READ_ONLY_STRATEGY_FILE_OPTIONS",
    "StrategyFileDependency",
    "inspect_strategy_file_dependencies",
    "split_strategy_file_arg",
    "strategy_file_dependency_blockers",
    "strategy_file_dependency_error_text",
]
