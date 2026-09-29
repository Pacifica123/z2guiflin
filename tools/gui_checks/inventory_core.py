#!/usr/bin/env python3
"""Read-only инвентаризация vendored-ядра zapret2."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CORE_ROOT = ROOT / "core" / "zapret2"
INVENTORY_PATH = CORE_ROOT / "CORE_INVENTORY.json"
BUILD_MAP_PATH = CORE_ROOT / "BUILD_MAP.json"
UPSTREAM_IMPORT_PATH = CORE_ROOT / "UPSTREAM_IMPORT.json"

SNAPSHOT_METADATA_FILES = {
    "UPSTREAM_IMPORT.json",
    "UPSTREAM_IMPORT.md",
    "CORE_INVENTORY.json",
    "BUILD_MAP.json",
}

# Declared build artifacts are runtime products, not vendored source generation.
# A successful owner build intentionally publishes these paths inside core/zapret2;
# inventory must remain idempotent across repeated acceptance runs.
GENERATED_BUILD_OUTPUTS = {
    "nfq2/nfqws2",
    "nfq2/dvtws2",
    "nfq2/winws2.exe",
    "ip2net/ip2net",
    "ip2net/ip2neta",
    "ip2net/ip2netx",
    "mdig/mdig",
    "mdig/mdiga",
    "mdig/mdigx",
}

# P03 keeps project-local runtime overlays outside the vendored upstream tree.
# This mapping is intentionally empty: any future entry is a generation-boundary
# regression and must be reviewed rather than silently treated as upstream.
PROJECT_LOCAL_CORE_FILES: dict[str, str] = {}

PRIMARY_MAKEFILES = [
    "Makefile",
    "nfq2/Makefile",
    "ip2net/Makefile",
    "mdig/Makefile",
]

MAKE_TARGET_RE = re.compile(r"^([A-Za-z0-9_.-][A-Za-z0-9_. -]*)\s*:(?!=)")

BUILD_UNITS: list[dict[str, Any]] = [
    {
        "name": "nfqws2",
        "kind": "packet_processing_binary",
        "makefile": "nfq2/Makefile",
        "sourceRoots": ["nfq2", "nfq2/crypto", "nfq2/andr"],
        "sourceGlobs": ["nfq2/*.c", "nfq2/crypto/*.c", "nfq2/andr/*.c"],
        "linuxOutputs": ["nfq2/nfqws2"],
        "otherOutputs": ["nfq2/dvtws2", "nfq2/winws2.exe"],
        "declaredLinuxLibraries": [
            "zlib",
            "libnetfilter_queue",
            "libnfnetlink",
            "libmnl",
            "libm",
            "LuaJIT или Lua",
        ],
        "knownTargets": [
            "all",
            "nfqws2",
            "ubsan",
            "systemd",
            "android",
            "bsd",
            "cygwin64",
            "cygwin32",
            "cygwin",
            "clean",
        ],
    },
    {
        "name": "ip2net",
        "kind": "helper_binary",
        "makefile": "ip2net/Makefile",
        "sourceRoots": ["ip2net"],
        "sourceGlobs": ["ip2net/ip2net.c", "ip2net/qsort.c"],
        "linuxOutputs": ["ip2net/ip2net"],
        "otherOutputs": ["ip2net/ip2neta", "ip2net/ip2netx"],
        "declaredLinuxLibraries": [],
        "knownTargets": ["all", "ip2net", "systemd", "android", "bsd", "mac", "win", "clean"],
    },
    {
        "name": "mdig",
        "kind": "dns_helper_binary",
        "makefile": "mdig/Makefile",
        "sourceRoots": ["mdig"],
        "sourceGlobs": ["mdig/*.c"],
        "linuxOutputs": ["mdig/mdig"],
        "otherOutputs": ["mdig/mdiga", "mdig/mdigx"],
        "declaredLinuxLibraries": ["pthread"],
        "knownTargets": ["all", "mdig", "systemd", "android", "bsd", "mac", "win", "clean"],
    },
]


def _core_files() -> list[Path]:
    return sorted(
        path
        for path in CORE_ROOT.rglob("*")
        if path.is_file()
        and path.name not in SNAPSHOT_METADATA_FILES
        and path.relative_to(CORE_ROOT).as_posix() not in GENERATED_BUILD_OUTPUTS
    )


def _vendor_files() -> list[Path]:
    return _core_files()


def _upstream_vendor_files() -> list[Path]:
    return [path for path in _core_files() if _rel(path) not in PROJECT_LOCAL_CORE_FILES]


def _project_local_files() -> list[Path]:
    return [path for path in _core_files() if _rel(path) in PROJECT_LOCAL_CORE_FILES]


def _rel(path: Path) -> str:
    return path.relative_to(CORE_ROOT).as_posix()


def _top_level(path: Path) -> str:
    rel = path.relative_to(CORE_ROOT)
    return rel.parts[0] if len(rel.parts) > 1 else "."


def _suffix(path: Path) -> str:
    return path.suffix.lower() or "<none>"


def _targets_from_makefile(rel_path: str) -> list[str]:
    path = CORE_ROOT / rel_path
    targets: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = MAKE_TARGET_RE.match(line)
        if not match:
            continue
        target_part = match.group(1)
        if "=" in target_part:
            continue
        for target in target_part.split():
            if target.startswith(".") or "$" in target:
                continue
            if target not in targets:
                targets.append(target)
    return targets


def compute_core_inventory() -> dict[str, Any]:
    upstream = json.loads(UPSTREAM_IMPORT_PATH.read_text(encoding="utf-8"))
    files = _vendor_files()
    upstream_files = _upstream_vendor_files()
    project_local_files = _project_local_files()
    top_dirs = Counter(_top_level(path) for path in files)
    extensions = Counter(_suffix(path) for path in files)
    source_dirs = Counter(
        Path(_rel(path)).parent.as_posix()
        for path in files
        if path.suffix.lower() in {".c", ".h", ".lua"}
    )
    makefiles = [
        _rel(path)
        for path in sorted(CORE_ROOT.rglob("*"))
        if path.is_file() and (path.name == "Makefile" or path.name == "BSDmakefile" or path.name.endswith("makefile"))
    ]
    privilege_touchpoints = [
        "install_easy.sh",
        "install_bin.sh",
        "install_prereq.sh",
        "uninstall_easy.sh",
        "blockcheck2.sh",
        "common/installer.sh",
        "common/elevate.sh",
        "common/linux_daemons.sh",
        "common/linux_fw.sh",
        "common/nft.sh",
        "common/ipt.sh",
        "init.d/",
        "ipset/",
    ]
    return {
        "schemaVersion": 1,
        "snapshotFor": "v0.4_p03_zapret2_1.0.6",
        "generatedBy": "tools/gui_checks/inventory_core.py",
        "coreRoot": "core/zapret2",
        "policy": {
            "mode": "read-only snapshot",
            "doesNotExecuteUpstreamScripts": True,
            "doesNotBuildCore": True,
            "doesNotRequireSudo": True,
            "doesNotAccessNetwork": True,
        },
        "upstream": {
            "name": upstream["upstreamName"],
            "sourceArchive": upstream["sourceArchive"],
            "importedAt": upstream["importedAt"],
            "licensePath": upstream["licensePath"],
            "contentDigestSha256": upstream["contentDigestSha256"],
        },
        "counts": {
            "vendorFileCount": len(files),
            "upstreamImportedFileCount": len(upstream_files),
            "projectLocalCoreFileCount": len(project_local_files),
            "extensionCounts": dict(sorted(extensions.items())),
            "topLevelFileCounts": dict(sorted(top_dirs.items())),
            "sourceDirectoryCounts": dict(sorted(source_dirs.items())),
        },
        "projectLocalCoreFiles": [
            {"path": _rel(path), "reason": PROJECT_LOCAL_CORE_FILES[_rel(path)]}
            for path in project_local_files
        ],
        "notablePaths": {
            "primaryMakefiles": PRIMARY_MAKEFILES,
            "allMakefiles": makefiles,
            "rootScripts": [
                "blockcheck2.sh",
                "install_bin.sh",
                "install_easy.sh",
                "install_prereq.sh",
                "uninstall_easy.sh",
            ],
            "configurationSeeds": ["config.default", "ipset/zapret-hosts-user-exclude.txt.default"],
            "luaScripts": sorted(_rel(path) for path in files if path.suffix.lower() == ".lua"),
            "serviceTemplates": sorted(
                _rel(path)
                for path in files
                if path.suffix.lower() in {".service", ".timer"} or "/systemd/" in _rel(path)
            ),
            "privilegeTouchpoints": privilege_touchpoints,
        },
    }


def compute_build_map() -> dict[str, Any]:
    makefile_targets = {rel_path: _targets_from_makefile(rel_path) for rel_path in PRIMARY_MAKEFILES}
    return {
        "schemaVersion": 1,
        "snapshotFor": "v0.4_p03_zapret2_1.0.6",
        "generatedBy": "tools/gui_checks/inventory_core.py",
        "coreRoot": "core/zapret2",
        "source": "parsed from vendored Makefiles without executing make",
        "safetyPolicy": {
            "automaticChecksMayParseMakefiles": True,
            "automaticChecksMayRunMake": False,
            "automaticChecksMayInstallPackages": False,
            "automaticChecksMayUseSudo": False,
            "automaticChecksMayMutateServicesOrFirewall": False,
        },
        "rootMakefile": {
            "path": "Makefile",
            "delegatedDirectories": ["nfq2", "ip2net", "mdig"],
            "outputDirectory": "binaries/my",
            "targets": makefile_targets["Makefile"],
            "notes": [
                "root all/systemd/android/bsd targets call subdirectory Makefiles",
                "clean removes binaries/my and delegates clean to subdirectories",
            ],
        },
        "makefileTargets": makefile_targets,
        "units": BUILD_UNITS,
        "futureAdapterContract": {
            "firstStep": "present build plan as data in GUI",
            "secondStep": "let owner run local build explicitly",
            "assistantBoundary": "tests validate plans and files; they do not execute host build or privileged install",
        },
    }


def _dump_json(data: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_snapshots() -> None:
    _dump_json(compute_core_inventory(), INVENTORY_PATH)
    _dump_json(compute_build_map(), BUILD_MAP_PATH)


def check_snapshots() -> int:
    expected_inventory = compute_core_inventory()
    expected_build_map = compute_build_map()
    actual_inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    actual_build_map = json.loads(BUILD_MAP_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []
    if actual_inventory != expected_inventory:
        errors.append("CORE_INVENTORY.json не совпадает с текущим деревом core/zapret2")
    if actual_build_map != expected_build_map:
        errors.append("BUILD_MAP.json не совпадает с текущими Makefile")
    if errors:
        for error in errors:
            print(error)
        print("Перегенерация для разработчика: python tools/gui_checks/inventory_core.py --write")
        return 1
    print("Инвентаризация ядра и build map актуальны")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Инвентаризация vendored-ядра zapret2 без сборки и sudo")
    parser.add_argument("--write", action="store_true", help="записать CORE_INVENTORY.json и BUILD_MAP.json")
    parser.add_argument("--check", action="store_true", help="проверить актуальность записанных snapshot-файлов")
    parser.add_argument(
        "--kind",
        choices=["inventory", "build-map"],
        default="inventory",
        help="какой JSON вывести в stdout без записи файлов",
    )
    args = parser.parse_args(argv)
    if args.write:
        write_snapshots()
        return 0
    if args.check:
        return check_snapshots()
    data = compute_core_inventory() if args.kind == "inventory" else compute_build_map()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
