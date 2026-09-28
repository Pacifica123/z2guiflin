from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_nfqws_privilege_order_is_explicit_p03_source_transform() -> None:
    upstream = (ROOT / "core" / "zapret2" / "nfq2" / "nfqws.c").read_text(encoding="utf-8")
    effective = (ROOT / "core" / "overlays" / "zapret2" / "source" / "nfq2" / "nfqws.c").read_text(encoding="utf-8")

    # Exact candidate remains byte-exact at rest and reproduces the regression trigger.
    assert upstream.index("if (params.droproot && !droproot") < upstream.index("if (!nfq_init(&h, &qh, &cbdata))")

    marker = "Zap2 source transform P03"
    assert marker in effective
    marker_index = effective.index(marker)
    nfq_index = effective.index("if (!nfq_init(&h, &qh, &cbdata))", marker_index)
    drop_index = effective.index("if (params.droproot && !droproot", marker_index)
    lua_index = effective.index("if (!lua_init())", marker_index)
    assert nfq_index < drop_index < lua_index


def test_runtime_overview_uses_compact_primary_button() -> None:
    widget = (ROOT / "gui" / "zap2_gui" / "widgets" / "runtime_controls.py").read_text(encoding="utf-8")
    assert "primaryRunButton" in widget
    assert 'misc_icon("toggle-start")' in widget
    assert 'misc_icon("toggle-stop")' in widget
    assert "runtimeStatusIndicator" in widget
    assert "Developer mode: ручные детали Default workflow" in widget
    assert "QGridLayout" in widget
    assert "setWordWrap(True)" in widget


def test_main_window_default_width_is_blockcheck_friendly_but_bounded() -> None:
    source = (ROOT / "gui" / "zap2_gui" / "windows" / "main_window.py").read_text(encoding="utf-8")
    assert "self.resize(1240, 840)" in source
    assert "self.setMinimumSize(960, 680)" in source
