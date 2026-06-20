from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_stage7g_blockcheck_lab_has_endpoint_button_and_centered_layout() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "widgets" / "blockcheck_lab.py").read_text(encoding="utf-8")

    assert "Endpoints" in source
    assert "discord_endpoint_discovery_plan_to_text" in source
    assert "discord_endpoint_report_to_text" in source
    assert "QScrollArea" in source
    assert "blockcheckLabScrollArea" in source
    assert "form_box.setMinimumWidth(BLOCKCHECK_LAB_SECTION_MIN_WIDTH)" in source
    assert "output.setMinimumWidth(BLOCKCHECK_LAB_SECTION_MIN_WIDTH)" in source
    assert "target_preset_hint.setMinimumHeight(42)" in source


def test_stage7g_main_window_is_roomier_again() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "windows" / "main_window.py").read_text(encoding="utf-8")

    assert "self.resize(1240, 840)" in source
    assert "self.setMinimumSize(960, 680)" in source
