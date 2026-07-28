from __future__ import annotations

from pathlib import Path

from zap2_gui.theme import SOFT_PASTEL_STYLESHEET

ROOT = Path(__file__).resolve().parents[1]


def test_groupbox_titles_and_tab_panes_are_softened() -> None:
    assert "QGroupBox::title" in SOFT_PASTEL_STYLESHEET
    assert "background: #faf8fb" in SOFT_PASTEL_STYLESHEET
    assert "QTabWidget::pane" in SOFT_PASTEL_STYLESHEET
    assert "border: 0;" in SOFT_PASTEL_STYLESHEET


def test_spinboxes_have_explicit_button_styling() -> None:
    assert "QAbstractSpinBox::up-button" in SOFT_PASTEL_STYLESHEET
    assert "QAbstractSpinBox::down-button" in SOFT_PASTEL_STYLESHEET
    assert "padding-right: 22px" in SOFT_PASTEL_STYLESHEET


def test_overview_table_actions_are_above_table_and_launch_issue_clears_on_input_change() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/runtime_controls.py").read_text(encoding="utf-8")
    assert source.index("overview_table_layout.addLayout(table_actions)") < source.index("overview_table_layout.addWidget(overview_table)")
    assert "def clear_launch_issue_on_input_change()" in source
    assert "vless_check.toggled.connect" in source
    assert "core_input.textChanged.connect" in source


def test_blockcheck_action_buttons_can_expand_for_long_labels() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/blockcheck_lab.py").read_text(encoding="utf-8")
    assert "action_button.setMaximumWidth(220)" in source
    assert "QSizePolicy.Policy.Expanding" in source
