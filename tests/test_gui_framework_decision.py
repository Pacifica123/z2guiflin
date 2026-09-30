from __future__ import annotations

from pathlib import Path


def test_pyqt_framework_decision_is_documented() -> None:
    root = Path(__file__).resolve().parents[1]
    framework_doc = (root / "docs/history/stages/GUI_FRAMEWORK.md").read_text(encoding="utf-8")
    strategy_doc = (root / "docs/DEVELOPMENT_STRATEGY.md").read_text(encoding="utf-8")
    gui_readme = (root / "gui/README.md").read_text(encoding="utf-8")

    assert "PyQt" in framework_doc
    assert "PyQt" in strategy_doc
    assert "PyQt" in gui_readme


def test_pyqt_shell_declares_optional_gui_dependency() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert "PyQt6" in pyproject
    assert "[project.optional-dependencies]" in pyproject
    assert "zap2-gui" in pyproject
    assert "PySide" not in pyproject
