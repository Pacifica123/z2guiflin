"""Minimal CLI-visible shell for the new project baseline."""

from __future__ import annotations

from . import PRODUCT_LABEL
from .core_inventory import load_core_build_map, load_core_inventory, load_core_inventory_snapshot
from .project_paths import discover_layout


def describe_project() -> str:
    layout = discover_layout()
    inventory = load_core_inventory(layout.root)
    snapshot = load_core_inventory_snapshot(layout.root)
    build_map = load_core_build_map(layout.root)
    units = ", ".join(unit.name for unit in build_map.units)
    return "\n".join(
        [
            f"Zap2 GUI Linux {PRODUCT_LABEL}",
            f"root: {layout.root}",
            f"core: {inventory.upstream_name} ({inventory.imported_files} imported files)",
            f"inventory: {snapshot.vendor_file_count} vendored files",
            f"build units: {units}",
            "status: bootstrap/read-only baseline",
        ]
    )


def main() -> None:
    print(describe_project())


if __name__ == "__main__":
    main()
