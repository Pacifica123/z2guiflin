"""Read-only state assembly for the GUI shell."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core_inventory import CoreBuildMap, CoreInventorySnapshot, load_core_build_map, load_core_inventory_snapshot
from ..models.navigation import NavigationSection, default_navigation_sections


@dataclass(frozen=True)
class GuiShellState:
    sections: tuple[NavigationSection, ...]
    core_snapshot: CoreInventorySnapshot
    build_map: CoreBuildMap


def load_gui_shell_state(root: Path | None = None) -> GuiShellState:
    return GuiShellState(
        sections=default_navigation_sections(),
        core_snapshot=load_core_inventory_snapshot(root),
        build_map=load_core_build_map(root),
    )
