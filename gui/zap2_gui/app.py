"""Minimal CLI-visible shell for the new project baseline."""

from __future__ import annotations

from . import PRODUCT_LABEL
from .core_inventory import load_core_inventory
from .project_paths import discover_layout


def describe_project() -> str:
    layout = discover_layout()
    inventory = load_core_inventory(layout.root)
    return "\n".join(
        [
            f"Zap2 GUI Linux {PRODUCT_LABEL}",
            f"root: {layout.root}",
            f"core: {inventory.upstream_name} ({inventory.imported_files} imported files)",
            "status: bootstrap/read-only baseline",
        ]
    )


def main() -> None:
    print(describe_project())


if __name__ == "__main__":
    main()
