"""Typed network evidence contracts for the VLESS/Vesktop lane.

The module deliberately separates local process/listener/SOCKS observations from
remote route/TLS/HTTP and application capability.  It is pure-Python and does
not execute network operations; adapters create spans and persist graphs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import uuid
from typing import Any, Iterable, Mapping, Sequence

EVIDENCE_GRAPH_SCHEMA_VERSION = 1
PROBE_SPAN_SCHEMA_VERSION = 1
CAPABILITY_VERDICT_SCHEMA_VERSION = 1
CONNECTION_RECEIPT_SCHEMA_VERSION = 2

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"
NOT_RUN = "NOT_RUN"

SUPPORTED = "SUPPORTED"
EXPERIMENTAL = "EXPERIMENTAL"
UNSUPPORTED = "UNSUPPORTED"
SUPPORT_UNKNOWN = "UNKNOWN"

_SECRET_KEY_FRAGMENTS = (
    "uuid",
    "userid",
    "user_id",
    "password",
    "token",
    "authorization",
    "cookie",
    "rawuri",
    "raw_uri",
    "privatekey",
    "private_key",
    "publickey",
    "public_key",
    "pbk",
    "shortid",
    "sid",
    "key",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(payload)


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _looks_secret_key(key: str) -> bool:
    normalized = key.replace("-", "").replace("_", "").lower()
    # ``key`` by itself is credential-bearing, but treating the substring
    # "key" as secret would incorrectly redact structural fields such as
    # unknownQueryKeys / recognizedQueryKeys.  Longer explicit fragments keep
    # their substring semantics (publicKey, privateKey, shortId, ...).
    if normalized == "key":
        return True
    return any(
        fragment.replace("_", "") in normalized
        for fragment in _SECRET_KEY_FRAGMENTS
        if fragment != "key"
    )


def redact_for_support(value: Any, *, key: str = "") -> Any:
    """Return a support-safe representation without raw credentials.

    Secret-bearing values are replaced with presence + hash.  Hashes permit
    equality/correlation checks without serializing the source credential.
    """

    if key and _looks_secret_key(key):
        if value in (None, "", [], {}):
            return {"present": False}
        return {"present": True, "sha256": hash_json(value) if not isinstance(value, str) else sha256_text(value)}
    if isinstance(value, Mapping):
        return {str(k): redact_for_support(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_for_support(item) for item in value]
    return value


@dataclass(frozen=True)
class ProbeSpan:
    span_id: str
    kind: str
    run_id: str
    result: str
    failure_class: str = ""
    target: str = ""
    deps: tuple[str, ...] = ()
    producer: str = "zap2_gui"
    created_at: str = field(default_factory=utc_now)
    input_hashes: Mapping[str, str] = field(default_factory=dict)
    detail: Mapping[str, Any] = field(default_factory=dict)
    limits: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProbeSpan":
        return cls(
            span_id=str(data.get("spanId", "")),
            kind=str(data.get("kind", "")),
            run_id=str(data.get("runId", "")),
            result=str(data.get("result", UNKNOWN)),
            failure_class=str(data.get("failureClass", "")),
            target=str(data.get("target", "")),
            deps=tuple(str(item) for item in data.get("deps", [])),
            producer=str(data.get("producer", "zap2_gui")),
            created_at=str(data.get("createdAt", utc_now())),
            input_hashes={str(k): str(v) for k, v in dict(data.get("inputHashes", {})).items()},
            detail=dict(data.get("detail", {})),
            limits=tuple(str(item) for item in data.get("limits", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": PROBE_SPAN_SCHEMA_VERSION,
            "spanId": self.span_id,
            "kind": self.kind,
            "runId": self.run_id,
            "target": self.target,
            "deps": list(self.deps),
            "producer": self.producer,
            "createdAt": self.created_at,
            "inputHashes": dict(self.input_hashes),
            "result": self.result,
            "failureClass": self.failure_class or None,
            "detail": redact_for_support(dict(self.detail)),
            "limits": list(self.limits),
        }


@dataclass(frozen=True)
class CapabilityVerdict:
    capability_id: str
    run_id: str
    support: str
    requirements: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    missing_requirements: tuple[str, ...] = ()
    failed_requirements: tuple[str, ...] = ()
    stale_evidence_ignored: tuple[str, ...] = ()
    scope: Mapping[str, Any] = field(default_factory=dict)
    next_experiment: str = ""
    reason: str = ""
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CapabilityVerdict":
        return cls(
            capability_id=str(data.get("capabilityId", "")),
            run_id=str(data.get("runId", "")),
            support=str(data.get("support", SUPPORT_UNKNOWN)),
            requirements=tuple(str(item) for item in data.get("requirements", [])),
            evidence_refs=tuple(str(item) for item in data.get("evidenceRefs", [])),
            missing_requirements=tuple(str(item) for item in data.get("missingRequirements", [])),
            failed_requirements=tuple(str(item) for item in data.get("failedRequirements", [])),
            stale_evidence_ignored=tuple(str(item) for item in data.get("staleEvidenceIgnored", [])),
            scope=dict(data.get("scope", {})),
            next_experiment=str(data.get("nextExperiment", "")),
            reason=str(data.get("reason", "")),
            created_at=str(data.get("createdAt", utc_now())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": CAPABILITY_VERDICT_SCHEMA_VERSION,
            "capabilityId": self.capability_id,
            "runId": self.run_id,
            "support": self.support,
            "scope": redact_for_support(dict(self.scope)),
            "requirements": list(self.requirements),
            "evidenceRefs": list(self.evidence_refs),
            "missingRequirements": list(self.missing_requirements),
            "failedRequirements": list(self.failed_requirements),
            "staleEvidenceIgnored": list(self.stale_evidence_ignored),
            "reason": self.reason,
            "nextExperiment": self.next_experiment,
            "createdAt": self.created_at,
        }


@dataclass
class EvidenceGraph:
    run_id: str
    profile_id: str
    connection_id: str
    connection_receipt_id: str
    core_identity_hash: str
    config_hash: str
    environment: Mapping[str, Any] = field(default_factory=dict)
    spans: list[ProbeSpan] = field(default_factory=list)
    verdicts: list[CapabilityVerdict] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceGraph":
        graph = cls(
            run_id=str(data.get("runId", "")),
            profile_id=str(data.get("profileId", "")),
            connection_id=str(data.get("connectionId", "")),
            connection_receipt_id=str(data.get("connectionReceiptId", "")),
            core_identity_hash=str(data.get("coreIdentityHash", "")),
            config_hash=str(data.get("configHash", "")),
            environment=dict(data.get("environment", {})),
            created_at=str(data.get("createdAt", utc_now())),
        )
        graph.spans = [ProbeSpan.from_dict(item) for item in data.get("spans", [])]
        graph.verdicts = [CapabilityVerdict.from_dict(item) for item in data.get("capabilityVerdicts", [])]
        return graph

    def add_span(self, span: ProbeSpan) -> None:
        if span.run_id != self.run_id:
            raise ValueError(f"probe span runId mismatch: graph={self.run_id}, span={span.run_id}")
        if any(existing.span_id == span.span_id for existing in self.spans):
            raise ValueError(f"duplicate probe span id: {span.span_id}")
        self.spans.append(span)

    def add_verdict(self, verdict: CapabilityVerdict) -> None:
        if verdict.run_id != self.run_id:
            raise ValueError(f"capability verdict runId mismatch: graph={self.run_id}, verdict={verdict.run_id}")
        self.verdicts = [item for item in self.verdicts if item.capability_id != verdict.capability_id]
        self.verdicts.append(verdict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": EVIDENCE_GRAPH_SCHEMA_VERSION,
            "createdAt": self.created_at,
            "runId": self.run_id,
            "profileId": self.profile_id,
            "connectionId": self.connection_id,
            "connectionReceiptId": self.connection_receipt_id,
            "coreIdentityHash": self.core_identity_hash,
            "configHash": self.config_hash,
            "environment": redact_for_support(dict(self.environment)),
            "spans": [span.to_dict() for span in self.spans],
            "capabilityVerdicts": [item.to_dict() for item in self.verdicts],
        }


def _latest_span_for_kind(
    spans: Sequence[ProbeSpan],
    *,
    run_id: str,
    kind: str,
    target: str | None = None,
) -> tuple[ProbeSpan | None, tuple[str, ...]]:
    current: list[ProbeSpan] = []
    stale: list[str] = []
    for span in spans:
        if span.kind != kind:
            continue
        if target is not None and span.target != target:
            continue
        if span.run_id == run_id:
            current.append(span)
        else:
            stale.append(span.span_id)
    return (current[-1] if current else None, tuple(stale))


def capability_from_required_spans(
    *,
    capability_id: str,
    run_id: str,
    spans: Sequence[ProbeSpan],
    requirements: Sequence[tuple[str, str | None]],
    scope: Mapping[str, Any] | None = None,
    next_experiment: str = "",
) -> CapabilityVerdict:
    """Evaluate a capability without promoting stale/local evidence.

    Each requirement is ``(kind, target-or-None)``.  Any current FAIL makes the
    capability UNSUPPORTED for this run. Missing/UNKNOWN evidence yields UNKNOWN.
    Only an all-PASS set yields SUPPORTED.
    """

    requirement_labels: list[str] = []
    evidence_refs: list[str] = []
    missing: list[str] = []
    failed: list[str] = []
    stale: list[str] = []
    unknown: list[str] = []

    for kind, target in requirements:
        label = f"{kind}@{target}" if target else kind
        requirement_labels.append(label)
        span, stale_refs = _latest_span_for_kind(spans, run_id=run_id, kind=kind, target=target)
        stale.extend(stale_refs)
        if span is None:
            missing.append(label)
            continue
        evidence_refs.append(span.span_id)
        if span.result == FAIL:
            failed.append(label)
        elif span.result != PASS:
            unknown.append(label)

    if failed:
        support = UNSUPPORTED
        reason = "one or more mandatory current-run predicates failed"
    elif missing or unknown:
        support = SUPPORT_UNKNOWN
        reason = "mandatory current-run evidence is missing or unknown"
    else:
        support = SUPPORTED
        reason = "all mandatory current-run predicates passed"

    return CapabilityVerdict(
        capability_id=capability_id,
        run_id=run_id,
        support=support,
        scope=dict(scope or {}),
        requirements=tuple(requirement_labels),
        evidence_refs=tuple(evidence_refs),
        missing_requirements=tuple((*missing, *unknown)),
        failed_requirements=tuple(failed),
        stale_evidence_ignored=tuple(stale),
        next_experiment=next_experiment,
        reason=reason,
    )


def aggregate_capability_verdicts(
    *,
    capability_id: str,
    run_id: str,
    verdicts: Iterable[CapabilityVerdict],
    scope: Mapping[str, Any] | None = None,
    next_experiment: str = "",
) -> CapabilityVerdict:
    """Conjoin subsystem/endpoint verdicts for an application capability."""

    current = [item for item in verdicts if item.run_id == run_id]
    requirements = tuple(item.capability_id for item in current)
    refs = tuple(ref for item in current for ref in item.evidence_refs)
    failed = tuple(item.capability_id for item in current if item.support == UNSUPPORTED)
    unknown = tuple(item.capability_id for item in current if item.support not in {SUPPORTED, UNSUPPORTED})

    if failed:
        support = UNSUPPORTED
        reason = "one or more mandatory application predicates failed"
    elif not current or unknown:
        support = SUPPORT_UNKNOWN
        reason = "mandatory application evidence is missing or unknown"
    else:
        support = SUPPORTED
        reason = "all mandatory application predicates passed"

    return CapabilityVerdict(
        capability_id=capability_id,
        run_id=run_id,
        support=support,
        scope=dict(scope or {}),
        requirements=requirements,
        evidence_refs=refs,
        missing_requirements=unknown,
        failed_requirements=failed,
        next_experiment=next_experiment,
        reason=reason,
    )
