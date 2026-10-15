from __future__ import annotations

import re
from pathlib import Path


CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def _project_markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.md"):
        rel = path.relative_to(root)
        rel_text = rel.as_posix()

        if any(part.startswith(".") for part in rel.parts):
            continue

        # Vendored upstream сохраняется без локального перевода. Единственный
        # project-authored файл внутри дерева ядра проверяется отдельно.
        if rel_text.startswith("core/zapret2/") and rel_text != "core/zapret2/UPSTREAM_IMPORT.md":
            continue

        files.append(path)
    return sorted(files)


def test_all_project_authored_markdown_has_russian_explanation() -> None:
    root = Path(__file__).resolve().parents[1]
    not_localized: list[str] = []

    for path in _project_markdown_files(root):
        text = path.read_text(encoding="utf-8")
        if len(CYRILLIC_RE.findall(text)) < 80:
            not_localized.append(path.relative_to(root).as_posix())

    assert not_localized == []


def test_documentation_language_boundary_is_documented() -> None:
    root = Path(__file__).resolve().parents[1]
    language_doc = (root / "docs" / "DOCUMENTATION_LANGUAGE.md").read_text(encoding="utf-8")
    strategy_doc = (root / "docs" / "DEVELOPMENT_STRATEGY.md").read_text(encoding="utf-8")

    assert "активная проектная документация" in language_doc.lower()
    assert "русском языке" in language_doc
    assert "Правило языка документации" in strategy_doc
    assert "будущие изменения" in strategy_doc
    assert "core/zapret2" in language_doc
