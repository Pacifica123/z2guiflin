from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from zap2_gui.adapters.preset_editor import (
    EditableTrafficProfile,
    PRESET_PROTOCOL_ANY,
    PRESET_PROTOCOL_TCP,
    PRESET_PROTOCOL_UDP,
    PRESET_TARGET_DOMAINS,
    PRESET_TARGET_NONE,
    add_owner_preset_profile,
    create_owner_preset,
    editable_profile_from_runtime,
    is_preset_editor_managed,
    list_profile_strategy_templates,
    move_owner_preset_profile,
    parse_manual_strategy_text,
    remove_owner_preset,
    remove_owner_preset_profile,
    split_blockcheck_profile_args,
    update_owner_preset_profile,
)
from zap2_gui.adapters.presets import load_preset, load_preset_catalog, select_preset

ROOT = Path(__file__).resolve().parents[1]


def _project_copy(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )
    return target


def _youtube_profile(name: str = "YouTube QUIC") -> EditableTrafficProfile:
    return EditableTrafficProfile(
        name=name,
        protocol=PRESET_PROTOCOL_UDP,
        ports="443",
        l7="quic",
        target_kind=PRESET_TARGET_DOMAINS,
        target_value="youtube.com www.youtube.com",
        strategy_args=(
            "--payload=quic_initial",
            "--lua-desync=fake:blob=quic_initial:repeats=6",
        ),
    )


def _discord_voice_profile(name: str = "Discord Voice") -> EditableTrafficProfile:
    return EditableTrafficProfile(
        name=name,
        protocol=PRESET_PROTOCOL_UDP,
        ports="50000-65535",
        l7="stun,discord",
        target_kind=PRESET_TARGET_NONE,
        target_value="",
        strategy_args=(
            "--payload=unknown_udp",
            "--lua-desync=fake:blob=unknown_udp:repeats=2",
        ),
    )


def test_cyrillic_title_gets_stable_readable_preset_id(tmp_path: Path) -> None:
    root = _project_copy(tmp_path)

    result = create_owner_preset("Универсальный Ростелеком", root=root)

    assert result.preset_id == "universalnyy-rostelekom"


def test_create_owner_preset_writes_canonical_files_and_catalog(tmp_path: Path) -> None:
    root = _project_copy(tmp_path)

    result = create_owner_preset(
        "Universal Rostelecom YT+DS",
        root=root,
        preset_id="universal-rostelecom-yt-ds",
    )

    assert result.profile_count == 0
    assert result.preset_path == root / "presets/workspace/universal-rostelecom-yt-ds.txt"
    assert result.metadata_path == root / "strategies/workspace/universal-rostelecom-yt-ds.json"
    assert result.preset_path.is_file()
    assert result.metadata_path.is_file()
    assert is_preset_editor_managed(result.preset_id, root)

    entry = load_preset(result.preset_id, root)
    assert entry.preset.to_runtime_args() == (
        "--lua-init=@core/zapret2/lua/zapret-lib.lua",
        "--lua-init=@core/zapret2/lua/zapret-antidpi.lua",
    )
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert tuple(metadata["runtimeArgs"]) == entry.preset.to_runtime_args()
    assert metadata["sourcePreset"]["editorManaged"] is True

    catalog = json.loads((root / "strategies/catalog.json").read_text(encoding="utf-8"))
    assert "strategies/workspace/universal-rostelecom-yt-ds.json" in catalog["strategyFiles"]


def test_add_move_update_and_remove_profiles_preserves_first_match_order(tmp_path: Path) -> None:
    root = _project_copy(tmp_path)
    preset_id = create_owner_preset("Ordered preset", root=root, preset_id="ordered-preset").preset_id

    add_owner_preset_profile(preset_id, _youtube_profile(), root=root)
    add_owner_preset_profile(preset_id, _discord_voice_profile(), root=root)
    entry = load_preset(preset_id, root)
    assert [item.name for item in entry.preset.profiles] == ["YouTube QUIC", "Discord Voice"]

    move_owner_preset_profile(preset_id, 1, 0, root=root)
    entry = load_preset(preset_id, root)
    assert [item.name for item in entry.preset.profiles] == ["Discord Voice", "YouTube QUIC"]
    assert entry.preset.to_runtime_args().index("--name=Discord Voice") < entry.preset.to_runtime_args().index(
        "--name=YouTube QUIC"
    )

    updated = _discord_voice_profile("Discord Voice UDP")
    update_owner_preset_profile(preset_id, 0, updated, root=root)
    entry = load_preset(preset_id, root)
    assert entry.preset.profiles[0].name == "Discord Voice UDP"
    editable = editable_profile_from_runtime(entry.preset.profiles[0])
    assert editable.protocol == PRESET_PROTOCOL_UDP
    assert editable.ports == "50000-65535"
    assert editable.l7 == "stun,discord"

    remove_owner_preset_profile(preset_id, 1, root=root)
    entry = load_preset(preset_id, root)
    assert [item.name for item in entry.preset.profiles] == ["Discord Voice UDP"]
    assert "--new" not in entry.preset.to_runtime_args()


def test_reference_preset_is_read_only_for_constructor(tmp_path: Path) -> None:
    root = _project_copy(tmp_path)

    with pytest.raises(ValueError, match="не создан конструктором"):
        add_owner_preset_profile("manual-local", _youtube_profile(), root=root)


def test_manual_strategy_accepts_actions_but_rejects_filter_and_global_layers() -> None:
    parsed = parse_manual_strategy_text(
        """
        # profile action only
        --payload=tls_client_hello
        --lua-desync=multidisorder:pos=1,midsld
        """
    )
    assert parsed == (
        "--payload=tls_client_hello",
        "--lua-desync=multidisorder:pos=1,midsld",
    )

    for forbidden in (
        "--filter-tcp=443",
        "--hostlist-domains=discord.com",
        "--lua-init=@core/zapret2/lua/zapret-lib.lua",
        "--new",
    ):
        with pytest.raises(ValueError, match="preset/global/filter"):
            parse_manual_strategy_text(f"{forbidden}\n--lua-desync=multisplit:pos=1")


def test_blockcheck_candidate_is_split_before_profile_import() -> None:
    filters, strategy = split_blockcheck_profile_args(
        (
            "--lua-init=@core/zapret2/lua/zapret-lib.lua",
            "--filter-tcp=443",
            "--filter-l7=tls",
            "--hostlist-domains=youtube.com",
            "--payload=tls_client_hello",
            "--lua-desync=multidisorder:pos=1,midsld",
        )
    )

    assert filters == (
        "--filter-tcp=443",
        "--filter-l7=tls",
        "--hostlist-domains=youtube.com",
    )
    assert strategy == (
        "--payload=tls_client_hello",
        "--lua-desync=multidisorder:pos=1,midsld",
    )


def test_blockcheck_candidate_accepts_both_standard_lua_imports() -> None:
    filters, strategy = split_blockcheck_profile_args(
        (
            "--lua-init=@core/zapret2/lua/zapret-lib.lua",
            "--lua-init=@core/zapret2/lua/zapret-antidpi.lua",
            "--filter-udp=443",
            "--filter-l7=quic",
            "--payload=quic_initial",
            "--lua-desync=fake:blob=fake_default_quic:repeats=1",
        )
    )

    assert filters == ("--filter-udp=443", "--filter-l7=quic")
    assert strategy[-1] == "--lua-desync=fake:blob=fake_default_quic:repeats=1"


@pytest.mark.parametrize(
    "global_arg",
    (
        "--lua-init=fake_default_tls=tls_mod(fake_default_tls,'rnd')",
        "--blob=my_fake=@profiles/fakes/custom.bin",
    ),
)
def test_blockcheck_candidate_rejects_extra_global_definitions(global_arg: str) -> None:
    with pytest.raises(ValueError, match="нельзя безопасно вставить"):
        split_blockcheck_profile_args(
            (
                global_arg,
                "--filter-tcp=443",
                "--payload=tls_client_hello",
                "--lua-desync=fake:blob=fake_default_tls",
            )
        )


def test_known_strategy_templates_are_reusable_profile_actions() -> None:
    templates = list_profile_strategy_templates(ROOT)

    assert templates
    assert all(any(arg.startswith("--lua-desync=") for arg in item.strategy_args) for item in templates)
    assert all(not any(arg.startswith("--filter-") for arg in item.strategy_args) for item in templates)
    assert all(not any(arg.startswith("--lua-init=") for arg in item.strategy_args) for item in templates)


def test_profile_validation_rejects_unfiltered_catch_all() -> None:
    profile = EditableTrafficProfile(
        name="Catch all",
        protocol=PRESET_PROTOCOL_ANY,
        target_kind=PRESET_TARGET_NONE,
        strategy_args=("--lua-desync=multisplit:pos=1",),
    )

    with pytest.raises(ValueError, match="перехватит любой трафик"):
        profile.validate()


def test_gui_source_exposes_constructor_and_profile_blockcheck() -> None:
    presets_source = (ROOT / "gui/zap2_gui/widgets/presets.py").read_text(encoding="utf-8")
    dialog_source = (ROOT / "gui/zap2_gui/widgets/preset_constructor.py").read_text(encoding="utf-8")

    assert '"+ Пресет"' in presets_source
    assert '"+ Профиль"' in presets_source
    assert '"Удалить пресет"' in presets_source
    assert "remove_owner_preset" in presets_source
    assert '"↑"' in presets_source and '"↓"' in presets_source
    assert "move_owner_preset_profile" in presets_source
    assert "Подобрать Blockcheck и вставить" in dialog_source
    assert "QProcess" in dialog_source
    assert "не Discord Voice/STUN UDP" in dialog_source
    assert "request_blockcheck_graceful_stop" in dialog_source
    assert 'stop_process(reason="AVAILABLE найден' not in dialog_source
    assert "AVAILABLE подтверждает только указанный target и probe" in dialog_source


def test_remove_owner_preset_deletes_files_and_catalog_entry(tmp_path: Path) -> None:
    root = _project_copy(tmp_path)
    created = create_owner_preset("Disposable preset", root=root, preset_id="disposable-preset")

    result = remove_owner_preset(created.preset_id, root=root)

    assert result.preset_id == created.preset_id
    assert not created.preset_path.exists()
    assert not created.metadata_path.exists()
    catalog_data = json.loads((root / "strategies/catalog.json").read_text(encoding="utf-8"))
    assert "strategies/workspace/disposable-preset.json" not in catalog_data["strategyFiles"]
    assert created.preset_id not in load_preset_catalog(root).by_id()


def test_remove_selected_owner_preset_falls_back_to_catalog_default(tmp_path: Path) -> None:
    root = _project_copy(tmp_path)
    created = create_owner_preset("Selected disposable", root=root, preset_id="selected-disposable")
    select_preset(created.preset_id, root=root, workspace_id="default", reason="test-delete")
    assert load_preset_catalog(root).selected_preset_id == created.preset_id

    result = remove_owner_preset(created.preset_id, root=root)

    assert result.selection_fallback_applied is True
    assert result.selected_preset_id == "manual-local"
    assert load_preset_catalog(root).selected_preset_id == "manual-local"


def test_reference_preset_cannot_be_deleted(tmp_path: Path) -> None:
    root = _project_copy(tmp_path)

    with pytest.raises(ValueError, match="Reference/community"):
        remove_owner_preset("manual-local", root=root)
