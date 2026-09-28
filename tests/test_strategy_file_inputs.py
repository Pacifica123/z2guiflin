from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from zap2_gui.adapters.core_provenance import write_core_build_receipt
from zap2_gui.adapters.preset_txt_import import import_txt_preset
from zap2_gui.adapters.presets import select_preset
from zap2_gui.adapters.runtime_session import build_runtime_session_config
from zap2_gui.adapters.runtime_state import confirm_runtime_plan, prepare_runtime_plan
from zap2_gui.adapters.strategy_file_inputs import (
    inspect_strategy_file_dependencies,
    strategy_file_dependency_error_text,
)

ROOT = Path(__file__).resolve().parents[1]


def _project_copy(tmp_path: Path) -> Path:
    target = tmp_path / "project"
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".zap2"),
    )
    return target


def _install_fake_nfqws2(project: Path) -> None:
    binary = project / "core/zapret2/nfq2/nfqws2"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    write_core_build_receipt(project, [binary], "nfqws2")


def _preset_text() -> str:
    return """# Preset: file dependency test
--lua-init=@lua/zapret-lib.lua
--lua-init=@lua/zapret-antidpi.lua
--filter-tcp=443
--hostlist=lists/service.txt
--ipset=lists/service-ipset.txt
--lua-desync=pass
"""


def test_dependency_inspector_distinguishes_ready_missing_and_unsafe(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "lists").mkdir(parents=True)
    (root / "lists/ok.txt").write_text("example.com\n", encoding="utf-8")
    args = (
        "--hostlist=lists/ok.txt",
        "--ipset=lists/missing.txt",
        "--hostlist-exclude=../../etc/passwd",
    )

    states = {item.value: item.state for item in inspect_strategy_file_dependencies(root, args)}

    assert states["lists/ok.txt"] == "ready"
    assert states["lists/missing.txt"] == "missing"
    assert states["../../etc/passwd"] == "unsafe"
    error = strategy_file_dependency_error_text(root, args)
    assert "lists/missing.txt" in error
    assert "../../etc/passwd" in error


def test_runtime_config_blocks_missing_strategy_lists_before_nfqws_start(tmp_path: Path) -> None:
    project = _project_copy(tmp_path)
    _install_fake_nfqws2(project)
    source = tmp_path / "preset.txt"
    source.write_text(_preset_text(), encoding="utf-8")
    imported = import_txt_preset(source, project)
    select_preset(imported.preset_id, root=project)
    prepared = prepare_runtime_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, prepared.plan_id)

    with pytest.raises(ValueError, match="strategy file dependencies не готовы") as exc:
        build_runtime_session_config(project, profile_id="default")

    assert "lists/service.txt" in str(exc.value)
    assert "lists/service-ipset.txt" in str(exc.value)


def test_runtime_config_uses_public_copies_for_imported_strategy_lists(tmp_path: Path, monkeypatch) -> None:
    project = _project_copy(tmp_path)
    _install_fake_nfqws2(project)
    package = tmp_path / "package"
    package.mkdir()
    (package / "lists").mkdir()
    (package / "lists/service.txt").write_text("example.com\n", encoding="utf-8")
    (package / "lists/service-ipset.txt").write_text("203.0.113.0/24\n", encoding="utf-8")
    source = package / "preset.txt"
    source.write_text(_preset_text(), encoding="utf-8")
    imported = import_txt_preset(source, project)
    select_preset(imported.preset_id, root=project)
    prepared = prepare_runtime_plan(project, action="start", profile_id="default")
    confirm_runtime_plan(project, prepared.plan_id)
    public_base = tmp_path / "public"
    monkeypatch.setenv("ZAP2_PUBLIC_RUNTIME_INPUTS_DIR", str(public_base))

    config = build_runtime_session_config(project, profile_id="default")

    assert len(config.strategy_file_input_paths) == 2
    assert all(path.is_file() for path in config.strategy_file_input_paths)
    assert all(path.is_relative_to(public_base / "zap2-runtime-inputs") for path in config.strategy_file_input_paths)
    hostlist_args = [arg for arg in config.runtime_args if arg.startswith("--hostlist=")]
    ipset_args = [arg for arg in config.runtime_args if arg.startswith("--ipset=")]
    assert any(str(public_base) in arg for arg in hostlist_args)
    assert any(str(public_base) in arg for arg in ipset_args)
    assert not any("presets/imported-assets" in arg for arg in hostlist_args + ipset_args)
