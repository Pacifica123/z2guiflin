"""Read-only inventory helpers for the vendored zapret2 core."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .project_paths import discover_layout


@dataclass(frozen=True)
class CoreInventory:
    upstream_name: str
    upstream_root: Path
    imported_files: int
    excluded_files: tuple[str, ...]
    license_path: Path


@dataclass(frozen=True)
class CoreInventorySnapshot:
    upstream_name: str
    vendor_file_count: int
    extension_counts: dict[str, int]
    top_level_file_counts: dict[str, int]
    primary_makefiles: tuple[str, ...]
    privilege_touchpoints: tuple[str, ...]


@dataclass(frozen=True)
class CoreBuildUnit:
    name: str
    kind: str
    makefile: str
    linux_outputs: tuple[str, ...]
    known_targets: tuple[str, ...]


@dataclass(frozen=True)
class CoreBuildMap:
    automatic_checks_may_run_make: bool
    delegated_directories: tuple[str, ...]
    output_directory: str
    root_targets: tuple[str, ...]
    units: tuple[CoreBuildUnit, ...]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_core_inventory(root: Path | None = None) -> CoreInventory:
    layout = discover_layout(root)
    manifest_path = layout.core_dir / "zapret2" / "UPSTREAM_IMPORT.json"
    data: dict[str, Any] = _read_json(manifest_path)
    return CoreInventory(
        upstream_name=str(data["upstreamName"]),
        upstream_root=layout.core_dir / "zapret2",
        imported_files=int(data["importedFileCount"]),
        excluded_files=tuple(str(item) for item in data.get("excludedFiles", [])),
        license_path=layout.core_dir / "zapret2" / str(data["licensePath"]),
    )


def load_core_inventory_snapshot(root: Path | None = None) -> CoreInventorySnapshot:
    layout = discover_layout(root)
    data: dict[str, Any] = _read_json(layout.core_dir / "zapret2" / "CORE_INVENTORY.json")
    counts = data["counts"]
    notable = data["notablePaths"]
    upstream = data["upstream"]
    return CoreInventorySnapshot(
        upstream_name=str(upstream["name"]),
        vendor_file_count=int(counts["vendorFileCount"]),
        extension_counts={str(k): int(v) for k, v in counts["extensionCounts"].items()},
        top_level_file_counts={str(k): int(v) for k, v in counts["topLevelFileCounts"].items()},
        primary_makefiles=tuple(str(item) for item in notable["primaryMakefiles"]),
        privilege_touchpoints=tuple(str(item) for item in notable["privilegeTouchpoints"]),
    )


def load_core_build_map(root: Path | None = None) -> CoreBuildMap:
    layout = discover_layout(root)
    data: dict[str, Any] = _read_json(layout.core_dir / "zapret2" / "BUILD_MAP.json")
    root_makefile = data["rootMakefile"]
    safety_policy = data["safetyPolicy"]
    units = tuple(
        CoreBuildUnit(
            name=str(unit["name"]),
            kind=str(unit["kind"]),
            makefile=str(unit["makefile"]),
            linux_outputs=tuple(str(item) for item in unit["linuxOutputs"]),
            known_targets=tuple(str(item) for item in unit["knownTargets"]),
        )
        for unit in data["units"]
    )
    return CoreBuildMap(
        automatic_checks_may_run_make=bool(safety_policy["automaticChecksMayRunMake"]),
        delegated_directories=tuple(str(item) for item in root_makefile["delegatedDirectories"]),
        output_directory=str(root_makefile["outputDirectory"]),
        root_targets=tuple(str(item) for item in root_makefile["targets"]),
        units=units,
    )
