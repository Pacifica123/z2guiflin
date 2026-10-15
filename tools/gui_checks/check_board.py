#!/usr/bin/env python3
"""Проверка целостности board/board.json (формат p2p_planner_bundle). Только stdlib; exit 0/1."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "board" / "board.json"


def check(path: Path = BOARD) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"не читается как JSON: {exc}"]
    manifest = data.get("manifest.json") or {}
    if manifest.get("format") != "p2p_planner_bundle":
        errors.append("manifest.json.format != p2p_planner_bundle")
    if manifest.get("formatVersion") != 1:
        errors.append("manifest.json.formatVersion != 1")
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return errors + ["нет payload"]

    def items(key: str) -> list[dict]:
        value = payload.get(key, [])
        return value if isinstance(value, list) else []

    seen: set[str] = set()
    for key, value in payload.items():
        for item in value if isinstance(value, list) else []:
            iid = item.get("id") if isinstance(item, dict) else None
            if iid is None:
                continue
            if iid in seen:
                errors.append(f"повторяющийся id {iid} ({key})")
            seen.add(iid)

    boards = {b["id"] for b in items("boards")}
    columns = {c["id"]: c for c in items("columns")}
    cards = {c["id"] for c in items("cards")}
    labels = {l["id"] for l in items("labels")}
    checklists = {c["id"] for c in items("checklists")}
    for col in columns.values():
        if col.get("boardId") not in boards:
            errors.append(f"колонка {col['id']}: неизвестная доска")
    for card in items("cards"):
        if card.get("columnId") not in columns:
            errors.append(f"карточка {card['id']}: неизвестная колонка {card.get('columnId')}")
        if card.get("boardId") not in boards:
            errors.append(f"карточка {card['id']}: неизвестная доска")
    for link in items("cardLabels"):
        if link.get("cardId") not in cards or link.get("labelId") not in labels:
            errors.append(f"cardLabels: битая ссылка {link}")
    for key in ("checklists", "comments"):
        for item in items(key):
            if item.get("cardId") not in cards:
                errors.append(f"{key} {item.get('id')}: неизвестная карточка")
    for item in items("checklistItems"):
        if item.get("checklistId") not in checklists:
            errors.append(f"checklistItems {item.get('id')}: неизвестный чеклист")

    counts = (manifest.get("summary") or {}).get("entityCounts") or {}
    for key, expected in counts.items():
        actual = len(items(key))
        if key in payload and actual != expected:
            errors.append(f"entityCounts.{key}={expected}, в payload {actual}")
        if key not in payload and expected:
            errors.append(f"entityCounts.{key}={expected}, в payload секции нет")

    for col in columns.values():
        limit = col.get("wipLimit")
        if isinstance(limit, int) and limit > 0:
            n = sum(1 for c in items("cards") if c.get("columnId") == col["id"] and not c.get("archivedAt"))
            if n > limit:
                errors.append(f"колонка «{col.get('name')}»: {n} карточек при WIP-лимите {limit}")
    return errors


def main() -> int:
    errors = check()
    if errors:
        print("board/board.json: ошибки:")
        for err in errors:
            print(f" - {err}")
        return 1
    print("board/board.json: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
