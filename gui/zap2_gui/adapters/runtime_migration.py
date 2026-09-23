"""P02 explicit migration transaction for owned runtime state.

Read-only status never mutates state.  Supported legacy records are migrated
only through detect -> backup -> temp migrate -> validate -> atomic replace ->
receipt.  Unknown/newer schema is refused.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runtime_session import SESSION_MARKER, SESSION_SCHEMA_VERSION, _upgrade_legacy_session_identity
from .runtime_state import atomic_write_json, ensure_runtime_store
from ..project_paths import discover_layout

MIGRATION_SCHEMA_VERSION = 1
MIGRATION_MARKER = "zap2-runtime-migration-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class RuntimeMigrationReceipt:
    state: str
    profile_id: str
    source_schema: int | None
    target_schema: int
    state_path: Path
    backup_path: Path | None
    receipt_path: Path
    message: str

    def to_text(self) -> str:
        return "\n".join([
            f"Runtime MigrationTxn: {self.state}",
            f"profile: {self.profile_id}",
            f"schema: {self.source_schema if self.source_schema is not None else 'none'} -> {self.target_schema}",
            f"state: {self.state_path}",
            f"backup: {self.backup_path if self.backup_path else 'нет'}",
            f"receipt: {self.receipt_path}",
            f"message: {self.message}",
        ])


def migrate_runtime_session_state(root: Path | None = None, profile_id: str = "default") -> RuntimeMigrationReceipt:
    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    state_path = paths.sessions_dir / f"{profile_id}.session.json"
    receipts_dir = paths.root / ".zap2" / "runtime" / "migrations"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipts_dir / f"{profile_id}.session.migration.json"
    if not state_path.is_file():
        receipt = {
            "schemaVersion": MIGRATION_SCHEMA_VERSION, "marker": MIGRATION_MARKER, "state": "not-required",
            "profileId": profile_id, "sourceSchema": None, "targetSchema": SESSION_SCHEMA_VERSION,
            "statePath": str(state_path.relative_to(paths.root)), "backupPath": None, "updatedAt": _utc_now(),
            "message": "session state absent",
        }
        atomic_write_json(receipt_path, receipt)
        return RuntimeMigrationReceipt("not-required", profile_id, None, SESSION_SCHEMA_VERSION, state_path, None, receipt_path, "session state absent")
    try:
        original = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"session migration refused: unreadable state: {exc}") from exc
    if not isinstance(original, dict) or original.get("marker") != SESSION_MARKER:
        raise ValueError("session migration refused: ownership marker mismatch")
    try:
        source_schema = int(original.get("schemaVersion", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("session migration refused: invalid schemaVersion") from exc
    if source_schema > SESSION_SCHEMA_VERSION:
        raise ValueError(f"session migration refused: schema {source_schema} newer than supported {SESSION_SCHEMA_VERSION}")
    if source_schema == SESSION_SCHEMA_VERSION and isinstance(original.get("processIdentity"), dict):
        receipt = {
            "schemaVersion": MIGRATION_SCHEMA_VERSION, "marker": MIGRATION_MARKER, "state": "not-required",
            "profileId": profile_id, "sourceSchema": source_schema, "targetSchema": SESSION_SCHEMA_VERSION,
            "statePath": str(state_path.relative_to(paths.root)), "backupPath": None, "updatedAt": _utc_now(),
            "message": "session state already current",
        }
        atomic_write_json(receipt_path, receipt)
        return RuntimeMigrationReceipt("not-required", profile_id, source_schema, SESSION_SCHEMA_VERSION, state_path, None, receipt_path, "session state already current")

    migrated = _upgrade_legacy_session_identity(original, paths.root)
    if migrated is None:
        raise ValueError("session migration refused: legacy record cannot prove exact pidfile/executable/argv ownership")
    if int(migrated.get("schemaVersion", 0)) != SESSION_SCHEMA_VERSION or not isinstance(migrated.get("processIdentity"), dict):
        raise ValueError("session migration validation failed")

    stamp = _utc_now().replace(":", "").replace("-", "")
    backup_path = state_path.with_name(f"{state_path.name}.pre-p02-{stamp}.bak")
    backup_bytes = state_path.read_bytes()
    backup_path.write_bytes(backup_bytes)
    os.chmod(backup_path, 0o600)
    before_sha = hashlib.sha256(backup_bytes).hexdigest()
    atomic_write_json(state_path, migrated)
    after_sha = _sha256(state_path)
    receipt = {
        "schemaVersion": MIGRATION_SCHEMA_VERSION, "marker": MIGRATION_MARKER, "state": "migrated",
        "profileId": profile_id, "sourceSchema": source_schema, "targetSchema": SESSION_SCHEMA_VERSION,
        "statePath": str(state_path.relative_to(paths.root)), "backupPath": str(backup_path.relative_to(paths.root)),
        "beforeSha256": before_sha, "afterSha256": after_sha, "updatedAt": _utc_now(),
        "validation": "exact pidfile/executable/argv -> processIdentity",
        "message": "legacy session migrated atomically after exact ownership proof",
    }
    atomic_write_json(receipt_path, receipt)
    return RuntimeMigrationReceipt("migrated", profile_id, source_schema, SESSION_SCHEMA_VERSION, state_path, backup_path, receipt_path, receipt["message"])


__all__ = ["RuntimeMigrationReceipt", "migrate_runtime_session_state"]
