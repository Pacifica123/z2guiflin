from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase_gated_runner_has_check_budget_auto_stop() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "Alt check cap" in source
    assert "phase_budget_spin.setValue(160)" in source
    assert "should_budget_stop_phase_alternative" in source
    assert "phase-alternative-check-cap" in source
    assert "Alternative достигла лимита проверок без AVAILABLE" in source


def test_blockcheck_lab_layout_is_less_edge_stretched() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "target_preset_combo.setMaximumWidth(860)" in source
    assert "domains_edit.setMaximumWidth(860)" in source
    assert "scan_mode_combo.setMaximumWidth(860)" in source
    assert "target_preset_hint.setMinimumHeight(30)" in source
    assert "target_preset_hint.setMaximumHeight(50)" in source


def test_main_window_stage7f_size_is_roomier() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "windows" / "main_window.py").read_text(encoding="utf-8")

    assert "self.resize(1240, 840)" in source
    assert "self.setMinimumSize(960, 680)" in source
