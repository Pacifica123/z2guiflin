"""Materialize one P04 immutable execution Plan from compatibility sources."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from .strategy_file_inputs import split_strategy_file_arg
from .workspace_profiles import load_workspace_catalog
from ..models.execution_plan import (
    ExecutionPlanMaterialization,
    ExecutionResource,
    ImmutableExecutionPlan,
)
from ..models.strategy import WorkspaceStrategy
from ..models.workspace_profile import HostlistRef, WorkspaceRuntimeContext
from ..project_paths import (
    discover_resource_location,
    normalize_resource_relative_path,
    resolve_resource_path,
)


def _file_sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except (FileNotFoundError, PermissionError, OSError):
        return None


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


def _selected_hostlists(
    runtime_context: WorkspaceRuntimeContext,
    preset: WorkspaceStrategy,
) -> tuple[HostlistRef, ...]:
    capture_policy = preset.capture_policy or {}
    if str(capture_policy.get("profileHostlists") or "").lower() in {"omit", "none", "disabled"}:
        return ()
    if not preset.capabilities.reads_hostlists:
        return ()
    return runtime_context.hostlists


def _resource_digest(root: Path, kind: str, raw_path: str) -> ExecutionResource:
    logical_path = normalize_resource_relative_path(raw_path)
    path = resolve_resource_path(logical_path, root)
    digest = _file_sha256(path)
    return ExecutionResource(
        kind=kind,
        logical_path=logical_path,
        state="ready" if digest is not None else "missing",
        sha256=digest,
    )


def _execution_resources(
    root: Path,
    runtime_context: WorkspaceRuntimeContext,
    preset: WorkspaceStrategy,
    runtime_args: Iterable[str],
) -> tuple[ExecutionResource, ...]:
    resources: list[ExecutionResource] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, raw_path: str) -> None:
        logical = normalize_resource_relative_path(raw_path)
        key = (kind, logical)
        if key in seen:
            return
        seen.add(key)
        resources.append(_resource_digest(root, kind, logical))

    for hostlist in _selected_hostlists(runtime_context, preset):
        add("runtime-context-hostlist", hostlist.path)

    for raw_arg in runtime_args:
        parsed = _runtime_arg_file_ref(str(raw_arg))
        if parsed is None:
            continue
        kind, raw_path = parsed
        add(kind, raw_path)

    return tuple(sorted(resources, key=lambda item: (item.kind, item.logical_path)))


def materialize_execution_plan_from_args(
    *,
    root: Path,
    runtime_context: WorkspaceRuntimeContext,
    preset: WorkspaceStrategy,
    runtime_args: Iterable[str],
    source_kind: str,
    source_path: str = "",
    compatibility_warnings: tuple[str, ...] = (),
) -> ExecutionPlanMaterialization:
    """Normalize already-parsed argv into the one execution Plan authority."""

    location = discover_resource_location(root)
    args = tuple(str(item) for item in runtime_args)
    resources = _execution_resources(location.root, runtime_context, preset, args)
    plan = ImmutableExecutionPlan(
        runtime_context_id=runtime_context.runtime_context_id,
        preset_id=preset.preset_id,
        engine="nfqws2",
        build_target=runtime_context.build_target,
        runtime_args=args,
        resources=resources,
    )
    return ExecutionPlanMaterialization(
        plan=plan,
        source_kind=source_kind,
        source_path=source_path,
        resource_origin=location.origin,
        compatibility_warnings=compatibility_warnings,
    )


def materialize_execution_plan(
    root: Path | None = None,
    runtime_context_id: str = "default",
) -> ExecutionPlanMaterialization:
    """Materialize the active preset selected by a runtime context.

    ``strategies/*.json runtimeArgs`` is compatibility metadata only.  The
    loader projects ``WorkspaceStrategy.runtime_args`` from ``presetPath`` when
    present, so this function cannot execute a divergent legacy duplicate.
    """

    location = discover_resource_location(root)
    catalog = load_workspace_catalog(location.root)
    contexts = catalog.profile_by_id()
    if runtime_context_id not in contexts:
        raise ValueError(
            f"Unknown runtimeContext: {runtime_context_id}. Available: {', '.join(sorted(contexts))}"
        )
    runtime_context = contexts[runtime_context_id]
    presets = catalog.strategy_by_id()
    if runtime_context.preset_id not in presets:
        raise ValueError(f"runtimeContext {runtime_context_id} references unknown preset: {runtime_context.preset_id}")
    preset = presets[runtime_context.preset_id]
    warnings = tuple(preset.compatibility_warnings)
    source_kind = "presetPath" if preset.preset_path else "legacy-runtimeArgs"
    source_path = preset.preset_path
    return materialize_execution_plan_from_args(
        root=location.root,
        runtime_context=runtime_context,
        preset=preset,
        runtime_args=preset.runtime_args,
        source_kind=source_kind,
        source_path=source_path,
        compatibility_warnings=warnings,
    )


__all__ = [
    "materialize_execution_plan",
    "materialize_execution_plan_from_args",
]
