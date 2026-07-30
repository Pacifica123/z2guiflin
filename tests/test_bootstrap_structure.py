from __future__ import annotations

import json
from pathlib import Path

from zap2_gui import PRODUCT_LABEL, __version__
from zap2_gui.core_inventory import load_core_inventory
from zap2_gui.project_paths import discover_layout


def test_product_label() -> None:
    assert PRODUCT_LABEL == "v0.4"
    assert __version__ == "0.4.0"


def test_layout_required_paths_exist() -> None:
    layout = discover_layout(Path(__file__).resolve().parents[1])
    missing = [path for path in layout.required_paths() if not path.exists()]
    assert missing == []


def test_core_inventory_manifest() -> None:
    root = Path(__file__).resolve().parents[1]
    inventory = load_core_inventory(root)
    assert inventory.upstream_name == "bol-van/zapret2"
    assert inventory.imported_files > 0
    assert inventory.license_path.exists()


def test_core_import_excludes_compiled_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "core/zapret2/UPSTREAM_IMPORT.json").read_text(encoding="utf-8"))
    excluded = set(data["excludedFiles"])
    assert "nfq2/windows/res/winws_res32.o" in excluded
    assert "nfq2/windows/windivert/libwindivert64.a" in excluded


def test_tools_and_meta_tools_layout() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "tools/gui_checks/check_project_tree.py").exists()
    assert (root / "tools/experimental/README.md").exists()
    assert (root / "tools/lowlevel/README.md").exists()
    assert (root / "meta_tools/devctl/devctl.py").exists()
    assert not (root / "tools/check_project_tree.py").exists()
