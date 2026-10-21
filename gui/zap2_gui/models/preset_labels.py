"""Подписи пресета в списке: откуда он, что с ним можно делать, есть ли проблемы порядка.

Только данные из metadata, без Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Iterable, Mapping

_OLD_BLOCKCHECK_TITLE = re.compile(r"^Blockcheck .+ / .+ #\d+$")


@dataclass(frozen=True)
class Chip:
    text: str
    tone: str  # accent | warn | error | muted
    tooltip: str = ""


SOURCE_KINDS = {
    "blockcheck-generated": ("Blockcheck", "Найден Blockcheck; только чтение — сделайте копию, чтобы править"),
    "txt-preset-import": ("импорт .txt", "Импортирован из .txt; можно править"),
    "strat-collection-port": ("strat_collection", "Портирован из strat_collection; можно править"),
}


def source_chip(source: Mapping[str, object] | None, managed: bool) -> Chip:
    source = source or {}
    kind = str(source.get("id") or "")
    if kind in SOURCE_KINDS:
        text, tooltip = SOURCE_KINDS[kind]
        return Chip(text, "muted", tooltip)
    if managed and source.get("copiedFromPresetId"):
        return Chip("копия", "muted", f"Копия {source.get('copiedFromPresetId')}; можно править")
    if managed:
        return Chip("свой", "muted", "Создан в конструкторе; можно править")
    return Chip("встроенный", "muted", "Поставляется с программой; только чтение — сделайте копию, чтобы править")


def preset_chips(
    source: Mapping[str, object] | None,
    *,
    managed: bool,
    selected: bool,
    overlap_severities: Iterable[str] = (),
) -> tuple[Chip, ...]:
    chips: list[Chip] = []
    if selected:
        chips.append(Chip("✓ выбран", "accent", "Этот пресет запускается в Default"))
    chips.append(source_chip(source, managed))
    severities = tuple(overlap_severities)
    dead = severities.count("error")
    partial = severities.count("warning")
    if dead:
        chips.append(Chip(f"✖ мёртвых профилей: {dead}", "error", "Профиль ниже никогда не сработает: его трафик забирает профиль выше"))
    elif partial:
        chips.append(Chip(f"⚠ пересечений: {partial}", "warn", "Часть трафика профиля уходит в профиль выше"))
    if (source or {}).get("missingListDependencies"):
        chips.append(Chip("нет списков", "error", "Не хватает hostlist/ipset файлов; запуск заблокирован"))
    return tuple(chips)


def desync_functions(args: Iterable[str]) -> tuple[str, ...]:
    names = []
    for arg in args:
        if arg.startswith("--lua-desync="):
            name = arg.partition("=")[2].split(":", 1)[0].strip()
            if name and name not in names:
                names.append(name)
    return tuple(names)


def blockcheck_title(service: str, functions: Iterable[str], target: str, when: datetime | None) -> str:
    """«YouTube: fake + multisplit · googlevideo.com · 21.10.2026 14:30» — понятно, что, чем и когда найдено."""

    funcs = " + ".join(functions) or "стратегия"
    parts = [f"{service}: {funcs}" if service else funcs]
    if target:
        parts.append(target)
    if when is not None:
        parts.append(when.astimezone().strftime("%d.%m.%Y %H:%M"))
    return " · ".join(parts)


def _parse_time(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def display_title(title: str, source: Mapping[str, object] | None, service_target: Mapping[str, object] | None,
                  runtime_args: Iterable[str]) -> str:
    """Читаемое название для старых пресетов Blockcheck вида «Blockcheck X / target #NN»."""

    source = source or {}
    if source.get("id") != "blockcheck-generated" or not _OLD_BLOCKCHECK_TITLE.match(title):
        return title
    service = str((service_target or {}).get("title") or "")
    return blockcheck_title(service, desync_functions(runtime_args), str(source.get("target") or ""), _parse_time(source.get("generatedAt")))


__all__ = ["Chip", "SOURCE_KINDS", "blockcheck_title", "desync_functions", "display_title", "preset_chips", "source_chip"]
