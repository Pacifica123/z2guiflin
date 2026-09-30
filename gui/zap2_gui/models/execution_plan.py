"""P04 normalized immutable execution Plan.

The Plan is location-independent: physical checkout/install paths and authoring
representation names are deliberately excluded from its hash.  Runtime-relevant
file bytes are represented by logical resource paths plus SHA-256 digests.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


EXECUTION_PLAN_SCHEMA_VERSION = 1
EXECUTION_PLAN_KIND = "zap2-normalized-execution-plan"


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ExecutionResource:
    kind: str
    logical_path: str
    state: str
    sha256: str | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "logicalPath": self.logical_path,
            "state": self.state,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class ImmutableExecutionPlan:
    """Canonical execution semantics selected by one runtime context."""

    runtime_context_id: str
    preset_id: str
    engine: str
    build_target: str
    runtime_args: tuple[str, ...]
    resources: tuple[ExecutionResource, ...]
    schema_version: int = EXECUTION_PLAN_SCHEMA_VERSION
    kind: str = EXECUTION_PLAN_KIND

    def to_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "kind": self.kind,
            "runtimeContextId": self.runtime_context_id,
            "presetId": self.preset_id,
            "engine": self.engine,
            "buildTarget": self.build_target,
            "runtimeArgs": list(self.runtime_args),
            "resources": [item.to_payload() for item in self.resources],
        }

    @property
    def plan_hash(self) -> str:
        return hashlib.sha256(_stable_json(self.to_payload()).encode("utf-8")).hexdigest()

    @property
    def resources_ready(self) -> bool:
        return all(item.state == "ready" and bool(item.sha256) for item in self.resources)

    def to_record(self) -> dict[str, Any]:
        return {**self.to_payload(), "planHash": self.plan_hash}


@dataclass(frozen=True)
class ExecutionPlanMaterialization:
    """Non-authoritative provenance around one canonical Plan.

    ``source_kind``/``source_path`` explain how the semantics were obtained but
    are not part of ``ImmutableExecutionPlan.plan_hash``.  This is what allows
    equivalent TXT/legacy projections to prove the same execution authority.
    """

    plan: ImmutableExecutionPlan
    source_kind: str
    source_path: str
    resource_origin: str
    compatibility_warnings: tuple[str, ...] = ()


__all__ = [
    "EXECUTION_PLAN_KIND",
    "EXECUTION_PLAN_SCHEMA_VERSION",
    "ExecutionPlanMaterialization",
    "ExecutionResource",
    "ImmutableExecutionPlan",
]
