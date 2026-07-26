from __future__ import annotations

import json
import shutil
from pathlib import Path

from zap2_gui.adapters.presets import (
    load_preset_catalog,
    preset_profile_to_text,
    preset_to_text,
)
from zap2_gui.adapters.workspace_profiles import load_workspace_catalog
from zap2_gui.app import describe_project, main
from zap2_gui.models.preset import parse_preset_args
from zap2_gui.models.workspace_profile import WorkspaceProfile, WorkspaceRuntimeContext

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_workspace_profile_name_is_only_an_alias() -> None:
    assert WorkspaceProfile is WorkspaceRuntimeContext


def test_every_catalog_strategy_has_a_canonical_preset_file() -> None:
    strategy_catalog = load_workspace_catalog(ROOT)
    for strategy in strategy_catalog.strategies:
        assert strategy.preset_path.startswith("presets/")
        assert (ROOT / strategy.preset_path).is_file()


def test_preset_round_trip_keeps_runtime_argv_exactly() -> None:
    strategy_catalog = load_workspace_catalog(ROOT)
    for strategy in strategy_catalog.strategies:
        preset = parse_preset_args(
            strategy.runtime_args,
            preset_id=strategy.strategy_id,
            title=strategy.title,
            source_path=strategy.preset_path,
        )
        assert preset.to_runtime_args() == strategy.runtime_args


def test_community_preset_is_split_into_ordered_profiles() -> None:
    catalog = load_preset_catalog(ROOT)
    preset = catalog.by_id()["community-discord-youtube-edge-flow"].preset

    assert len(preset.global_args) == 7
    assert len(preset.profiles) == 6
    assert [profile.index for profile in preset.profiles] == list(range(6))
    assert preset.profiles[0].name == "Edge / начало соединения"
    assert preset.profiles[0].strategy_label == "wssize + syndata"
    assert preset.profiles[0].traffic_filter.tcp == ("443",)
    assert preset.profiles[0].range_label == "in=x; out=-s1"
    assert preset.profiles[0].direction_label == "out"
    assert preset.profiles[-1].name == "QUIC / UDP 443"
    assert preset.profiles[-1].traffic_filter.udp == ("443",)


def test_profile_actions_keep_effective_range_and_payload() -> None:
    preset = load_preset_catalog(ROOT).by_id()["manual-local"].preset
    profile = preset.profiles[0]

    assert [action.function_name for action in profile.actions] == ["fake", "fake", "multisplit"]
    assert [action.payload for action in profile.actions] == [
        "tls_client_hello",
        "http_req",
        "tls_client_hello,http_req",
    ]
    assert all(action.in_range == "x" for action in profile.actions)
    assert all(action.out_range == "a" for action in profile.actions)


def test_preset_cli_exposes_catalog_and_profile_details(capsys) -> None:
    assert main(["--list-presets"]) == 0
    assert "Zapret2 presets:" in capsys.readouterr().out

    assert main(["--show-preset", "community-discord-youtube-edge-flow"]) == 0
    preset_text = capsys.readouterr().out
    assert "profile order: first match wins" in preset_text
    assert "Edge / начало соединения" in preset_text

    assert main(["--show-preset-profile", "community-discord-youtube-edge-flow", "1"]) == 0
    profile_text = capsys.readouterr().out
    assert "strategy: wssize + syndata" in profile_text
    assert "direction: out" in profile_text


def test_preset_text_formatters_are_read_only() -> None:
    text = preset_to_text("manual-local", ROOT)
    profile = preset_profile_to_text("manual-local", "1", ROOT)

    assert "profiles: 1" in text
    assert "filter: TCP 80,443" in profile
    assert "raw args:" in profile


def test_gui_source_uses_preset_and_profile_catalog() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/presets.py").read_text(encoding="utf-8")

    assert "QListWidget" in source
    assert "QTableWidget" in source
    assert '"Профиль", "Фильтр", "Стратегия", "Range", "Direction"' in source
    assert "Выбрать пресет" in source
    assert "select_preset" in source


def test_project_description_uses_unambiguous_terms() -> None:
    text = describe_project()
    assert "workspace contexts: 1" in text
    assert "presets: 15" in text
    assert "traffic profiles: 61" in text


def test_strategy_json_shadow_matches_preset_file() -> None:
    catalog = json.loads((ROOT / "strategies/catalog.json").read_text(encoding="utf-8"))
    for rel in catalog["strategyFiles"]:
        data = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        args = tuple(
            line.strip()
            for line in (ROOT / data["presetPath"]).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        assert args == tuple(data.get("runtimeArgs", []))


def test_generated_strategy_export_contract_mentions_preset_path() -> None:
    source = (ROOT / "gui/zap2_gui/adapters/blockcheck_gui.py").read_text(encoding="utf-8")
    assert '"presetPath": preset_path' in source
    assert 'layout.root / "presets" / "generated"' in source
