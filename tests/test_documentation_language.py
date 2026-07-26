from __future__ import annotations

import re
from pathlib import Path

PROJECT_DOCUMENTATION_PATHS = [
    "README.md",
    "core/README.md",
    "core/zapret2/UPSTREAM_IMPORT.md",
    "gui/README.md",
    "profiles/README.md",
    "presets/README.md",
    "strategies/README.md",
    "runtime/README.md",
    "docs/DEVELOPMENT_STRATEGY.md",
    "docs/DOCUMENTATION_LANGUAGE.md",
    "docs/GUI_FRAMEWORK.md",
    "docs/GUI_SHELL.md",
    "docs/CORE_INVENTORY.md",
    "docs/CORE_BUILD_MAP.md",
    "docs/LOCAL_BUILD_ADAPTER.md",
    "docs/WORKSPACE_PROFILES.md",
    "docs/STRATEGIES.md",
    "docs/PRESET_PROFILE_ARCHITECTURE.md",
    "docs/RUNTIME_LIFECYCLE.md",
    "docs/RUNTIME_PLANS.md",
    "docs/PROJECT_STRUCTURE.md",
    "docs/SAFETY_AND_PRIVILEGE_BOUNDARY.md",
    "docs/SOURCE_ALIGNMENT.md",
    "docs/VERSIONING.md",
    "docs/SERVICE_TARGET_PRESETS.md",
    "docs/reference/legacy_project_digest.md",
    "docs/reference/windows_gui_feature_digest.md",
]

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def test_project_documentation_is_russian_language_baseline() -> None:
    root = Path(__file__).resolve().parents[1]
    not_localized = []
    for rel_path in PROJECT_DOCUMENTATION_PATHS:
        text = (root / rel_path).read_text(encoding="utf-8")
        if len(CYRILLIC_RE.findall(text)) < 80:
            not_localized.append(rel_path)

    assert not_localized == []


def test_future_documentation_language_rule_is_documented() -> None:
    root = Path(__file__).resolve().parents[1]
    language_doc = (root / "docs/DOCUMENTATION_LANGUAGE.md").read_text(encoding="utf-8")
    strategy_doc = (root / "docs/DEVELOPMENT_STRATEGY.md").read_text(encoding="utf-8")

    assert "активная проектная документация" in language_doc
    assert "русском языке" in language_doc
    assert "Правило языка документации" in strategy_doc
    assert "будущие изменения" in strategy_doc
