from __future__ import annotations

from pathlib import Path


def test_pyqt_framework_decision_is_documented() -> None:
    root = Path(__file__).resolve().parents[1]
    framework_doc = (root / "docs/GUI_FRAMEWORK.md").read_text(encoding="utf-8")
    strategy_doc = (root / "docs/DEVELOPMENT_STRATEGY.md").read_text(encoding="utf-8")
    gui_readme = (root / "gui/README.md").read_text(encoding="utf-8")

    assert "PyQt" in framework_doc
    assert "PyQt" in strategy_doc
    assert "PyQt" in gui_readme


def test_pyqt_decision_does_not_add_runtime_dependency_yet() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert "PyQt" not in pyproject
    assert "PySide" not in pyproject
