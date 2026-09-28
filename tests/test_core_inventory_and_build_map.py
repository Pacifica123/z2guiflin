from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from zap2_gui.core_inventory import load_core_build_map, load_core_inventory_snapshot

ROOT = Path(__file__).resolve().parents[1]


def _load_json(rel_path: str) -> dict:
    return json.loads((ROOT / rel_path).read_text(encoding="utf-8"))


def _load_inventory_tool():
    spec = importlib.util.spec_from_file_location("inventory_core", ROOT / "tools/gui_checks/inventory_core.py")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_core_inventory_snapshot_matches_import_manifest() -> None:
    manifest = _load_json("core/zapret2/UPSTREAM_IMPORT.json")
    inventory = _load_json("core/zapret2/CORE_INVENTORY.json")

    assert inventory["schemaVersion"] == 1
    assert inventory["policy"]["doesNotBuildCore"] is True
    assert inventory["policy"]["doesNotRequireSudo"] is True
    assert manifest["importedFileCount"] == 244
    assert inventory["counts"]["vendorFileCount"] == 244
    assert inventory["counts"]["upstreamImportedFileCount"] == 244
    assert inventory["counts"]["projectLocalCoreFileCount"] == 0
    assert inventory["projectLocalCoreFiles"] == []
    assert inventory["counts"]["topLevelFileCounts"]["nfq2"] == 68
    assert inventory["counts"]["extensionCounts"][".c"] == 32
    assert inventory["notablePaths"]["primaryMakefiles"] == [
        "Makefile",
        "nfq2/Makefile",
        "ip2net/Makefile",
        "mdig/Makefile",
    ]


def test_build_map_describes_primary_units_without_auto_make() -> None:
    build_map = _load_json("core/zapret2/BUILD_MAP.json")

    assert build_map["schemaVersion"] == 1
    assert build_map["safetyPolicy"]["automaticChecksMayRunMake"] is False
    assert build_map["safetyPolicy"]["automaticChecksMayUseSudo"] is False
    assert build_map["rootMakefile"]["delegatedDirectories"] == ["nfq2", "ip2net", "mdig"]
    assert build_map["rootMakefile"]["targets"] == ["all", "systemd", "android", "bsd", "clean"]

    units = {unit["name"]: unit for unit in build_map["units"]}
    assert set(units) == {"nfqws2", "ip2net", "mdig"}
    assert units["nfqws2"]["makefile"] == "nfq2/Makefile"
    assert "libnetfilter_queue" in units["nfqws2"]["declaredLinuxLibraries"]
    assert units["ip2net"]["linuxOutputs"] == ["ip2net/ip2net"]
    assert units["mdig"]["linuxOutputs"] == ["mdig/mdig"]


def test_inventory_tool_matches_committed_snapshots() -> None:
    tool = _load_inventory_tool()
    assert tool.compute_core_inventory() == _load_json("core/zapret2/CORE_INVENTORY.json")
    assert tool.compute_build_map() == _load_json("core/zapret2/BUILD_MAP.json")


def test_gui_layer_can_read_inventory_and_build_map() -> None:
    snapshot = load_core_inventory_snapshot(ROOT)
    build_map = load_core_build_map(ROOT)

    assert snapshot.upstream_name == "bol-van/zapret2"
    assert snapshot.vendor_file_count == 244
    assert snapshot.upstream_imported_file_count == 244
    assert snapshot.project_local_core_file_count == 0
    assert snapshot.project_local_core_files == ()
    assert "nfq2/Makefile" in snapshot.primary_makefiles
    assert "common/linux_fw.sh" in snapshot.privilege_touchpoints

    assert build_map.automatic_checks_may_run_make is False
    assert build_map.delegated_directories == ("nfq2", "ip2net", "mdig")
    assert [unit.name for unit in build_map.units] == ["nfqws2", "ip2net", "mdig"]
