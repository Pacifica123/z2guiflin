"""Reproducibility and compatibility receipt for the vendored zapret2 core.

The receipt is deliberately local runtime metadata. It does not download or
update upstream and it is not a trust signature. Its purpose is to detect a
mixed source/Lua/binary bundle before privileged runtime start.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .runtime_state import atomic_write_json, ensure_runtime_store

RECEIPT_SCHEMA_VERSION = 1
RECEIPT_MARKER = "zap2-core-build-receipt-v1"


@dataclass(frozen=True)
class CoreProvenanceStatus:
    state: str  # verified | unknown | mismatch
    message: str
    receipt_path: Path
    source_digest: str
    lua_digest: str
    c_compat: int | None
    lua_compat: int | None

    @property
    def hard_error(self) -> bool:
        return self.state == "mismatch"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_digest(files: Iterable[Path], base: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((p for p in files if p.is_file()), key=lambda item: str(item.relative_to(base))):
        rel = path.relative_to(base).as_posix().encode("utf-8")
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        blob = path.read_bytes()
        digest.update(len(blob).to_bytes(8, "big"))
        digest.update(blob)
    return digest.hexdigest()


def _source_files(core_root: Path) -> tuple[Path, ...]:
    patterns = ("nfq2/**/*.c", "nfq2/**/*.h", "nfq2/**/Makefile", "Makefile")
    result: list[Path] = []
    for pattern in patterns:
        result.extend(core_root.glob(pattern))
    return tuple(dict.fromkeys(path for path in result if path.is_file()))


def _lua_files(core_root: Path) -> tuple[Path, ...]:
    return tuple(path for path in core_root.glob("lua/**/*.lua") if path.is_file())


def _compat_versions(core_root: Path) -> tuple[int | None, int | None]:
    c_version: int | None = None
    lua_version: int | None = None
    header = core_root / "nfq2" / "nfqws.h"
    lua = core_root / "lua" / "zapret-lib.lua"
    try:
        match = re.search(r"^\s*#\s*define\s+LUA_COMPAT_VER\s+(\d+)\b", header.read_text(encoding="utf-8", errors="replace"), re.M)
        if match:
            c_version = int(match.group(1))
    except OSError:
        pass
    try:
        match = re.search(r"^\s*NFQWS2_COMPAT_VER_REQUIRED\s*=\s*(\d+)\b", lua.read_text(encoding="utf-8", errors="replace"), re.M)
        if match:
            lua_version = int(match.group(1))
    except OSError:
        pass
    return c_version, lua_version


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
    revision = data.get("upstreamRevision") or data.get("revision") or data.get("commit") or data.get("tag")
    return {
        "status": "recorded",
        "sourceArchive": data.get("sourceArchive"),
        "contentDigest": data.get("contentDigest"),
        "upstreamRevision": revision or "unknown",
    }


def write_core_build_receipt(root: Path, artifact_paths: Iterable[Path], build_target: str) -> Path:
    root = root.resolve()
    core_root = root / "core" / "zapret2"
    source_digest = _tree_digest(_source_files(core_root), core_root)
    lua_digest = _tree_digest(_lua_files(core_root), core_root)
    c_compat, lua_compat = _compat_versions(core_root)
    artifacts = []
    for path in artifact_paths:
        path = path.resolve()
        if path.is_file():
            artifacts.append({
                "path": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
                "sha256": _sha256_file(path),
                "sizeBytes": path.stat().st_size,
            })
    receipt = {
        "schemaVersion": RECEIPT_SCHEMA_VERSION,
        "marker": RECEIPT_MARKER,
        "createdAt": _utc_now(),
        "buildTarget": build_target,
        "sourceDigestSha256": source_digest,
        "luaDigestSha256": lua_digest,
        "compat": {"nfqwsHeader": c_compat, "zapretLuaRequired": lua_compat},
        "artifacts": artifacts,
        "upstreamImport": _upstream_import(core_root),
        "meaning": "local reproducibility receipt; not a trust signature",
    }
    path = _receipt_path(root)
    atomic_write_json(path, receipt)
    return path


def verify_core_bundle(root: Path, required_binary: Path | None = None) -> CoreProvenanceStatus:
    root = root.resolve()
    core_root = root / "core" / "zapret2"
    receipt_path = _receipt_path(root)
    source_digest = _tree_digest(_source_files(core_root), core_root)
    lua_digest = _tree_digest(_lua_files(core_root), core_root)
    c_compat, lua_compat = _compat_versions(core_root)

    if c_compat is not None and lua_compat is not None and c_compat != lua_compat:
        return CoreProvenanceStatus(
            "mismatch",
            f"zapret2 core/Lua compatibility mismatch: nfqws={c_compat}, Lua requires={lua_compat}",
            receipt_path,
            source_digest,
            lua_digest,
            c_compat,
            lua_compat,
        )
    if not receipt_path.is_file():
        return CoreProvenanceStatus(
            "unknown",
            "core build receipt отсутствует; текущая C/Lua compat пара не противоречит друг другу, происхождение binary не подтверждено",
            receipt_path,
            source_digest,
            lua_digest,
            c_compat,
            lua_compat,
        )
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CoreProvenanceStatus("mismatch", "core build receipt повреждён/нечитаем", receipt_path, source_digest, lua_digest, c_compat, lua_compat)
    if receipt.get("marker") != RECEIPT_MARKER:
        return CoreProvenanceStatus("mismatch", "core build receipt имеет неизвестный marker", receipt_path, source_digest, lua_digest, c_compat, lua_compat)
    if receipt.get("sourceDigestSha256") != source_digest:
        return CoreProvenanceStatus("mismatch", "core sources изменились после recorded build; требуется пересборка", receipt_path, source_digest, lua_digest, c_compat, lua_compat)
    if receipt.get("luaDigestSha256") != lua_digest:
        return CoreProvenanceStatus("mismatch", "zapret2 Lua bundle изменился после recorded build; требуется согласованная пересборка", receipt_path, source_digest, lua_digest, c_compat, lua_compat)

    if required_binary is not None and required_binary.is_file():
        rel = str(required_binary.resolve().relative_to(root)) if required_binary.resolve().is_relative_to(root) else str(required_binary.resolve())
        expected = next((item for item in receipt.get("artifacts", []) if item.get("path") == rel), None)
        if expected is None:
            return CoreProvenanceStatus("unknown", f"binary {rel} не записан в build receipt", receipt_path, source_digest, lua_digest, c_compat, lua_compat)
        if expected.get("sha256") != _sha256_file(required_binary):
            return CoreProvenanceStatus("mismatch", f"binary {rel} отличается от build receipt; требуется пересборка", receipt_path, source_digest, lua_digest, c_compat, lua_compat)
    return CoreProvenanceStatus("verified", "core sources, Lua compatibility and binary match local build receipt", receipt_path, source_digest, lua_digest, c_compat, lua_compat)
