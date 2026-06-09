from __future__ import annotations

from pathlib import Path

from zap2_gui.adapters.gui_state import load_gui_shell_state
from zap2_gui.app import describe_project, main
from zap2_gui.models.navigation import default_navigation_sections
from zap2_gui.qt_compat import is_pyqt_available

ROOT = Path(__file__).resolve().parents[1]


def test_navigation_sections_are_fixed_for_stage_5() -> None:
    sections = default_navigation_sections()

    assert [section.key for section in sections] == [
        "overview",
        "core",
        "strategies",
        "diagnostics",
        "settings",
        "logs",
    ]
    assert [section.title for section in sections] == [
        "Обзор",
        "Ядро",
        "Стратегии",
        "Диагностика",
        "Настройки",
        "Логи",
    ]
    assert sections[1].ready_state == "inventory-backed"


def test_gui_shell_state_is_read_only_and_inventory_backed() -> None:
    state = load_gui_shell_state(ROOT)

    assert len(state.sections) == 6
    assert state.core_snapshot.vendor_file_count == 245
    assert [unit.name for unit in state.build_map.units] == ["nfqws2", "ip2net", "mdig"]
    assert state.build_map.automatic_checks_may_run_make is False


def test_text_entry_point_describes_gui_shell_without_requiring_pyqt() -> None:
    text = describe_project()

    assert "gui shell: PyQt skeleton" in text
    assert "Обзор" in text
    assert "Логи" in text


def test_main_text_mode_returns_success_without_launching_gui() -> None:
    assert main([]) == 0


def test_pyqt_availability_probe_is_boolean() -> None:
    assert isinstance(is_pyqt_available(), bool)


def test_gui_shell_documentation_lists_navigation_sections() -> None:
    doc = (ROOT / "docs/GUI_SHELL.md").read_text(encoding="utf-8")

    for title in ("Обзор", "Ядро", "Стратегии", "Диагностика", "Настройки", "Логи"):
        assert title in doc


def test_main_window_default_size_is_blockcheck_friendly() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "windows" / "main_window.py").read_text(encoding="utf-8")

    assert "self.resize(1280, 860)" in source
    assert "self.setMinimumSize(1040, 700)" in source
