from __future__ import annotations

from pathlib import Path

from zap2_gui.theme import (
    DARK_PASTEL_STYLESHEET,
    SOFT_PASTEL_STYLESHEET,
    THEME_DARK,
    THEME_LIGHT,
    normalize_theme_name,
)

ROOT = Path(__file__).resolve().parents[1]


def test_theme_names_are_normalized_and_dark_qss_is_real() -> None:
    assert normalize_theme_name("dark") == THEME_DARK
    assert normalize_theme_name("anything-else") == THEME_LIGHT
    assert DARK_PASTEL_STYLESHEET != SOFT_PASTEL_STYLESHEET
    assert "#211e25" in DARK_PASTEL_STYLESHEET
    assert "QFrame#settingsCard" in SOFT_PASTEL_STYLESHEET


def test_groupbox_title_has_no_marker_background_and_tab_base_is_disabled() -> None:
    assert "QGroupBox::title" in SOFT_PASTEL_STYLESHEET
    assert "background: transparent" in SOFT_PASTEL_STYLESHEET
    assert "qproperty-drawBase: 0" in SOFT_PASTEL_STYLESHEET
    tunnel = (ROOT / "gui/zap2_gui/widgets/tunnel.py").read_text(encoding="utf-8")
    logs = (ROOT / "gui/zap2_gui/widgets/runtime_logs.py").read_text(encoding="utf-8")
    assert "controls_tabs.tabBar().setDrawBase(False)" in tunnel
    assert "tabs.tabBar().setDrawBase(False)" in logs


def test_settings_page_persists_and_applies_theme() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/settings.py").read_text(encoding="utf-8")
    assert "class ThemeToggle" in source
    assert 'settings.value("ui/theme", THEME_LIGHT)' in source
    assert 'settings.setValue("ui/theme", normalized)' in source
    assert "apply_application_theme(app, theme_name)" in source
    main_window = (ROOT / "gui/zap2_gui/windows/main_window.py").read_text(encoding="utf-8")
    assert "make_settings_page(self._settings)" in main_window


def test_qt_bootstrap_reads_saved_theme_before_window_creation() -> None:
    source = (ROOT / "gui/zap2_gui/qt_app.py").read_text(encoding="utf-8")
    assert 'settings.value("ui/theme", THEME_LIGHT)' in source
    assert source.index("apply_application_theme") < source.index("create_main_window(root)")


def test_blockcheck_actions_use_two_equal_columns() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/blockcheck_lab.py").read_text(encoding="utf-8")
    assert "primary_row_layout" in source
    assert "actions_layout.setColumnStretch(0, 1)" in source
    assert "actions_layout.setColumnStretch(1, 1)" in source
    assert "(build_button, 2, 1, 1, 1)" in source
    assert "(voice_profiles_button, 8, 1, 1, 1)" in source
