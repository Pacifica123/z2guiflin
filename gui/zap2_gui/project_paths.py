"""Repository layout helpers for the v0.3-alpha reboot.

The helpers in this module are intentionally read-only. They do not build,
install, start services, alter firewall state, or request elevated privileges.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectLayout:
    root: Path
    core_dir: Path
    gui_dir: Path
    docs_dir: Path
    tools_dir: Path
    profiles_dir: Path
    strategies_dir: Path

    def required_paths(self) -> tuple[Path, ...]:
        return (
            self.core_dir / "zapret2" / "docs" / "LICENSE.txt",
            self.core_dir / "zapret2" / "nfq2" / "nfqws.c",
            self.gui_dir / "zap2_gui" / "__init__.py",
            self.docs_dir / "DEVELOPMENT_STRATEGY.md",
            self.docs_dir / "VERSIONING.md",
            self.tools_dir / "check_project_tree.py",
            self.profiles_dir / "default.json",
            self.strategies_dir / "catalog.json",
        )


def discover_layout(root: Path | None = None) -> ProjectLayout:
    resolved_root = (root or Path(__file__).resolve().parents[2]).resolve()
    return ProjectLayout(
        root=resolved_root,
        core_dir=resolved_root / "core",
        gui_dir=resolved_root / "gui",
        docs_dir=resolved_root / "docs",
        tools_dir=resolved_root / "tools",
        profiles_dir=resolved_root / "profiles",
        strategies_dir=resolved_root / "strategies",
    )
