from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_blockcheck_lab_has_more_compact_two_pane_control_sizing() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "target_preset_combo.setMinimumHeight(32)" in source
    assert "domains_edit.setMinimumHeight(32)" in source
    assert "form.setContentsMargins(10, 14, 10, 10)" in source
    assert "form.setColumnMinimumWidth(1, 128)" in source
    assert "form_box.setMinimumHeight(0)" in source
    assert "form_box.setMaximumHeight(390)" in source
    assert "QtWidgets.QSizePolicy.Policy.Maximum" in source
    assert "body_layout.addWidget(form_box, 3, QtCore.Qt.AlignmentFlag.AlignTop)" in source
    assert "action_button.setMinimumHeight(30)" in source
    assert "compact_combo.setMinimumHeight(28)" in source
    assert "body_layout = QtWidgets.QHBoxLayout(body)" in source
    assert "Raw log" in source


def test_phase_gated_runner_uses_human_gui_tournament_log() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "GUI tournament log" in source
    assert "raw upstream blockcheck output is written to Last log / candidate log files" in source
    assert "Найдена AVAILABLE стратегия для фазы" in source
    assert "стратегия-рекордсмен" in source
    assert "топ стратегий" in source
    assert "if not state.get(\"phase_gated_run\")" in source
