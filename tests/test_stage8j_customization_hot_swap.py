from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path

from zap2_gui.adapters import preset_hot_swap
from zap2_gui.adapters.strat_collection import load_strat_collection
from zap2_gui.theme import THEME_DARK
from zap2_gui.theme_profiles import ThemeProfile, load_theme_profile, save_theme_profile, theme_profile_from_dict

ROOT = Path(__file__).resolve().parents[1]


def _status(session_state: str):
    @dataclass
    class Session:
        state: str
    @dataclass
    class Status:
        session_status: Session
    return Status(Session(session_state))


def test_hot_swap_running_orders_stop_select_start(monkeypatch) -> None:
    events: list[str] = []

    class Catalog:
        selected_preset_id = "old"
        def by_id(self): return {"old": object(), "new": object()}

    statuses = iter((_status("running"), _status("not-started"), _status("running")))
    monkeypatch.setattr(preset_hot_swap, "load_preset_catalog", lambda _root: Catalog())
    monkeypatch.setattr(preset_hot_swap, "default_workflow_status", lambda **_kw: next(statuses))
    monkeypatch.setattr(preset_hot_swap, "select_preset", lambda preset_id, **_kw: events.append(f"select:{preset_id}"))
    monkeypatch.setattr(preset_hot_swap, "_run", lambda _root, action, _profile: (events.append(action) or True, action))

    result = preset_hot_swap.hot_swap_preset("new", ROOT)
    assert result.success
    assert result.state == "switched"
    assert events == ["stop", "select:new", "start"]


def test_hot_swap_failed_start_restores_old_selection_and_runtime(monkeypatch) -> None:
    events: list[str] = []

    class Catalog:
        selected_preset_id = "old"
        def by_id(self): return {"old": object(), "new": object()}

    statuses = iter((_status("running"), _status("not-started"), _status("not-started"), _status("running")))
    runs = iter(((True, "stop ok"), (False, "new start failed"), (True, "old start ok")))
    monkeypatch.setattr(preset_hot_swap, "load_preset_catalog", lambda _root: Catalog())
    monkeypatch.setattr(preset_hot_swap, "default_workflow_status", lambda **_kw: next(statuses))
    monkeypatch.setattr(preset_hot_swap, "select_preset", lambda preset_id, **_kw: events.append(f"select:{preset_id}"))
    monkeypatch.setattr(preset_hot_swap, "_run", lambda _root, action, _profile: (events.append(action) or next(runs)))

    result = preset_hot_swap.hot_swap_preset("new", ROOT)
    assert result.state == "start-failed-rolled-back"
    assert result.selected_preset_id == "old"
    assert events == ["stop", "select:new", "start", "select:old", "start"]


def test_theme_profile_json_roundtrip_and_validation(tmp_path: Path) -> None:
    profile = ThemeProfile(
        name="Grey custom",
        base=THEME_DARK,
        colors={"accent": "#123456", "window": "#101010"},
        font_family="Noto Sans",
        font_size_pt=12,
        corner_radius_px=4,
        navigation_width_px=250,
    ).normalized()
    target = tmp_path / "theme.json"
    save_theme_profile(target, profile)
    loaded = load_theme_profile(target)
    assert loaded.name == "Grey custom"
    assert loaded.colors["accent"] == "#123456"
    assert loaded.navigation_width_px == 250
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["schemaVersion"] == 1
    assert data["metrics"]["cornerRadiusPx"] == 4

    bad = dict(data)
    bad["colors"] = {"accent": "red"}
    try:
        theme_profile_from_dict(bad)
    except ValueError as exc:
        assert "#RRGGBB" in str(exc)
    else:
        raise AssertionError("invalid color must be rejected")


def test_bundled_strat_collection_is_indexed_without_execution() -> None:
    catalog = load_strat_collection(ROOT)
    assert len(catalog.entries) == 55
    assert all(entry.compatibility == "legacy zapret1 / reference-only" for entry in catalog.entries)
    assert all(entry.source_path.is_file() for entry in catalog.entries)
    discord = catalog.search("discord")
    assert discord
    assert any(entry.desync_modes for entry in discord)
    assert all(arg.startswith("--") for entry in catalog.entries for arg in entry.winws_args)


def test_presets_ui_has_loop_uh_style_search_and_one_click_apply() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/presets.py").read_text(encoding="utf-8")
    assert 'QtGui.QKeySequence("Ctrl+F")' in source
    assert "preset_list.itemClicked.connect(one_click_apply)" in source
    assert "hot_swap_preset(" in source
    assert 'tabs.addTab(collection_tab, "strat_collection")' in source
    assert "BAT/winws никогда не исполняются" in source


def test_settings_ui_exports_theme_and_controls_hot_swap() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/settings.py").read_text(encoding="utf-8")
    assert "Экспорт темы…" in source
    assert "Импорт темы…" in source
    assert 'settings.value("presets/one-click-apply",True,type=bool)' in source
    assert "navigationRail" in source
