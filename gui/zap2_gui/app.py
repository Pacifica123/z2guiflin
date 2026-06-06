"""CLI-visible entry point and optional PyQt GUI launcher."""

from __future__ import annotations

import argparse
import sys

from . import PRODUCT_LABEL
from .core_inventory import load_core_build_map, load_core_inventory, load_core_inventory_snapshot
from .models.navigation import default_navigation_sections
from .project_paths import discover_layout
from .qt_compat import PyQtUnavailableError, is_pyqt_available


def describe_project() -> str:
    layout = discover_layout()
    inventory = load_core_inventory(layout.root)
    snapshot = load_core_inventory_snapshot(layout.root)
    build_map = load_core_build_map(layout.root)
    units = ", ".join(unit.name for unit in build_map.units)
    sections = ", ".join(section.title for section in default_navigation_sections())
    pyqt_state = "available" if is_pyqt_available() else "not installed"
    return "\n".join(
        [
            f"Zap2 GUI Linux {PRODUCT_LABEL}",
            f"root: {layout.root}",
            f"core: {inventory.upstream_name} ({inventory.imported_files} imported files)",
            f"inventory: {snapshot.vendor_file_count} vendored files",
            f"build units: {units}",
            f"gui shell: PyQt skeleton ({pyqt_state})",
            f"navigation: {sections}",
            "status: bootstrap/read-only baseline with optional GUI launch",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Zap2 GUI Linux bootstrap shell")
    parser.add_argument(
        "--gui",
        action="store_true",
        help="запустить локальную PyQt GUI shell; требует установленный PyQt6 и display server",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.gui:
        try:
            from .qt_app import run_gui

            return run_gui(sys.argv if argv is None else [sys.argv[0], *argv])
        except PyQtUnavailableError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    print(describe_project())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
