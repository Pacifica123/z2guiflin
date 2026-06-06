#!/usr/bin/env python3
"""Read-only repository check for the v0.3-alpha bootstrap."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = [
    "README.md",
    "pyproject.toml",
    "core/README.md",
    "core/zapret2/UPSTREAM_IMPORT.json",
    "core/zapret2/docs/LICENSE.txt",
    "core/zapret2/Makefile",
    "core/zapret2/nfq2/nfqws.c",
    "core/zapret2/lua/zapret-lib.lua",
    "gui/README.md",
    "gui/zap2_gui/__init__.py",
    "gui/zap2_gui/app.py",
    "docs/DEVELOPMENT_STRATEGY.md",
    "docs/VERSIONING.md",
    "docs/SAFETY_AND_PRIVILEGE_BOUNDARY.md",
    "docs/reference/windows_gui_feature_digest.md",
    "docs/reference/legacy_project_digest.md",
]

FORBIDDEN_IMPORTED_SUFFIXES = (".o", ".a", ".exe", ".dll")


def main() -> int:
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    if missing:
        print("Missing required paths:")
        for path in missing:
            print(f" - {path}")
        return 1

    manifest_path = ROOT / "core/zapret2/UPSTREAM_IMPORT.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("upstreamName") != "bol-van/zapret2":
        print("Unexpected upstreamName in core import manifest")
        return 1
    if int(manifest.get("importedFileCount", 0)) <= 0:
        print("Core import manifest has no imported files")
        return 1

    bad = [
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in (ROOT / "core/zapret2").rglob("*")
        if path.is_file() and path.name.lower().endswith(FORBIDDEN_IMPORTED_SUFFIXES)
    ]
    if bad:
        print("Unexpected compiled/binary artifacts imported:")
        for path in bad:
            print(f" - {path}")
        return 1

    print("v0.3-alpha bootstrap tree OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
