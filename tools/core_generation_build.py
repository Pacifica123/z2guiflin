#!/usr/bin/env python3
"""Build the P03 zapret2 generation from a staged, transformed source copy.

The canonical ``core/zapret2`` tree stays byte-exact to the pinned filtered
upstream candidate. Project-local C source transforms live under
``core/overlays/zapret2`` and are applied only to a fresh staging tree.
Successful artifacts are copied atomically back to the canonical output paths.
No sudo, package installation, network, firewall or service mutation occurs.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "gui"
if str(GUI) not in sys.path:
    sys.path.insert(0, str(GUI))

from zap2_gui.adapters.core_generation import (  # noqa: E402
    BUILD_ARTIFACT_PATHS,
    UPSTREAM_METADATA_FILES,
    generation_identity_errors,
    generation_snapshot,
    load_overlay_manifest,
    sha256_file,
)

BUILD_ADAPTER_ID = "zap2-p03-staged-generation-build-v1"
STAGE_BASE = ROOT / ".zap2" / "build" / "core-generation"
CORE_ROOT = ROOT / "core" / "zapret2"
BUILD_MAP = CORE_ROOT / "BUILD_MAP.json"


def _build_map() -> dict:
    return json.loads(BUILD_MAP.read_text(encoding="utf-8"))


def _units() -> dict[str, dict]:
    return {str(item["name"]): item for item in _build_map().get("units", [])}


def _artifact_paths(target: str) -> tuple[str, ...]:
    units = _units()
    selected = units.values() if target == "all" else (units[target],)
    return tuple(str(rel) for unit in selected for rel in unit.get("linuxOutputs", []))


def _remove_canonical_artifacts() -> None:
    for rel in BUILD_ARTIFACT_PATHS:
        path = CORE_ROOT / rel
        if path.is_file() or path.is_symlink():
            path.unlink()
    binaries_my = CORE_ROOT / "binaries" / "my"
    if binaries_my.exists():
        shutil.rmtree(binaries_my)


def _prepare_stage(stage: Path) -> None:
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(CORE_ROOT, stage, symlinks=True)
    for name in UPSTREAM_METADATA_FILES:
        path = stage / name
        if path.exists():
            path.unlink()
    for rel in BUILD_ARTIFACT_PATHS:
        path = stage / rel
        if path.is_file() or path.is_symlink():
            path.unlink()
    binaries_my = stage / "binaries" / "my"
    if binaries_my.exists():
        shutil.rmtree(binaries_my)


def _apply_transforms(stage: Path) -> tuple[str, ...]:
    manifest = load_overlay_manifest(ROOT)
    applied: list[str] = []
    for raw in manifest.get("sourceTransforms", []):
        transform_id = str(raw["id"])
        target_rel = str(raw["targetPath"])
        overlay_rel = str(raw["overlayPath"])
        target = stage / target_rel
        overlay = ROOT / overlay_rel
        if not target.is_file() or sha256_file(target) != str(raw["baseSha256"]):
            raise RuntimeError(f"source transform base mismatch: {transform_id}:{target_rel}")
        if not overlay.is_file() or sha256_file(overlay) != str(raw["effectiveSha256"]):
            raise RuntimeError(f"source transform overlay mismatch: {transform_id}:{overlay_rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(overlay, target)
        if sha256_file(target) != str(raw["effectiveSha256"]):
            raise RuntimeError(f"source transform application mismatch: {transform_id}:{target_rel}")
        applied.append(transform_id)
    return tuple(applied)


def _make_command(target: str, stage: Path) -> tuple[Path, tuple[str, ...]]:
    if target == "all":
        return stage, ("make", "all")
    unit = _units()[target]
    makefile = Path(str(unit["makefile"]))
    return stage / makefile.parent, ("make", target)


def _atomic_copy(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise RuntimeError(f"expected build artifact missing: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.p03-", dir=str(dst.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(src, tmp)
        os.chmod(tmp, src.stat().st_mode & 0o777)
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()


def build(target: str) -> int:
    if target == "clean":
        _remove_canonical_artifacts()
        if STAGE_BASE.exists():
            shutil.rmtree(STAGE_BASE)
        return 0

    errors = generation_identity_errors(ROOT)
    if errors:
        raise RuntimeError("P03 generation identity invalid before build: " + "; ".join(errors))

    snapshot = generation_snapshot(ROOT)
    stage_id = f"{snapshot.upstream_tree_digest[:12]}-{snapshot.source_transform_digest[:12]}"
    stage = STAGE_BASE / stage_id / "source"
    stage.parent.mkdir(parents=True, exist_ok=True)
    _prepare_stage(stage)
    applied = _apply_transforms(stage)

    cwd, argv = _make_command(target, stage)
    print(f"build-adapter: {BUILD_ADAPTER_ID}")
    print(f"upstream-tree: {snapshot.upstream_tree_digest}")
    print(f"source-transform-digest: {snapshot.source_transform_digest}")
    print(f"transforms: {','.join(applied) if applied else 'none'}")
    print(f"stage: {stage}")
    print(f"command: cd {cwd} && {' '.join(argv)}")
    completed = subprocess.run(list(argv), cwd=str(cwd), check=False)
    if completed.returncode != 0:
        return completed.returncode

    for rel in _artifact_paths(target):
        _atomic_copy(stage / rel, CORE_ROOT / rel)
        print(f"artifact: {rel} sha256={sha256_file(CORE_ROOT / rel)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("all", "nfqws2", "ip2net", "mdig", "clean"))
    args = parser.parse_args()
    try:
        return build(args.target)
    except Exception as exc:
        print(f"P03 build blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
