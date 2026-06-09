from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_blockcheck_lab_has_less_cramped_control_sizing() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "setMinimumHeight(38)" in source
    assert "form.setColumnMinimumWidth(1, 300)" in source
    assert "form_box.setMinimumHeight(0)" in source
    assert "action_button.setMinimumHeight(38)" in source
    assert "Raw log" in source


def test_phase_gated_runner_uses_human_gui_tournament_log() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "GUI tournament log" in source
    assert "raw upstream blockcheck output is written to Last log / candidate log files" in source
    assert "Найдена AVAILABLE стратегия для фазы" in source
    assert "стратегия-рекордсмен" in source
    assert "топ стратегий" in source
    assert "if not state.get(\"phase_gated_run\")" in source
