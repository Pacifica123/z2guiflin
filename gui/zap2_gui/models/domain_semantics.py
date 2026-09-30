"""P04 domain ontology and executable-action contract foundation.

P04 deliberately separates stable domain vocabulary from the legacy CLI/parser
shape.  This module is pure data: importing it cannot execute handlers, mutate
runtime state, request privilege, or touch the network.
"""

from __future__ import annotations

from dataclasses import dataclass


CANONICAL_DOMAIN_NOUNS: tuple[str, ...] = (
    "runtimeContext",
    "preset",
    "trafficProfile",
    "desyncAction",
    "tunnelConnection",
    "backend/core",
    "runtimeResource",
    "operation/action",
    "Plan",
    "probe",
    "Evidence",
    "Verdict",
    "Capability",
)

CANONICAL_ACTION_VERBS: tuple[str, ...] = (
    "inspect",
    "list",
    "show",
    "plan",
    "validate",
    "prepare",
    "confirm",
    "apply",
    "revert",
    "start",
    "stop",
    "reconcile",
    "probe",
    "launch",
    "import",
    "export",
)

ACTION_PRIVILEGES: tuple[str, ...] = (
    "none",
    "owner",
    "bounded-root",
)


@dataclass(frozen=True)
class LegacyTermAlias:
    """One compatibility-only terminology mapping with explicit scope."""

    legacy: str
    canonical: str
    scope: str
    note: str


LEGACY_TERM_ALIASES: tuple[LegacyTermAlias, ...] = (
    LegacyTermAlias(
        legacy="workspace profile",
        canonical="runtimeContext",
        scope="profiles/*.json and WorkspaceProfile Python alias",
        note="Legacy storage/API name remains readable; new UI/docs should say runtime context.",
    ),
    LegacyTermAlias(
        legacy="strategy (selected runtime recipe)",
        canonical="preset",
        scope="strategies/*.json selection metadata",
        note="The executable nfqws2 recipe is the preset; strategy remains historical metadata vocabulary.",
    ),
    LegacyTermAlias(
        legacy="profile (inside preset)",
        canonical="trafficProfile",
        scope="ordered nfqws2 --new blocks",
        note="Do not reuse profile for the runtime context.",
    ),
    LegacyTermAlias(
        legacy="generic run",
        canonical="operation/action",
        scope="CLI/GUI labels",
        note="Use the concrete verb (probe/start/launch/etc.) whenever the effect is known.",
    ),
)


@dataclass(frozen=True)
class ActionContract:
    """Executable-action declaration and projection metadata.

    P04a introduces the contract type and its invariants only.  Later bounded
    P04 hyperpatches move legacy executable paths behind these contracts.  A
    non-internal contract must identify a handler; metadata-only third registries
    are therefore not valid ActionContracts.
    """

    action_id: str
    label: str
    effect: str
    short_help: str
    handler_id: str | None
    aliases: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    concept_links: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    privilege: str = "none"
    capability: str | None = None
    location: str | None = None
    focus_target: str | None = None
    safe_invoke: bool = False
    deep_help: str | None = None
    legacy_aliases: tuple[str, ...] = ()
    internal: bool = False

    def validation_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.action_id.strip():
            errors.append("action_id must be non-empty")
        if not self.label.strip():
            errors.append("label must be non-empty")
        if self.effect not in CANONICAL_ACTION_VERBS:
            errors.append(f"effect must be canonical: {self.effect!r}")
        if self.privilege not in ACTION_PRIVILEGES:
            errors.append(f"unknown privilege class: {self.privilege!r}")
        if not self.short_help.strip():
            errors.append("short_help must be non-empty")
        if not self.internal and not (self.handler_id or "").strip():
            errors.append("visible ActionContract requires handler_id")
        if self.safe_invoke and self.effect in {"apply", "revert", "start", "stop", "launch"}:
            errors.append("mutating/launch actions cannot be safeInvoke without an explicit prepare/confirm flow")
        return tuple(errors)

    @property
    def is_valid(self) -> bool:
        return not self.validation_errors()
