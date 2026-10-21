from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from zap2_gui.adapters import preset_hot_swap
from zap2_gui.adapters.gui_privilege import GuiPrivilegedCommand, GuiPrivilegedResult
from zap2_gui.adapters.strat_collection import load_strat_collection
from zap2_gui.adapters.strat_collection_port import analyze_strat_port
from zap2_gui.theme_profiles import DARK_COLORS, theme_profile_from_dict, custom_stylesheet

ROOT = Path(__file__).resolve().parents[1]


def test_gui_privileged_result_keeps_success_alias_for_gui_adapters() -> None:
    command = GuiPrivilegedCommand("stop", "default", "plan", ("true",), ROOT)
    result = GuiPrivilegedResult("stop", "default", "plan", 0, "", "", command)
    assert result.ok is True
    assert result.success is True


def test_hot_swap_run_uses_gui_privileged_ok_contract(monkeypatch) -> None:
    monkeypatch.setattr(preset_hot_swap, "prepare_default_workflow_plan", lambda **_kw: SimpleNamespace(plan_id="p"))
    monkeypatch.setattr(preset_hot_swap, "confirm_runtime_plan", lambda **_kw: None)

    class ResultWithOnlyOk:
        ok = True
        def to_text(self) -> str:
            return "done"

    monkeypatch.setattr(preset_hot_swap, "execute_gui_privileged_workflow", lambda **_kw: ResultWithOnlyOk())
    ok, text = preset_hot_swap._run(ROOT, "stop", "default")
    assert ok is True
    assert text == "done"


def test_strat_port_is_conservative_and_uses_documented_zapret2_shapes() -> None:
    catalog = load_strat_collection(ROOT)
    by_id = {entry.entry_id: entry for entry in catalog.entries}

    v2 = analyze_strat_port(by_id["original_bolvan_2"], ROOT)
    assert v2.can_port
    assert not any(arg.startswith("--wf-") for arg in v2.runtime_args)
    assert not any(arg.startswith("--dpi-desync") for arg in v2.runtime_args)
    assert "--filter-l7=http" in v2.runtime_args
    assert "--payload=http_req" in v2.runtime_args
    assert any("fake_default_http" in arg for arg in v2.runtime_args)
    assert any("ip6_autottl=-2,3-20" in arg for arg in v2.runtime_args)
    multidisorder = [arg for arg in v2.runtime_args if "multidisorder_legacy" in arg]
    assert multidisorder
    assert all("repeats=" not in arg and "tcp_md5" not in arg and "tcp_seq=" not in arg for arg in multidisorder)

    # v1 has an any-protocol Discord UDP fake without an explicit payload/blob:
    # nfqws1 sends its documented default (64 zero bytes), and the port says so.
    v1 = analyze_strat_port(by_id["original_bolvan"], ROOT)
    assert v1.can_port
    assert any("blob=0x" + "00" * 64 in arg for arg in v1.runtime_args)
    assert any("64 нулевых байта" in item for item in v1.adaptations)

    # Legacy split2 is an nfqws1 alias of multisplit.
    split2 = analyze_strat_port(by_id["bolvan3"], ROOT)
    assert any("split2 → multisplit" in item for item in split2.adaptations)


def test_theme_backward_compat_fills_new_notice_and_status_colors() -> None:
    profile = theme_profile_from_dict({
        "schemaVersion": 1,
        "name": "old stage8j theme",
        "base": "dark",
        "colors": {"accent": "#123456"},
    })
    assert profile.colors["accent"] == "#123456"
    for key in ("noticeBg", "noticeBorder", "noticeText", "statusRunning", "statusStopped", "statusWarning", "statusUnknown"):
        assert profile.colors[key] == DARK_COLORS[key]

    qss = custom_stylesheet(profile)
    assert "QFrame#launchIssueBanner" in qss
    assert "QLabel#runtimeStatusIndicator" in qss
    assert "background:transparent; border:0" in qss
    assert "QPushButton#primaryRunButton" in qss


def test_presets_ui_preserves_selection_and_dispatches_contextual_apply() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/presets.py").read_text(encoding="utf-8")
    assert source.index("previous_current = _current_preset_id()") < source.index("preset_list.clear()")
    assert '"strat_selected_id": ""' in source
    assert "desired_id = str(state.get(\"strat_selected_id\") or \"\")" in source
    assert 'select_button.setText("Портировать + применить")' in source
    assert 'select_button.setText("Автопорт недоступен")' in source
    assert "apply_current_selection" in source
    assert "port_strat_collection_entry" in source


def test_overview_refreshes_on_navigation_and_runtime_indicator_is_flat() -> None:
    runtime = (ROOT / "gui/zap2_gui/widgets/runtime_controls.py").read_text(encoding="utf-8")
    main = (ROOT / "gui/zap2_gui/windows/main_window.py").read_text(encoding="utf-8")
    assert "page.refresh_runtime_state = refresh_visual_state" in runtime
    assert 'getattr(page, "refresh_runtime_state", None)' in main
    assert "background: transparent;" in runtime
    assert "tinted_misc_icon" in runtime
    assert 'current_theme.colors["accent"]' in runtime
