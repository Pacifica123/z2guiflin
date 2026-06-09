from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_nfqws_opens_nfqueue_before_droproot() -> None:
    source = (ROOT / "core" / "zapret2" / "nfq2" / "nfqws.c").read_text(encoding="utf-8")
    marker = "Zap2 Linux runtime note (v0.3-beta)"
    assert marker in source
    marker_index = source.index(marker)
    nfq_index = source.index("if (!nfq_init(&h, &qh, &cbdata))", marker_index)
    drop_index = source.index("if (params.droproot && !droproot", marker_index)
    lua_index = source.index("if (!lua_init())", marker_index)
    assert nfq_index < drop_index < lua_index


def test_runtime_overview_uses_compact_primary_button() -> None:
    widget = (ROOT / "gui" / "zap2_gui" / "widgets" / "runtime_controls.py").read_text(encoding="utf-8")
    assert "primaryRunButton" in widget
    assert "▶" in widget
    assert "■" in widget
    assert "runtimeStatusIndicator" in widget
    assert "Диагностика и ручные шаги" in widget
    assert "QGridLayout" in widget
    assert "LineWrapMode.WidgetWidth" in widget


def test_main_window_default_width_is_blockcheck_friendly_but_bounded() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "windows" / "main_window.py").read_text(encoding="utf-8")
    assert "self.resize(1280, 860)" in source
    assert "self.setMinimumSize(1040, 700)" in source
