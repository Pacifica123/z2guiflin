"""Сбор кандидатов для оркестратора circular из уже имеющихся стратегий.

Источник — ``strategies/catalog.json`` и перечисленные в нём strategy JSON
(``runtimeArgs``). Результаты Blockcheck в проекте не хранятся в
структурированном виде между сессиями, поэтому здесь не используются; кандидат
из Blockcheck можно вставить вручную через конструктор профиля.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from ..models.orchestrator import CircularSwitch, OrchestratedProfile, candidates_from_args, parse_circular_log
from ..project_paths import discover_layout


@dataclass(frozen=True)
class OrchestratorCandidate:
    strategy_id: str
    title: str
    instances: tuple[str, ...]
    payload: str = ""


def _profiles(args: Iterable[str]) -> tuple[tuple[str, ...], ...]:
    profiles: list[list[str]] = [[]]
    for arg in args:
        if arg == "--new" or str(arg).startswith("--new="):
            profiles.append([])
            continue
        profiles[-1].append(str(arg))
    return tuple(tuple(item) for item in profiles)


def list_orchestrator_candidates(root: Path | None = None) -> tuple[OrchestratorCandidate, ...]:
    base = discover_layout(root).root
    catalog = json.loads((base / "strategies" / "catalog.json").read_text(encoding="utf-8"))
    result: list[OrchestratorCandidate] = []
    for rel in catalog.get("strategyFiles", []):
        path = base / rel
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("orchestrator"):
            continue
        profiles = _profiles(data.get("runtimeArgs", ()))
        for number, profile_args in enumerate(profiles, start=1):
            candidate = _candidate(data, path, profile_args, number if len(profiles) > 1 else 0)
            if candidate is not None:
                result.append(candidate)
    return tuple(result)


def _candidate(data: dict, path: Path, profile_args: tuple[str, ...], number: int) -> OrchestratorCandidate | None:
    payloads = {arg.partition("=")[2] for arg in profile_args if arg.startswith("--payload=")}
    # Разные --payload внутри профиля нельзя честно переложить в один
    # кандидат circular без изменения смысла — такие стратегии пропускаем.
    if len(payloads) > 1:
        return None
    instances = candidates_from_args(profile_args)
    if not instances:
        return None
    strategy_id = str(data.get("id", path.stem))
    title = str(data.get("title", path.stem))
    if number:
        strategy_id = f"{strategy_id}#{number}"
        title = f"{title} / профиль {number}"
    return OrchestratorCandidate(strategy_id, title, instances, next(iter(payloads), ""))


def build_orchestrated_profile(
    strategy_ids: Iterable[str],
    *,
    root: Path | None = None,
    params: dict[str, str | int | bool] | None = None,
    final_last: bool = False,
    payload: str = "",
) -> OrchestratedProfile:
    available = {item.strategy_id: item for item in list_orchestrator_candidates(root)}
    chosen = []
    payloads = set()
    for strategy_id in strategy_ids:
        if strategy_id not in available:
            raise ValueError(f"Стратегия {strategy_id!r} не найдена или не годится в кандидаты circular")
        chosen.append(available[strategy_id].instances)
        payloads.add(available[strategy_id].payload)
    if len(payloads) > 1:
        raise ValueError("Кандидаты circular используют разные --payload; выберите стратегии с одинаковым payload")
    profile = OrchestratedProfile(tuple(chosen), dict(params or {}), final_last, payload or next(iter(payloads), ""))
    profile.validate()
    return profile


def circular_switches_from_log(path: Path, max_lines: int = 20000) -> tuple[CircularSwitch, ...]:
    """Для виджета runtime-логов: переключения circular из debug-лога nfqws2."""

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ()
    return parse_circular_log(lines[-max_lines:])
