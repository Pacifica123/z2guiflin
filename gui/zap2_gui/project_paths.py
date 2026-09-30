"""Project/resource location helpers.

P04b keeps the historical ``ProjectLayout.root`` API for compatibility, but no
longer treats ``Path(__file__).parents[...]`` as an installation contract.  A
resource root now has an explicit provenance:

* ``explicit`` -- caller supplied ``root``;
* ``environment`` -- ``ZAP2_RESOURCE_ROOT`` points at an external resource tree;
* ``source-checkout`` -- the package is demonstrably running from this checkout.

A normal site-packages install without an external/bundled resource root fails
closed instead of silently inventing an installation prefix.  P04b does not yet
claim full S-INSTALL readiness: packaging and writable-state separation remain
later work.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping


RESOURCE_ROOT_ENV = "ZAP2_RESOURCE_ROOT"


class ResourceLocationError(RuntimeError):
    """Raised when application resources cannot be located unambiguously."""


@dataclass(frozen=True)
class ResourceLocation:
    root: Path
    origin: str
    outside_checkout_contract: bool

    @property
    def is_source_checkout(self) -> bool:
        return self.origin == "source-checkout"


@dataclass(frozen=True)
class ProjectLayout:
    root: Path
    core_dir: Path
    gui_dir: Path
    docs_dir: Path
    tools_dir: Path
    profiles_dir: Path
    presets_dir: Path
    strategies_dir: Path
    runtime_dir: Path
    resource_origin: str = "explicit"

    def required_paths(self) -> tuple[Path, ...]:
        return (
            self.core_dir / "zapret2" / "docs" / "LICENSE.txt",
            self.core_dir / "zapret2" / "nfq2" / "nfqws.c",
            self.gui_dir / "zap2_gui" / "__init__.py",
            self.docs_dir / "DEVELOPMENT_STRATEGY.md",
            self.docs_dir / "VERSIONING.md",
            self.tools_dir / "gui_checks" / "check_project_tree.py",
            self.profiles_dir / "default.json",
            self.presets_dir / "README.md",
            self.strategies_dir / "catalog.json",
            self.runtime_dir / "README.md",
            self.runtime_dir / "schemas" / "runtime-plan.schema.json",
            self.runtime_dir / "schemas" / "runtime-event.schema.json",
            self.runtime_dir / "schemas" / "confirmation.schema.json",
        )


def _looks_like_resource_root(candidate: Path) -> bool:
    """Cheap identity check; this is not a full structural validation gate."""

    return all(
        path.exists()
        for path in (
            candidate / "strategies" / "catalog.json",
            candidate / "profiles" / "default.json",
            candidate / "runtime" / "README.md",
            candidate / "core" / "zapret2" / "docs" / "LICENSE.txt",
        )
    )


def discover_resource_location(
    root: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> ResourceLocation:
    """Resolve the immutable/static resource root with explicit provenance.

    ``root`` remains the strongest compatibility boundary.  Outside a checkout,
    callers/installers can provide ``ZAP2_RESOURCE_ROOT``.  The source fallback
    is accepted only when the inferred directory actually has project resource
    sentinels; an installed Python module without those sentinels is an error.
    """

    if root is not None:
        return ResourceLocation(Path(root).expanduser().resolve(), "explicit", True)

    env = os.environ if environ is None else environ
    configured = str(env.get(RESOURCE_ROOT_ENV, "")).strip()
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if not _looks_like_resource_root(candidate):
            raise ResourceLocationError(
                f"{RESOURCE_ROOT_ENV} does not point to a Zap2 resource root: {candidate}"
            )
        return ResourceLocation(candidate, "environment", True)

    candidate = Path(__file__).resolve().parents[2]
    if _looks_like_resource_root(candidate):
        return ResourceLocation(candidate, "source-checkout", False)

    raise ResourceLocationError(
        "Zap2 resources are not discoverable from this Python installation. "
        f"Set {RESOURCE_ROOT_ENV} to an installed/external resource root."
    )


def normalize_resource_relative_path(value: str) -> str:
    """Return one canonical POSIX resource path and reject escape attempts."""

    raw = str(value).strip().lstrip("@").replace("\\", "/")
    if not raw:
        raise ValueError("resource path is empty")
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"resource path leaves resource root: {value}")
    normalized = Path(*[part for part in candidate.parts if part not in {"", "."}]).as_posix()
    if not normalized or normalized == ".":
        raise ValueError("resource path is empty")
    return normalized


def resolve_resource_path(value: str, root: Path | None = None) -> Path:
    """Resolve a logical resource path without allowing symlink/root escape."""

    location = discover_resource_location(root)
    relative = normalize_resource_relative_path(value)
    lexical = location.root / relative
    resolved = lexical.resolve()
    try:
        resolved.relative_to(location.root)
    except ValueError as exc:
        raise ValueError(f"resource path leaves workspace/resource root: {value}") from exc
    return resolved


def discover_layout(root: Path | None = None) -> ProjectLayout:
    location = discover_resource_location(root)
    resolved_root = location.root
    return ProjectLayout(
        root=resolved_root,
        core_dir=resolved_root / "core",
        gui_dir=resolved_root / "gui",
        docs_dir=resolved_root / "docs",
        tools_dir=resolved_root / "tools",
        profiles_dir=resolved_root / "profiles",
        presets_dir=resolved_root / "presets",
        strategies_dir=resolved_root / "strategies",
        runtime_dir=resolved_root / "runtime",
        resource_origin=location.origin,
    )


__all__ = [
    "ProjectLayout",
    "RESOURCE_ROOT_ENV",
    "ResourceLocation",
    "ResourceLocationError",
    "discover_layout",
    "discover_resource_location",
    "normalize_resource_relative_path",
    "resolve_resource_path",
]
