"""Stable runtime ownership identity shared by firewall/process lifecycle code.

The Linux network namespace is global while z2guiflin state lives inside a
workspace.  Resource names therefore must include a workspace identity instead
of assuming that ``profile_id`` alone is unique.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

OWNER_SCHEMA_VERSION = 1
_OWNER_TOKEN_RE = re.compile(r"[^a-z0-9_]+")


def _parse_non_negative_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value, 10)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def runtime_owner_uid(root: Path) -> tuple[int, str]:
    """Return the desktop owner UID consistently before and after sudo."""

    sudo_uid = _parse_non_negative_int(os.environ.get("SUDO_UID"))
    if sudo_uid is not None:
        return sudo_uid, "sudo-owner"
    getuid = getattr(os, "getuid", None)
    if getuid is not None:
        uid = int(getuid())
        if uid != 0:
            return uid, "current-user"
    try:
        stat_uid = int(root.resolve().stat().st_uid)
    except OSError:
        stat_uid = 0
    if stat_uid != 0:
        return stat_uid, "workspace-owner"
    return 0, "root-fallback"


def _profile_token(profile_id: str) -> str:
    token = _OWNER_TOKEN_RE.sub("_", profile_id.strip().lower()).strip("_")
    return token or "default"


def workspace_identity_digest(root: Path) -> str:
    """Return a stable non-secret digest of the canonical workspace path."""

    canonical = str(root.resolve()).encode("utf-8", errors="surrogateescape")
    return hashlib.sha256(canonical).hexdigest()[:12]


@dataclass(frozen=True)
class RuntimeOwnerIdentity:
    uid: int
    uid_source: str
    workspace_digest: str
    profile_id: str
    profile_token: str

    @property
    def owner_key(self) -> str:
        return f"u{self.uid}-{self.workspace_digest}-{self.profile_token}"

    @property
    def marker(self) -> str:
        return f"zap2-owner:{self.owner_key}"

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": OWNER_SCHEMA_VERSION,
            "uid": self.uid,
            "uidSource": self.uid_source,
            "workspaceDigest": self.workspace_digest,
            "profileId": self.profile_id,
            "ownerKey": self.owner_key,
            "marker": self.marker,
        }


def runtime_owner_identity(root: Path, profile_id: str = "default") -> RuntimeOwnerIdentity:
    uid, uid_source = runtime_owner_uid(root)
    return RuntimeOwnerIdentity(
        uid=uid,
        uid_source=uid_source,
        workspace_digest=workspace_identity_digest(root),
        profile_id=profile_id,
        profile_token=_profile_token(profile_id),
    )


def owned_nft_table_name(root: Path, profile_id: str = "default", *, prefix: str = "zap2") -> str:
    """Return an nft identifier unique to owner UID + workspace + profile."""

    identity = runtime_owner_identity(root, profile_id)
    # Keep names short/readable and within conservative nft identifier limits.
    return f"{prefix}_u{identity.uid}_{identity.workspace_digest[:8]}_{identity.profile_token[:24]}"


__all__ = [
    "OWNER_SCHEMA_VERSION",
    "RuntimeOwnerIdentity",
    "owned_nft_table_name",
    "runtime_owner_identity",
    "runtime_owner_uid",
    "workspace_identity_digest",
]
