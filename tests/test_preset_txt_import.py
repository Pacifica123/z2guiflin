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
