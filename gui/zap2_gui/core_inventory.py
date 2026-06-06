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


def load_core_inventory(root: Path | None = None) -> CoreInventory:
    layout = discover_layout(root)
    manifest_path = layout.core_dir / "zapret2" / "UPSTREAM_IMPORT.json"
    data: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    return CoreInventory(
        upstream_name=str(data["upstreamName"]),
        upstream_root=layout.core_dir / "zapret2",
        imported_files=int(data["importedFileCount"]),
        excluded_files=tuple(str(item) for item in data.get("excludedFiles", [])),
        license_path=layout.core_dir / "zapret2" / str(data["licensePath"]),
    )
