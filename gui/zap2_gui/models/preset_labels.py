"""Подписи пресета в списке: откуда он, что с ним можно делать, есть ли проблемы порядка.

Только данные из metadata, без Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


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


__all__ = ["Chip", "SOURCE_KINDS", "preset_chips", "source_chip"]
