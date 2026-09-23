"""Immutable runtime input inventory used by P02 privileged execution.

The pre-P02 plan hash described *which* files nfqws2 would read but did not bind
those files' bytes.  A confirmed plan could therefore survive a later edit to a
Lua file, hostlist or binary.  P02 makes the bytes part of the plan evidence so
post-confirm mutation changes the plan hash and the bounded root executor can
revalidate the same digests before it copies anything into its root-owned run
bundle.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from .runtime_owner import runtime_owner_gid, runtime_owner_uid
from .runtime_queue import resolve_runtime_queue
from .strategy_file_inputs import split_strategy_file_arg
from .runtime_plan_generator import GeneratedRuntimePlan

ARTIFACT_DIGEST_SCHEMA_VERSION = 1


def file_sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _assert_no_symlink_components(root: Path, candidate: Path) -> None:
    root = root.resolve()
    try:
        rel = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"runtime file dependency leaves workspace: {candidate}") from exc
    current = root
    for part in rel.parts:
        current = current / part
        try:
            if current.is_symlink():
                raise ValueError(f"runtime file dependency contains symlink component: {current}")
        except OSError as exc:
            raise ValueError(f"runtime file dependency cannot be inspected safely: {current}: {exc}") from exc


def _resolve_workspace_file(root: Path, raw: str) -> Path:
    value = raw.strip().lstrip("@").replace("\\", "/")
    if not value:
        raise ValueError("runtime file dependency has an empty path")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"runtime file dependency leaves workspace: {raw}")
    root = root.resolve()
    lexical = root / candidate
    _assert_no_symlink_components(root, lexical)
    resolved = lexical.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"runtime file dependency leaves workspace: {raw}") from exc
    return lexical


def _runtime_arg_file_ref(arg: str) -> tuple[str, str] | None:
    parsed = split_strategy_file_arg(arg)
    if parsed is not None:
        option, value = parsed
        return option.lstrip("-"), value
    if arg.startswith("--lua-init=@"):
        return "lua-init", arg[len("--lua-init=@") :]
    if arg.startswith("--blob=") and ":@" in arg:
        _prefix, path = arg.split(":@", 1)
        return "blob", path
    return None


def _inventory_entry(root: Path, kind: str, path: Path) -> dict[str, object]:
    root = root.resolve()
    _assert_no_symlink_components(root, path)
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"runtime artifact outside workspace: {path}") from exc
    digest = file_sha256(path)
    return {
        "kind": kind,
        "path": rel,
        "state": "ready" if digest is not None else "missing",
        "sha256": digest,
    }


def runtime_artifact_inventory(root: Path, plan: GeneratedRuntimePlan) -> dict[str, object]:
    """Return the exact file-byte and owner/queue inputs bound by a start plan."""

    root = root.resolve()
    binary = _resolve_workspace_file(root, plan.binary_relative_path)
    entries: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, path: Path) -> None:
        key = (kind, path.resolve().as_posix())
        if key in seen:
            return
        seen.add(key)
        entries.append(_inventory_entry(root, kind, path))

    for hostlist in plan.hostlists:
        add("profile-hostlist", _resolve_workspace_file(root, hostlist.path))

    for raw_arg in plan.strategy.runtime_args:
        arg = str(raw_arg)
        ref = _runtime_arg_file_ref(arg)
        if ref is None:
            # Any unclassified @file syntax is deliberately rejected by the
            # privileged executor later; it is not silently omitted here.
            continue
        kind, raw_path = ref
        add(kind, _resolve_workspace_file(root, raw_path))

    uid, uid_source = runtime_owner_uid(root)
    gid, gid_source = runtime_owner_gid(root)
    queue = resolve_runtime_queue(root, plan.profile.profile_id)
    return {
        "schemaVersion": ARTIFACT_DIGEST_SCHEMA_VERSION,
        "binary": _inventory_entry(root, "nfqws2-binary", binary),
        "inputs": sorted(entries, key=lambda item: (str(item["kind"]), str(item["path"]))),
        "owner": {
            "uid": uid,
            "uidSource": uid_source,
            "gid": gid,
            "gidSource": gid_source,
        },
        "queue": queue.to_dict(),
    }


def inventory_ready(inventory: dict[str, object]) -> bool:
    binary = inventory.get("binary")
    if not isinstance(binary, dict) or binary.get("state") != "ready" or not binary.get("sha256"):
        return False
    inputs = inventory.get("inputs")
    if not isinstance(inputs, list):
        return False
    return all(isinstance(item, dict) and item.get("state") == "ready" and item.get("sha256") for item in inputs)


__all__ = [
    "ARTIFACT_DIGEST_SCHEMA_VERSION",
    "file_sha256",
    "inventory_ready",
    "runtime_artifact_inventory",
]
