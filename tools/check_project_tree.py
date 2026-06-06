#!/usr/bin/env python3
"""Read-only проверка структуры репозитория для v0.3-alpha."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = [
    "README.md",
    "pyproject.toml",
    "core/README.md",
    "core/zapret2/UPSTREAM_IMPORT.json",
    "core/zapret2/docs/LICENSE.txt",
    "core/zapret2/Makefile",
    "core/zapret2/nfq2/nfqws.c",
    "core/zapret2/lua/zapret-lib.lua",
    "gui/README.md",
    "gui/zap2_gui/__init__.py",
    "gui/zap2_gui/app.py",
    "docs/DEVELOPMENT_STRATEGY.md",
    "docs/DOCUMENTATION_LANGUAGE.md",
    "docs/GUI_FRAMEWORK.md",
    "docs/VERSIONING.md",
    "docs/SAFETY_AND_PRIVILEGE_BOUNDARY.md",
    "docs/reference/windows_gui_feature_digest.md",
    "docs/reference/legacy_project_digest.md",
]

PROJECT_DOCUMENTATION_PATHS = [
    "README.md",
    "core/README.md",
    "core/zapret2/UPSTREAM_IMPORT.md",
    "gui/README.md",
    "docs/DEVELOPMENT_STRATEGY.md",
    "docs/DOCUMENTATION_LANGUAGE.md",
    "docs/GUI_FRAMEWORK.md",
    "docs/PROJECT_STRUCTURE.md",
    "docs/SAFETY_AND_PRIVILEGE_BOUNDARY.md",
    "docs/SOURCE_ALIGNMENT.md",
    "docs/VERSIONING.md",
    "docs/reference/legacy_project_digest.md",
    "docs/reference/windows_gui_feature_digest.md",
]

FORBIDDEN_IMPORTED_SUFFIXES = (".o", ".a", ".exe", ".dll")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def _contains_russian_text(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    return len(CYRILLIC_RE.findall(text)) >= 80


def main() -> int:
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    if missing:
        print("Отсутствуют обязательные пути:")
        for path in missing:
            print(f" - {path}")
        return 1

    manifest_path = ROOT / "core/zapret2/UPSTREAM_IMPORT.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("upstreamName") != "bol-van/zapret2":
        print("Неожиданное upstreamName в манифесте импорта ядра")
        return 1
    if int(manifest.get("importedFileCount", 0)) <= 0:
        print("В манифесте импорта ядра нет импортированных файлов")
        return 1

    bad = [
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in (ROOT / "core/zapret2").rglob("*")
        if path.is_file() and path.name.lower().endswith(FORBIDDEN_IMPORTED_SUFFIXES)
    ]
    if bad:
        print("Неожиданные compiled/binary artifacts в импорте:")
        for path in bad:
            print(f" - {path}")
        return 1

    gui_framework_doc = (ROOT / "docs/GUI_FRAMEWORK.md").read_text(encoding="utf-8")
    strategy_doc = (ROOT / "docs/DEVELOPMENT_STRATEGY.md").read_text(encoding="utf-8")
    if "PyQt" not in gui_framework_doc or "PyQt" not in strategy_doc:
        print("Решение по PyQt GUI framework отсутствует в документации")
        return 1

    language_doc = (ROOT / "docs/DOCUMENTATION_LANGUAGE.md").read_text(encoding="utf-8")
    if "русском" not in language_doc or "проектная документация" not in language_doc:
        print("Правило русского языка документации не зафиксировано")
        return 1

    not_localized = [
        path
        for path in PROJECT_DOCUMENTATION_PATHS
        if not _contains_russian_text(ROOT / path)
    ]
    if not_localized:
        print("Активная проектная документация должна быть на русском языке:")
        for path in not_localized:
            print(f" - {path}")
        return 1

    print("Дерево v0.3-alpha OK; PyQt и русскоязычная документация зафиксированы")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
