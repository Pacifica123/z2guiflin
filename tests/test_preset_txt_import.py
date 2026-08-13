from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from zap2_gui.adapters.preset_txt_import import analyze_txt_preset, import_txt_preset
from zap2_gui.adapters.presets import load_preset

ROOT = Path(__file__).resolve().parents[1]


def _project_copy(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".zap2"),
    )
    return target


def _windows_zapret2_text() -> str:
    return """# Preset: Universal import test
# BuiltinVersion: 2.26
# Description: test full preset
--lua-init=@lua/zapret-lib.lua
--lua-init=@lua/zapret-antidpi.lua
--lua-init=@lua/missing-unused.lua
--wf-tcp-out=80,443-65535
--wf-udp-out=443-65535
--wf-raw-part=@windivert.filter/test.txt
--blob=tls_google:@bin/tls_clienthello_www_google_com.bin
--blob=unused_missing:@bin/not-present.bin
--name=YouTube
--filter-tcp=443
--hostlist=lists/youtube.txt
--out-range=-d8
--lua-desync=fake:blob=tls_google:repeats=2
--new
--name=Discord
--filter-tcp=443
--hostlist-domains=discord.com
--out-range=-d8
--lua-desync=send:repeats=2
"""


def test_windows_txt_preset_is_detected_and_adapted_without_runtime_execution(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    source = tmp_path / "Universal V5.txt"
    source.write_text(_windows_zapret2_text(), encoding="utf-8")

    analysis = analyze_txt_preset(source, project)

    assert analysis.can_import is True
    assert analysis.title == "Universal import test"
    assert analysis.builtin_version == "2.26"
    assert analysis.confidence == "high"
    assert len(analysis.parsed_preset.profiles) == 2
    assert analysis.windows_tcp_capture_hint == ("80", "443-65535")
    assert analysis.windows_udp_capture_hint == ("443-65535",)
    assert not any(arg.startswith("--wf-") for arg in analysis.runtime_args)
    assert "--lua-init=@core/zapret2/lua/zapret-lib.lua" in analysis.runtime_args
    assert "--lua-init=@core/zapret2/lua/zapret-antidpi.lua" in analysis.runtime_args
    assert "--blob=tls_google:@core/zapret2/files/fake/tls_clienthello_www_google_com.bin" in analysis.runtime_args
    assert not any("unused_missing" in arg for arg in analysis.runtime_args)
    assert any(issue.code == "LIST_DEPENDENCIES_MISSING" for issue in analysis.warnings)
    assert any(issue.code == "UNUSED_LUA_INIT_DROPPED" for issue in analysis.warnings)


def test_import_creates_full_owner_managed_preset_and_keeps_profile_order(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    source = tmp_path / "preset.txt"
    source.write_text(_windows_zapret2_text(), encoding="utf-8")

    result = import_txt_preset(source, project)
    entry = load_preset(result.preset_id, project)

    assert result.mutation.action == "txt-imported"
    assert [profile.name for profile in entry.preset.profiles] == ["YouTube", "Discord"]
    assert entry.preset.to_runtime_args() == result.analysis.runtime_args
    assert not any(arg.startswith("--wf-") for arg in entry.preset.to_runtime_args())
    metadata = json.loads(result.mutation.metadata_path.read_text(encoding="utf-8"))
    assert metadata["sourcePreset"]["id"] == "txt-preset-import"
    assert metadata["sourcePreset"]["editorManaged"] is True
    assert metadata["sourcePreset"]["sourceFilename"] == "preset.txt"
    assert metadata["sourcePreset"]["sourceSha256"]

    second = import_txt_preset(source, project)
    assert second.preset_id == result.preset_id + "-2"


def test_cp1251_txt_preset_is_supported(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    source = tmp_path / "russian.txt"
    text = """# Preset: Русский пресет
--filter-tcp=443
--hostlist-domains=example.com
--lua-desync=pass
"""
    source.write_bytes(text.encode("cp1251"))

    analysis = analyze_txt_preset(source, project)

    assert analysis.can_import is True
    assert analysis.encoding == "cp1251"
    assert analysis.title == "Русский пресет"
    assert analysis.parsed_preset.profiles[0].strategy_label == "pass"


def test_arbitrary_txt_is_rejected_before_catalog_mutation(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("обычный текст\n--verbose\n--help\n", encoding="utf-8")
    before = (project / "strategies/catalog.json").read_bytes()

    with pytest.raises(ValueError, match="не распознан как Zapret preset"):
        import_txt_preset(source, project)

    assert (project / "strategies/catalog.json").read_bytes() == before


def test_zapret1_dpi_desync_txt_is_detected_but_not_silently_translated(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    source = tmp_path / "zapret1.txt"
    source.write_text(
        "--filter-tcp=443\n--hostlist=lists/example.txt\n--dpi-desync=fake,split2\n",
        encoding="utf-8",
    )

    analysis = analyze_txt_preset(source, project)

    assert analysis.can_import is False
    assert any(issue.code == "ZAPRET1_OPTION_UNSUPPORTED" for issue in analysis.errors)


def test_used_unknown_lua_function_blocks_import(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    source = tmp_path / "custom.txt"
    source.write_text(
        "--lua-init=@lua/custom-not-present.lua\n"
        "--filter-tcp=443\n"
        "--hostlist-domains=example.com\n"
        "--lua-desync=my_custom_split:pos=1\n",
        encoding="utf-8",
    )

    analysis = analyze_txt_preset(source, project)

    assert analysis.can_import is False
    assert any(issue.code == "LUA_DESYNC_FUNCTION_UNAVAILABLE" for issue in analysis.errors)


def test_workspace_escape_in_hostlist_is_rejected(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    source = tmp_path / "escape.txt"
    source.write_text(
        "--filter-tcp=443\n"
        "--hostlist=../../etc/passwd\n"
        "--lua-desync=pass\n",
        encoding="utf-8",
    )

    analysis = analyze_txt_preset(source, project)

    assert analysis.can_import is False
    assert any(issue.code == "UNSAFE_FILE_REFERENCE" for issue in analysis.errors)


def test_gui_exposes_txt_preset_import_button_and_file_dialog() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/presets.py").read_text(encoding="utf-8")

    assert '"Импорт .txt"' in source
    assert "QFileDialog.getOpenFileName" in source
    assert "analyze_txt_preset" in source
    assert "import_txt_preset" in source


def test_companion_lists_are_discovered_copied_and_rewritten_into_project_assets(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    package = tmp_path / "external-package"
    source_dir = package / "presets"
    source_dir.mkdir(parents=True)
    lists_dir = package / "lists"
    lists_dir.mkdir(parents=True)
    source = source_dir / "Universal.txt"
    source.write_text(_windows_zapret2_text(), encoding="utf-8")
    lists_dir.joinpath("youtube.txt").write_text("youtube.com\ngooglevideo.com\n", encoding="utf-8")

    analysis = analyze_txt_preset(source, project)

    assert analysis.external_list_dependencies == ("lists/youtube.txt",)
    assert analysis.missing_list_dependencies == ()
    assert analysis.runtime_ready_after_import is True

    result = import_txt_preset(source, project)
    entry = load_preset(result.preset_id, project)
    hostlist_arg = next(arg for arg in entry.preset.to_runtime_args() if arg.startswith("--hostlist="))
    imported_rel = hostlist_arg.split("=", 1)[1]

    assert imported_rel.startswith("presets/imported-assets/txt-")
    assert imported_rel.endswith("/lists/youtube.txt")
    imported = project / imported_rel
    assert imported.read_text(encoding="utf-8") == "youtube.com\ngooglevideo.com\n"
    assert result.analysis.missing_list_dependencies == ()
    metadata = json.loads(result.mutation.metadata_path.read_text(encoding="utf-8"))
    assert metadata["sourcePreset"]["listAssetsRoot"].startswith("presets/imported-assets/txt-")
    assert "missingListDependencies" not in metadata["sourcePreset"]


def test_explicit_dependency_root_can_supply_lists_not_adjacent_to_txt(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    source = tmp_path / "loose" / "Universal.txt"
    source.parent.mkdir(parents=True)
    source.write_text(_windows_zapret2_text(), encoding="utf-8")
    package = tmp_path / "package-root"
    (package / "lists").mkdir(parents=True)
    (package / "lists" / "youtube.txt").write_text("youtube.com\n", encoding="utf-8")

    analysis = analyze_txt_preset(source, project, dependency_root=package)
    result = import_txt_preset(source, project, dependency_root=package)

    assert analysis.missing_list_dependencies == ()
    assert analysis.external_list_dependencies == ("lists/youtube.txt",)
    assert result.analysis.runtime_ready_after_import is True
    assert any("presets/imported-assets/" in arg for arg in result.analysis.runtime_args if arg.startswith("--hostlist="))


def test_incomplete_import_is_marked_not_runtime_ready(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    source = tmp_path / "preset.txt"
    source.write_text(_windows_zapret2_text(), encoding="utf-8")

    result = import_txt_preset(source, project)
    metadata = json.loads(result.mutation.metadata_path.read_text(encoding="utf-8"))

    assert result.analysis.can_import is True
    assert result.analysis.runtime_ready_after_import is False
    assert result.analysis.missing_list_dependencies == ("lists/youtube.txt",)
    assert metadata["sourcePreset"]["missingListDependencies"] == ["lists/youtube.txt"]


def test_gui_can_request_dependency_root_for_missing_lists() -> None:
    source = (ROOT / "gui/zap2_gui/widgets/presets.py").read_text(encoding="utf-8")

    assert "missing_list_dependencies" in source
    assert "QFileDialog.getExistingDirectory" in source
    assert "dependency_root=dependency_root" in source


def test_nested_package_root_is_discovered_beyond_old_two_ancestor_limit(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    package = tmp_path / "loop-style-package"
    source = package / "presets" / "builtin" / "winws2" / "Universal V5.txt"
    source.parent.mkdir(parents=True)
    source.write_text(_windows_zapret2_text(), encoding="utf-8")
    (package / "lists").mkdir(parents=True)
    (package / "lists" / "youtube.txt").write_text("youtube.com\n", encoding="utf-8")

    analysis = analyze_txt_preset(source, project)
    result = import_txt_preset(source, project)

    assert analysis.dependency_root_hint == package.resolve()
    assert analysis.dependency_root_coverage == "1/1"
    assert analysis.missing_list_dependencies == ()
    assert result.analysis.runtime_ready_after_import is True


def test_source_package_root_resolver_is_not_bound_to_preset_file_type(tmp_path: Path) -> None:
    from zap2_gui.adapters.import_source_root import discover_source_package_root, resolve_source_package_file

    package = tmp_path / "generic-package"
    source = package / "deep" / "objects" / "payload.custom"
    source.parent.mkdir(parents=True)
    source.write_text("payload", encoding="utf-8")
    (package / "assets").mkdir(parents=True)
    companion = package / "assets" / "data.bin"
    companion.write_bytes(b"data")

    probe = discover_source_package_root(source, ("assets/data.bin",))
    resolved, resolved_probe = resolve_source_package_file(
        source,
        "assets/data.bin",
        all_relative_refs=("assets/data.bin",),
    )

    assert probe is not None
    assert probe.root == package.resolve()
    assert probe.coverage == "1/1"
    assert resolved == companion.resolve()
    assert resolved_probe is not None
    assert resolved_probe.root == package.resolve()


def test_loop_uh_source_layout_is_detected_but_missing_runtime_lists_stays_explicit(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    repo = tmp_path / "zapretgui"
    source_root = repo / "src"
    source = source_root / "presets" / "builtin" / "winws2" / "Universal V5.txt"
    source.parent.mkdir(parents=True)
    source.write_text(_windows_zapret2_text(), encoding="utf-8")
    (source_root / "lists").mkdir(parents=True)
    (source_root / "lists" / "__init__.py").write_text("", encoding="utf-8")
    (source_root / "config").mkdir(parents=True)
    (source_root / "config" / "runtime_layout.py").write_text("# marker\n", encoding="utf-8")

    analysis = analyze_txt_preset(source, project)

    assert analysis.dependency_root_hint == source_root.resolve()
    assert "application-resource-root" in analysis.dependency_root_reason
    assert analysis.missing_list_dependencies == ("lists/youtube.txt",)
    assert any(issue.code == "SOURCE_PACKAGE_RUNTIME_ASSETS_ABSENT" for issue in analysis.warnings)


def test_deleting_imported_presets_removes_assets_only_after_last_reference(tmp_path: Path) -> None:
    from zap2_gui.adapters.preset_editor import remove_owner_preset

    project = _project_copy(tmp_path)
    package = tmp_path / "package"
    source = package / "presets" / "Universal.txt"
    source.parent.mkdir(parents=True)
    source.write_text(_windows_zapret2_text(), encoding="utf-8")
    (package / "lists").mkdir(parents=True)
    (package / "lists" / "youtube.txt").write_text("youtube.com\n", encoding="utf-8")

    first = import_txt_preset(source, project)
    second = import_txt_preset(source, project)
    first_meta = json.loads(first.mutation.metadata_path.read_text(encoding="utf-8"))
    second_meta = json.loads(second.mutation.metadata_path.read_text(encoding="utf-8"))
    assert first_meta["sourcePreset"]["listAssetsRoot"] == second_meta["sourcePreset"]["listAssetsRoot"]
    asset_root = project / first_meta["sourcePreset"]["listAssetsRoot"]
    assert asset_root.is_dir()

    first_deleted = remove_owner_preset(first.preset_id, root=project)
    assert first_deleted.removed_asset_root is None
    assert asset_root.is_dir()

    second_deleted = remove_owner_preset(second.preset_id, root=project)
    assert second_deleted.removed_asset_root == asset_root.resolve()
    assert not asset_root.exists()
