from __future__ import annotations

from pathlib import Path

from zap2_gui.theme import SOFT_PASTEL_STYLESHEET

ROOT = Path(__file__).resolve().parents[1]


def test_theme_detaches_fusion_widgets_from_desktop_dark_palette() -> None:
    source = (ROOT / "gui/zap2_gui/theme.py").read_text(encoding="utf-8")
    assert "from PyQt6 import QtGui" in source
    assert "app.setPalette(palette)" in source
    assert source.index("_apply_light_palette(app)") < source.index("app.setStyleSheet")
    assert 'ColorRole.Base: "#fffefe"' in source
    assert 'ColorRole.Highlight: "#d9cbe1"' in source


def test_item_views_have_explicit_light_background_and_selection() -> None:
    assert "QTableView, QTreeView, QListView" in SOFT_PASTEL_STYLESHEET
    assert "background: #fffefe" in SOFT_PASTEL_STYLESHEET
    assert "selection-background-color: #d9cbe1" in SOFT_PASTEL_STYLESHEET
    assert "QTableView::viewport" in SOFT_PASTEL_STYLESHEET
    assert "QComboBox QAbstractItemView" in SOFT_PASTEL_STYLESHEET


def test_blockcheck_local_style_no_longer_assumes_dark_theme() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/blockcheck_lab.py").read_text(encoding="utf-8")
    assert "rgba(220, 220, 220" not in source
    assert "color: #756d7b" in source
    assert "(tournament_button, 3, 2, 1, 2)" in source
    assert "(endpoint_button, 4, 2, 1, 2)" in source


def test_runtime_status_colors_are_stable_hex_values() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/runtime_controls.py").read_text(encoding="utf-8")
    for value in ("#dcefe3", "#f2e8d8", "#f4ded9", "#f6edd7"):
        assert value in source
