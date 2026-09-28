"""Deterministic identity helpers for the shipped zapret2 generation.

P03 treats the pinned upstream source, project overlays/source transforms,
shipping preset corpus and compiled binary as one indivisible generation.
This module is intentionally read-only: it never downloads, builds, installs
or mutates runtime state.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

P03_UPSTREAM_REPO = "bol-van/zapret2"
P03_UPSTREAM_COMMIT = "00f5aaa36de500971faf6db440dd7d8b25672281"
P03_UPSTREAM_VERSION = "1.0.6"
P03_ARCHIVE_SHA256 = "769df14fa4463fbe9744a2aab97e7f1bfe1a2f77a669981f4e6372d7b86d71a9"
P03_FILTER_POLICY_VERSION = "zap2-p03-filter-v1"
TREE_DIGEST_ALGORITHM = "sha256(path-len||path||blob-len||blob)-v1"
OVERLAY_ID = "zap2-p03-generation-overlays-v1"
OVERLAY_RELATIVE_PATH = "core/overlays/zapret2/lua/custom_funcs.lua"
OVERLAY_MANIFEST_RELATIVE_PATH = "core/overlays/zapret2/OVERLAY_MANIFEST.json"
COMPAT_RECEIPT_RELATIVE_PATH = "runtime/preset-compatibility-receipt.json"
SHIPPING_CORPUS_MANIFEST_RELATIVE_PATH = "runtime/shipping-strategy-manifest.json"

# These are project metadata, not files from the filtered upstream generation.
UPSTREAM_METADATA_FILES = frozenset({
    "UPSTREAM_IMPORT.json",
    "UPSTREAM_IMPORT.md",
    "CORE_INVENTORY.json",
    "BUILD_MAP.json",
})

# Outputs produced by the supported Makefiles live inside the vendored source
# tree. They are generation artifacts, not part of the pinned upstream source
# tree digest. Their bytes are bound separately by the build receipt.
BUILD_ARTIFACT_PATHS = frozenset({
    "nfq2/nfqws2",
    "nfq2/dvtws2",
    "nfq2/winws2",
    "nfq2/winws2.exe",
    "mdig/mdig",
    "mdig/mdiga",
    "mdig/mdigx",
    "ip2net/ip2net",
    "ip2net/ip2neta",
    "ip2net/ip2netx",
})


@dataclass(frozen=True)
class GenerationSnapshot:
    upstream_tree_digest: str
    overlay_digest: str
    source_transform_digest: str
    shipping_corpus_digest: str
    compatibility_receipt_digest: str
    c_compat: int | None
    lua_compat: int | None
    upstream_commit: str
    upstream_version: str
    archive_sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_named_blobs(items: Iterable[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, blob in sorted(items, key=lambda row: row[0]):
        nb = name.encode("utf-8")
        digest.update(len(nb).to_bytes(4, "big"))
        digest.update(nb)
        digest.update(len(blob).to_bytes(8, "big"))
        digest.update(blob)
    return digest.hexdigest()


def tree_digest(files: Iterable[Path], base: Path) -> str:
    """Hash a tree by relative path and exact bytes, independent of mtimes."""

    unique = {path.resolve(): path for path in files if path.is_file()}
    return _hash_named_blobs(
        (path.relative_to(base).as_posix(), path.read_bytes())
        for path in unique.values()
    )


def upstream_tree_files(root: Path) -> tuple[Path, ...]:
    core_root = root / "core" / "zapret2"
    result: list[Path] = []
    for path in core_root.rglob("*"):
        if not path.is_file() or path.name in UPSTREAM_METADATA_FILES:
            continue
        rel = path.relative_to(core_root).as_posix()
        if rel in BUILD_ARTIFACT_PATHS or rel.startswith("binaries/my/"):
            continue
        result.append(path)
    return tuple(result)


def upstream_tree_digest(root: Path) -> str:
    core_root = root / "core" / "zapret2"
    return tree_digest(upstream_tree_files(root), core_root)


def _compat_versions(root: Path) -> tuple[int | None, int | None]:
    core_root = root / "core" / "zapret2"
    c_version: int | None = None
    lua_version: int | None = None
    header = core_root / "nfq2" / "nfqws.h"
    lua = core_root / "lua" / "zapret-lib.lua"
    if header.is_file():
        match = re.search(
            r"^\s*#\s*define\s+LUA_COMPAT_VER\s+(\d+)\b",
            header.read_text(encoding="utf-8", errors="replace"),
            re.M,
        )
        if match:
            c_version = int(match.group(1))
    if lua.is_file():
        match = re.search(
            r"^\s*NFQWS2_COMPAT_VER_REQUIRED\s*=\s*(\d+)\b",
            lua.read_text(encoding="utf-8", errors="replace"),
            re.M,
        )
        if match:
            lua_version = int(match.group(1))
    return c_version, lua_version


def load_upstream_manifest(root: Path) -> dict[str, Any]:
    path = root / "core" / "zapret2" / "UPSTREAM_IMPORT.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_overlay_manifest(root: Path) -> dict[str, Any]:
    path = root / OVERLAY_MANIFEST_RELATIVE_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def source_transform_records(root: Path) -> tuple[dict[str, str], ...]:
    manifest = load_overlay_manifest(root)
    rows: list[dict[str, str]] = []
    for raw in manifest.get("sourceTransforms", []):
        if not isinstance(raw, dict):
            continue
        rows.append({
            "id": str(raw.get("id") or ""),
            "targetPath": str(raw.get("targetPath") or ""),
            "overlayPath": str(raw.get("overlayPath") or ""),
            "baseSha256": str(raw.get("baseSha256") or ""),
            "effectiveSha256": str(raw.get("effectiveSha256") or ""),
        })
    return tuple(rows)


def source_transform_digest(root: Path) -> str:
    rows = source_transform_records(root)
    blobs: list[tuple[str, bytes]] = []
    for row in rows:
        spec = json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")
        blobs.append((f"spec:{row['id']}", spec))
        overlay = root / row["overlayPath"]
        if overlay.is_file():
            blobs.append((f"overlay:{row['overlayPath']}", overlay.read_bytes()))
    return _hash_named_blobs(blobs)


def overlay_digest(root: Path) -> str:
    """Bind manifest semantics plus all project-local generation bytes."""

    manifest_path = root / OVERLAY_MANIFEST_RELATIVE_PATH
    manifest = load_overlay_manifest(root)
    blobs: list[tuple[str, bytes]] = [(OVERLAY_MANIFEST_RELATIVE_PATH, manifest_path.read_bytes())]
    for item in manifest.get("files", []):
        if not isinstance(item, dict):
            continue
        rel = str(item.get("path") or "")
        path = root / rel
        if rel and path.is_file():
            blobs.append((rel, path.read_bytes()))
    for item in manifest.get("sourceTransforms", []):
        if not isinstance(item, dict):
            continue
        rel = str(item.get("overlayPath") or "")
        path = root / rel
        if rel and path.is_file():
            blobs.append((rel, path.read_bytes()))
    return _hash_named_blobs(blobs)


def _strategy_runtime_args(root: Path, rel_strategy_path: str) -> tuple[str, ...]:
    data = json.loads((root / rel_strategy_path).read_text(encoding="utf-8"))
    legacy = tuple(str(item) for item in data.get("runtimeArgs", []))
    preset_path = str(data.get("presetPath") or "").strip()
    if not preset_path:
        return legacy
    preset = root / preset_path
    args = tuple(
        line.strip()
        for line in preset.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if legacy and legacy != args:
        raise ValueError(f"presetPath/runtimeArgs mismatch: {rel_strategy_path}")
    return args


def shipping_corpus_records(root: Path) -> tuple[dict[str, Any], ...]:
    manifest_path = root / SHIPPING_CORPUS_MANIFEST_RELATIVE_PATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 1 or manifest.get("marker") != "zap2-p03-shipping-strategy-corpus-v1":
        raise ValueError("P03 shipping corpus manifest schema/marker mismatch")
    records: list[dict[str, Any]] = []
    for rel_path in manifest.get("strategyFiles", []):
        rel = str(rel_path)
        data = json.loads((root / rel).read_text(encoding="utf-8"))
        args = _strategy_runtime_args(root, rel)
        records.append(
            {
                "id": str(data["id"]),
                "strategyPath": rel,
                "presetPath": str(data.get("presetPath") or ""),
                "runtimeArgs": list(args),
            }
        )
    return tuple(records)


def shipping_corpus_digest(root: Path) -> str:
    payload = json.dumps(
        shipping_corpus_records(root),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compatibility_receipt_digest(root: Path) -> str:
    path = root / COMPAT_RECEIPT_RELATIVE_PATH
    return sha256_file(path) if path.is_file() else ""


def generation_snapshot(root: Path) -> GenerationSnapshot:
    root = root.resolve()
    manifest = load_upstream_manifest(root)
    c_compat, lua_compat = _compat_versions(root)
    return GenerationSnapshot(
        upstream_tree_digest=upstream_tree_digest(root),
        overlay_digest=overlay_digest(root),
        source_transform_digest=source_transform_digest(root),
        shipping_corpus_digest=shipping_corpus_digest(root),
        compatibility_receipt_digest=compatibility_receipt_digest(root),
        c_compat=c_compat,
        lua_compat=lua_compat,
        upstream_commit=str(manifest.get("upstreamCommit") or ""),
        upstream_version=str(manifest.get("upstreamVersion") or ""),
        archive_sha256=str(manifest.get("sourceArchiveSha256") or ""),
    )


def _validate_overlay_manifest(root: Path, errors: list[str]) -> None:
    try:
        overlay_manifest = load_overlay_manifest(root)
    except Exception as exc:
        errors.append(f"overlay manifest unreadable: {exc}")
        return
    if overlay_manifest.get("schemaVersion") != 2:
        errors.append("overlay manifest schema mismatch")
    if overlay_manifest.get("overlayId") != OVERLAY_ID:
        errors.append("overlay id mismatch")
    if overlay_manifest.get("targetUpstreamCommit") != P03_UPSTREAM_COMMIT:
        errors.append("overlay target upstream commit mismatch")
    if overlay_manifest.get("targetUpstreamVersion") != P03_UPSTREAM_VERSION:
        errors.append("overlay target upstream version mismatch")
    if int(overlay_manifest.get("luaCompat", -1)) != 6:
        errors.append("overlay luaCompat must be 6")

    core_root = root / "core" / "zapret2"
    for item in overlay_manifest.get("files", []):
        if not isinstance(item, dict):
            errors.append("overlay file entry is not an object")
            continue
        rel = str(item.get("path") or "")
        path = root / rel
        if not rel or not path.is_file():
            errors.append(f"overlay file missing: {rel}")
            continue
        if path.is_relative_to(core_root):
            errors.append(f"project-local overlay is hidden inside upstream tree: {rel}")
        if item.get("sha256") != sha256_file(path):
            errors.append(f"overlay file hash mismatch: {rel}")

    seen_targets: set[str] = set()
    transforms = overlay_manifest.get("sourceTransforms", [])
    if not isinstance(transforms, list) or not transforms:
        errors.append("required P03 source transform set is empty")
        return
    for item in transforms:
        if not isinstance(item, dict):
            errors.append("source transform entry is not an object")
            continue
        transform_id = str(item.get("id") or "")
        target_rel = str(item.get("targetPath") or "")
        overlay_rel = str(item.get("overlayPath") or "")
        if not transform_id or not target_rel or not overlay_rel:
            errors.append("source transform has empty id/target/overlay path")
            continue
        if target_rel in seen_targets:
            errors.append(f"duplicate source transform target: {target_rel}")
        seen_targets.add(target_rel)
        target = core_root / target_rel
        overlay = root / overlay_rel
        if not target.is_file():
            errors.append(f"source transform base target missing: {target_rel}")
            continue
        if not overlay.is_file():
            errors.append(f"source transform overlay missing: {overlay_rel}")
            continue
        if overlay.is_relative_to(core_root):
            errors.append(f"source transform overlay must stay outside upstream tree: {overlay_rel}")
        base_hash = sha256_file(target)
        effective_hash = sha256_file(overlay)
        if item.get("baseSha256") != base_hash:
            errors.append(f"source transform base hash mismatch: {target_rel}")
        if item.get("effectiveSha256") != effective_hash:
            errors.append(f"source transform effective hash mismatch: {overlay_rel}")


def generation_identity_errors(root: Path) -> tuple[str, ...]:
    """Return deterministic generation errors without running upstream code."""

    root = root.resolve()
    errors: list[str] = []
    try:
        manifest = load_upstream_manifest(root)
    except Exception as exc:
        return (f"upstream manifest unreadable: {exc}",)

    expected_manifest = {
        "upstreamName": P03_UPSTREAM_REPO,
        "upstreamCommit": P03_UPSTREAM_COMMIT,
        "upstreamVersion": P03_UPSTREAM_VERSION,
        "sourceArchiveSha256": P03_ARCHIVE_SHA256,
        "filterPolicyVersion": P03_FILTER_POLICY_VERSION,
    }
    for key, expected in expected_manifest.items():
        if manifest.get(key) != expected:
            errors.append(f"upstream manifest {key} mismatch: {manifest.get(key)!r} != {expected!r}")

    actual_tree = upstream_tree_digest(root)
    recorded_tree = str(manifest.get("filteredTreeSha256") or manifest.get("contentDigestSha256") or "")
    if not recorded_tree or recorded_tree != actual_tree:
        errors.append("filtered upstream tree digest mismatch")
    if int(manifest.get("importedFileCount", -1)) != len(upstream_tree_files(root)):
        errors.append("filtered upstream file count mismatch")

    core_local_overlay = root / "core" / "zapret2" / "lua" / "custom_funcs.lua"
    if core_local_overlay.exists():
        errors.append("project-local custom_funcs.lua is still hidden inside upstream tree")

    _validate_overlay_manifest(root, errors)

    c_compat, lua_compat = _compat_versions(root)
    if c_compat != 6 or lua_compat != 6:
        errors.append(f"Lua compatibility generation mismatch: C={c_compat}, Lua={lua_compat}, expected=6")

    receipt_path = root / COMPAT_RECEIPT_RELATIVE_PATH
    if not receipt_path.is_file():
        errors.append("preset compatibility receipt missing")
    else:
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            corpus = shipping_corpus_digest(root)
            if receipt.get("candidateCorpusSha256") != corpus:
                errors.append("shipping preset corpus differs from compatibility receipt")
            if receipt.get("targetUpstreamCommit") != P03_UPSTREAM_COMMIT:
                errors.append("compatibility receipt target commit mismatch")
            shipping_manifest = receipt.get("shippingCorpusManifest")
            manifest_path = root / SHIPPING_CORPUS_MANIFEST_RELATIVE_PATH
            if not isinstance(shipping_manifest, dict):
                errors.append("compatibility receipt shipping corpus manifest evidence missing")
            elif shipping_manifest.get("path") != SHIPPING_CORPUS_MANIFEST_RELATIVE_PATH:
                errors.append("compatibility receipt shipping corpus manifest path mismatch")
            elif not manifest_path.is_file() or shipping_manifest.get("sha256") != sha256_file(manifest_path):
                errors.append("shipping corpus manifest differs from compatibility receipt")
            entries = receipt.get("strategies", [])
            catalog_ids = {row["id"] for row in shipping_corpus_records(root)}
            receipt_ids = {str(row.get("id")) for row in entries if isinstance(row, dict)}
            if catalog_ids != receipt_ids:
                errors.append("compatibility receipt does not classify 100% of shipping strategies")
            bad = [
                str(row.get("id"))
                for row in entries
                if isinstance(row, dict)
                and str(row.get("classification")) not in {
                    "equivalent",
                    "equivalent-local-overlay-relocation",
                    "changed-transformable",
                    "changed-unsupported",
                }
            ]
            if bad:
                errors.append("unclassified shipping strategies: " + ", ".join(sorted(bad)))
        except Exception as exc:
            errors.append(f"preset compatibility receipt unreadable: {exc}")

    return tuple(errors)
