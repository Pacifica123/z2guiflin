"""Build/generation provenance for the vendored zapret2 core.

P03 makes the build receipt bind the whole executable generation: exact
filtered upstream source, upstream Lua, project-local overlays, the classified
shipping preset corpus and produced binaries.  The receipt is local evidence,
not a trust signature and not a downloader/updater.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .core_generation import (
    GenerationSnapshot,
    generation_identity_errors,
    generation_snapshot,
    load_upstream_manifest,
    tree_digest,
)
from .runtime_state import atomic_write_json, ensure_runtime_store

RECEIPT_SCHEMA_VERSION = 2
RECEIPT_MARKER = "zap2-core-generation-build-receipt-v2"


@dataclass(frozen=True)
class CoreProvenanceStatus:
    state: str  # verified | unknown | mismatch
    message: str
    receipt_path: Path
    source_digest: str
    lua_digest: str
    c_compat: int | None
    lua_compat: int | None
    upstream_tree_digest: str = ""
    overlay_digest: str = ""
    shipping_corpus_digest: str = ""

    @property
    def hard_error(self) -> bool:
        return self.state == "mismatch"

    @property
    def runtime_ready(self) -> bool:
        """P03 runtime may start only from a fully verified generation."""

        return self.state == "verified"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_files(core_root: Path) -> tuple[Path, ...]:
    patterns = ("nfq2/**/*.c", "nfq2/**/*.h", "nfq2/**/Makefile", "Makefile")
    result: list[Path] = []
    for pattern in patterns:
        result.extend(core_root.glob(pattern))
    return tuple(dict.fromkeys(path for path in result if path.is_file()))


def _lua_files(core_root: Path) -> tuple[Path, ...]:
    return tuple(path for path in core_root.glob("lua/**/*.lua") if path.is_file())


def _receipt_path(root: Path) -> Path:
    return ensure_runtime_store(root).root / ".zap2" / "runtime" / "core-build-receipt.json"


def _upstream_import(core_root: Path) -> dict[str, Any]:
    path = core_root / "UPSTREAM_IMPORT.json"
    if not path.is_file():
        return {"status": "missing"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unreadable"}
    return {
        "status": "recorded",
        "upstreamName": data.get("upstreamName"),
        "upstreamCommit": data.get("upstreamCommit") or "unknown",
        "upstreamVersion": data.get("upstreamVersion") or "unknown",
        "sourceArchive": data.get("sourceArchive"),
        "sourceArchiveSha256": data.get("sourceArchiveSha256"),
        "filteredTreeSha256": data.get("filteredTreeSha256") or data.get("contentDigestSha256"),
        "filterPolicyVersion": data.get("filterPolicyVersion"),
    }


def _generation_dict(snapshot: GenerationSnapshot) -> dict[str, Any]:
    return {
        "upstreamTreeDigestSha256": snapshot.upstream_tree_digest,
        "overlayDigestSha256": snapshot.overlay_digest,
        "sourceTransformDigestSha256": snapshot.source_transform_digest,
        "shippingCorpusSha256": snapshot.shipping_corpus_digest,
        "presetCompatibilityReceiptSha256": snapshot.compatibility_receipt_digest,
        "compat": {"nfqwsHeader": snapshot.c_compat, "zapretLuaRequired": snapshot.lua_compat},
        "upstream": {
            "commit": snapshot.upstream_commit,
            "version": snapshot.upstream_version,
            "archiveSha256": snapshot.archive_sha256,
        },
    }


def write_core_build_receipt(root: Path, artifact_paths: Iterable[Path], build_target: str) -> Path:
    root = root.resolve()
    errors = generation_identity_errors(root)
    if errors:
        raise ValueError("cannot write core generation receipt: " + "; ".join(errors))

    core_root = root / "core" / "zapret2"
    source_digest = tree_digest(_source_files(core_root), core_root)
    lua_digest = tree_digest(_lua_files(core_root), core_root)
    snapshot = generation_snapshot(root)
    artifacts = []
    for path in artifact_paths:
        path = path.resolve()
        if path.is_file():
            artifacts.append(
                {
                    "path": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
                    "sha256": _sha256_file(path),
                    "sizeBytes": path.stat().st_size,
                }
            )
    def first_line(argv: list[str]) -> str:
        try:
            completed = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return "unavailable"
        return (completed.stdout or "").splitlines()[0].strip() if (completed.stdout or "").splitlines() else "unknown"

    build_adapter = root / "tools" / "core_generation_build.py"
    build_evidence = {
        "adapter": "tools/core_generation_build.py",
        "adapterSha256": _sha256_file(build_adapter) if build_adapter.is_file() else None,
        "target": build_target,
        "sourceTransformDigestSha256": snapshot.source_transform_digest,
        "toolchain": {
            "python": platform.python_version(),
            "make": first_line(["make", "--version"]),
            "cc": first_line(["cc", "--version"]),
            "platform": platform.platform(),
        },
        "environmentFlags": {
            "CFLAGS": os.environ.get("CFLAGS", ""),
            "CPPFLAGS": os.environ.get("CPPFLAGS", ""),
            "LDFLAGS": os.environ.get("LDFLAGS", ""),
        },
        "note": "production build path stages exact upstream, applies verified source transforms outside the upstream tree, then atomically publishes artifacts",
    }
    receipt = {
        "schemaVersion": RECEIPT_SCHEMA_VERSION,
        "marker": RECEIPT_MARKER,
        "createdAt": _utc_now(),
        "buildTarget": build_target,
        "sourceDigestSha256": source_digest,
        "luaDigestSha256": lua_digest,
        "generation": _generation_dict(snapshot),
        "build": build_evidence,
        "artifacts": artifacts,
        "upstreamImport": _upstream_import(core_root),
        "meaning": "local whole-generation reproducibility receipt; not a trust signature",
    }
    path = _receipt_path(root)
    atomic_write_json(path, receipt)
    return path


def _status(
    state: str,
    message: str,
    receipt_path: Path,
    source_digest: str,
    lua_digest: str,
    snapshot: GenerationSnapshot | None,
) -> CoreProvenanceStatus:
    return CoreProvenanceStatus(
        state=state,
        message=message,
        receipt_path=receipt_path,
        source_digest=source_digest,
        lua_digest=lua_digest,
        c_compat=None if snapshot is None else snapshot.c_compat,
        lua_compat=None if snapshot is None else snapshot.lua_compat,
        upstream_tree_digest="" if snapshot is None else snapshot.upstream_tree_digest,
        overlay_digest="" if snapshot is None else snapshot.overlay_digest,
        shipping_corpus_digest="" if snapshot is None else snapshot.shipping_corpus_digest,
    )


def verify_core_bundle(root: Path, required_binary: Path | None = None) -> CoreProvenanceStatus:
    root = root.resolve()
    core_root = root / "core" / "zapret2"
    receipt_path = _receipt_path(root)
    source_digest = tree_digest(_source_files(core_root), core_root)
    lua_digest = tree_digest(_lua_files(core_root), core_root)

    identity_errors = generation_identity_errors(root)
    try:
        snapshot = generation_snapshot(root)
    except Exception as exc:
        snapshot = None
        identity_errors = (*identity_errors, f"generation snapshot unreadable: {exc}")
    if identity_errors:
        return _status(
            "mismatch",
            "MIXED_GENERATION: " + "; ".join(identity_errors),
            receipt_path,
            source_digest,
            lua_digest,
            snapshot,
        )
    assert snapshot is not None
    if snapshot.c_compat != snapshot.lua_compat:
        return _status(
            "mismatch",
            f"zapret2 core/Lua compatibility mismatch: nfqws={snapshot.c_compat}, Lua requires={snapshot.lua_compat}",
            receipt_path,
            source_digest,
            lua_digest,
            snapshot,
        )
    if not receipt_path.is_file():
        return _status(
            "unknown",
            "whole-generation build receipt отсутствует; clean build обязателен до runtime start",
            receipt_path,
            source_digest,
            lua_digest,
            snapshot,
        )
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _status("mismatch", "core generation build receipt повреждён/нечитаем", receipt_path, source_digest, lua_digest, snapshot)
    if receipt.get("schemaVersion") != RECEIPT_SCHEMA_VERSION or receipt.get("marker") != RECEIPT_MARKER:
        return _status(
            "mismatch",
            "legacy/unknown core build receipt cannot prove the P03 whole generation; clean rebuild required",
            receipt_path,
            source_digest,
            lua_digest,
            snapshot,
        )
    if receipt.get("sourceDigestSha256") != source_digest:
        return _status("mismatch", "core C sources changed after recorded build; rebuild required", receipt_path, source_digest, lua_digest, snapshot)
    if receipt.get("luaDigestSha256") != lua_digest:
        return _status("mismatch", "upstream Lua bundle changed after recorded build; rebuild required", receipt_path, source_digest, lua_digest, snapshot)

    expected_generation = _generation_dict(snapshot)
    if receipt.get("generation") != expected_generation:
        return _status(
            "mismatch",
            "MIXED_GENERATION: upstream/overlay/preset compatibility generation differs from build receipt",
            receipt_path,
            source_digest,
            lua_digest,
            snapshot,
        )
    build = receipt.get("build")
    if not isinstance(build, dict):
        return _status("mismatch", "P03 build evidence missing from generation receipt", receipt_path, source_digest, lua_digest, snapshot)
    if build.get("adapter") != "tools/core_generation_build.py":
        return _status("mismatch", "P03 build receipt does not name the staged generation build adapter", receipt_path, source_digest, lua_digest, snapshot)
    if build.get("sourceTransformDigestSha256") != snapshot.source_transform_digest:
        return _status("mismatch", "MIXED_GENERATION: build source-transform evidence differs from current generation", receipt_path, source_digest, lua_digest, snapshot)

    if required_binary is not None:
        if not required_binary.is_file():
            return _status("mismatch", f"required binary missing: {required_binary}", receipt_path, source_digest, lua_digest, snapshot)
        resolved = required_binary.resolve()
        rel = str(resolved.relative_to(root)) if resolved.is_relative_to(root) else str(resolved)
        expected = next((item for item in receipt.get("artifacts", []) if item.get("path") == rel), None)
        if expected is None:
            return _status("unknown", f"binary {rel} is not recorded in generation build receipt", receipt_path, source_digest, lua_digest, snapshot)
        if expected.get("sha256") != _sha256_file(required_binary):
            return _status("mismatch", f"binary {rel} differs from generation build receipt; rebuild required", receipt_path, source_digest, lua_digest, snapshot)

    manifest = load_upstream_manifest(root)
    return _status(
        "verified",
        f"whole generation verified: {manifest.get('upstreamVersion')}@{str(manifest.get('upstreamCommit'))[:7]} + overlay + shipping corpus + binary",
        receipt_path,
        source_digest,
        lua_digest,
        snapshot,
    )
