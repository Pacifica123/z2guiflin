"""Discord SOCKS/VLESS tunnel lane for Stage 7p1..7p4.

This adapter deliberately does not implement the VLESS protocol itself.  It
stores owner-provided connection profiles, generates a local loopback SOCKS core
configuration for an owner-selected external core, and manages only the process
recorded in Zap2's local tunnel session file.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import json
import secrets
import os
import shlex
import shutil
import signal
import socket
import ssl
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, unquote, urlsplit

from .runtime_default import default_workflow_status
from .runtime_state import confirm_runtime_plan, ensure_runtime_store, plan_payload_hash
from ..project_paths import discover_layout
from ..models.network_evidence import (
    CONNECTION_RECEIPT_SCHEMA_VERSION,
    EvidenceGraph,
    EXPERIMENTAL,
    FAIL,
    PASS,
    UNKNOWN,
    ProbeSpan,
    SUPPORT_UNKNOWN,
    SUPPORTED,
    UNSUPPORTED,
    aggregate_capability_verdicts,
    capability_from_required_spans,
    hash_json as evidence_hash_json,
    new_run_id,
    redact_for_support,
    sha256_text,
)

TUNNEL_STAGE = "v0.4-alpha_stage8g"
TUNNEL_SCHEMA_VERSION = 2
TUNNEL_MARKER = "zap2-discord-tunnel-v1"
DEFAULT_PROFILE_ID = "default"
DEFAULT_SOCKS_HOST = "127.0.0.1"
# 0 = выбрать случайный свободный loopback-порт при создании plan/session.
# Хорошо известные порты (10808/1080/9000/16000-16100) сканируются локальными
# приложениями и сайтами-помощниками, см. wiki.zapret.moe/VLESS-SOCKS5-vulnerability.
DEFAULT_SOCKS_PORT = 0
SOCKS_AUTO_PORT_RANGE = (20000, 60999)
SOCKS_SCANNED_PORTS = frozenset({1080, 9000, 10808, *range(16000, 16101)})
SOCKS_AUTH_PASSWORD = "password"
SOCKS_AUTH_LEGACY_NOAUTH = "legacy-noauth"
SUPPORTED_SOCKS_AUTH_MODES = (SOCKS_AUTH_PASSWORD, SOCKS_AUTH_LEGACY_NOAUTH)
SOCKS_REDACTED = "<redacted>"
LEGACY_NOAUTH_WARNING = (
    "ВНИМАНИЕ: legacy noauth SOCKS включён явно. Любое локальное приложение или сайт-сканер "
    "может использовать loopback SOCKS без пароля и узнать IP VPN-сервера (localhost ≠ private). "
    "Режим нужен только для Chromium/Electron --proxy-server, который не умеет SOCKS-аутентификацию."
)
DEFAULT_CORE_KIND = "auto"
SUPPORTED_CORE_KINDS = ("auto", "xray", "v2ray", "sing-box")
SUPPORTED_LAUNCH_MODES = ("socks-updater-window", "socks-full-session", "socks-env-only", "socks-flag-only")
DEFAULT_DISCORD_COMMAND = "discord"
VESKTOP_COMMAND = "vesktop"
FLATPAK_VESKTOP_COMMAND = "flatpak run dev.vencord.Vesktop"
AUTO_DISCORD_COMMAND = "auto"
XHTTP_LIKE_TRANSPORTS = {"xhttp", "splithttp"}


def _tail_file(path: Path, *, max_chars: int = 1400) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _core_transport_warning(profile: "VlessConnectionProfile", core_kind: str) -> str:
    network = (profile.network or "tcp").lower()
    security = (profile.security or "none").lower()
    kind = (core_kind or "auto").lower()
    if kind == "v2ray" and security == "reality":
        return (
            "security=reality относится к Xray/XTLS lane и обычным V2Ray core не поддерживается. "
            "Выберите Xray core для этого VLESS profile или используйте профиль без REALITY."
        )
    if network in XHTTP_LIKE_TRANSPORTS and kind == "v2ray":
        return (
            f"transport {network} обычно не поддерживается V2Ray core. "
            "Используйте Xray с поддержкой XHTTP или импортируйте VLESS profile с type=tcp/ws/grpc."
        )
    return ""


def _last_core_failure_summary(paths: "TunnelStorePaths", profile_id: str) -> str:
    session_path = _session_path(paths, profile_id)
    lines: list[str] = []
    if session_path.exists():
        try:
            session = _read_json(session_path)
        except Exception:
            session = {}
        state = str(session.get("state", ""))
        if state:
            lines.append(f"last session state: {state}")
        pid = int(session.get("pid", 0) or 0)
        if pid:
            lines.append(f"last pid: {pid}; proc: {_proc_state(pid)}")
    stdout_tail = _tail_file(_stdout_path(paths, profile_id), max_chars=900)
    stderr_tail = _tail_file(_stderr_path(paths, profile_id), max_chars=1400)
    if stdout_tail:
        lines.extend(["last core stdout:", stdout_tail])
    if stderr_tail:
        lines.extend(["last core stderr:", stderr_tail])
        if "unknown transport protocol" in stderr_tail:
            lines.append(
                "diagnosis: tunnel core rejected the generated config transport. "
                "Check VLESS type=... and selected core binary. For type=xhttp/splithttp, /usr/bin/v2ray may be incompatible."
            )
    return "\n".join(lines)

FLATPAK_DISCORD_COMMAND = "flatpak run com.discordapp.Discord"
SECRET_KEYS = {"id", "uuid", "password", "rawUri"}
KNOWN_VLESS_QUERY_KEYS = {
    "encryption",
    "security",
    "type",
    "host",
    "headerType",
    "sni",
    "alpn",
    "flow",
    "path",
    "fp",
    "pbk",
    "sid",
    "spx",
    "serviceName",
    "mode",
    "authority",
    "seed",
    "mtu",
    "tti",
    "quicSecurity",
    "key",
    "extra",
    "fm",
    "insecure",
    "allowInsecure",
    "allow_insecure",
    "ech",
    "vcn",
    "pcs",
    "pqv",
}
VLESS_URI_RE = re.compile(r"vless://[^\s<>\"']+", re.IGNORECASE)
MAX_VLESS_IMPORT_TEXT_BYTES = 256 * 1024
MAX_VLESS_IMPORT_CANDIDATES = 64


@dataclass(frozen=True)
class TunnelStorePaths:
    root: Path
    tunnel_root: Path
    connections_dir: Path
    generated_dir: Path
    runtime_dir: Path
    logs_dir: Path
    plans_dir: Path
    confirmations_dir: Path
    receipts_dir: Path
    evidence_dir: Path

    @property
    def required_dirs(self) -> tuple[Path, ...]:
        return (
            self.tunnel_root,
            self.connections_dir,
            self.generated_dir,
            self.runtime_dir,
            self.logs_dir,
            self.plans_dir,
            self.confirmations_dir,
            self.receipts_dir,
            self.evidence_dir,
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: dict[str, Any], *, secret: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if secret:
        try:
            path.chmod(0o600)
        except OSError:
            pass


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha12(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _sha256_json(data: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def tunnel_store_paths(root: Path | None = None) -> TunnelStorePaths:
    layout = discover_layout(root)
    runtime_paths = ensure_runtime_store(layout.root)
    tunnel_root = layout.root / ".zap2" / "tunnel"
    return TunnelStorePaths(
        root=layout.root,
        tunnel_root=tunnel_root,
        connections_dir=tunnel_root / "connections",
        generated_dir=tunnel_root / "generated",
        runtime_dir=tunnel_root / "runtime",
        logs_dir=tunnel_root / "logs",
        plans_dir=runtime_paths.plans_dir,
        confirmations_dir=runtime_paths.confirmations_dir,
        receipts_dir=tunnel_root / "receipts",
        evidence_dir=tunnel_root / "evidence",
    )


def ensure_tunnel_store(root: Path | None = None) -> TunnelStorePaths:
    paths = tunnel_store_paths(root)
    for directory in paths.required_dirs:
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def _connection_receipt_id(profile: "VlessConnectionProfile") -> str:
    normalized = profile.normalized_hash or profile.fingerprint
    return f"receipt-{profile.connection_id}-{normalized[:12]}"


def _connection_receipt_path(paths: TunnelStorePaths, profile_id: str, profile: "VlessConnectionProfile") -> Path:
    return paths.receipts_dir / f"{profile_id}.{_connection_receipt_id(profile)}.json"


def _evidence_graph_path(paths: TunnelStorePaths, profile_id: str, run_id: str) -> Path:
    return paths.evidence_dir / f"{profile_id}.{run_id}.evidence.json"


@dataclass(frozen=True)
class VlessConnectionProfile:
    connection_id: str
    scheme: str
    user_id: str
    server: str
    port: int
    remarks: str
    encryption: str
    security: str
    network: str
    header_type: str
    host: str
    sni: str
    alpn: tuple[str, ...]
    flow: str
    path: str
    service_name: str
    authority: str
    xhttp_mode: str
    xhttp_extra: str
    allow_insecure: bool
    kcp_seed: str
    kcp_mtu: int | None
    kcp_tti: int | None
    final_mask: str
    raw_query: dict[str, str]
    unknown_query: dict[str, str]
    imported_at: str
    source: str
    source_hash: str
    normalized_hash: str

    @property
    def fingerprint(self) -> str:
        publicish = {
            "scheme": self.scheme,
            "server": self.server,
            "port": self.port,
            "security": self.security,
            "network": self.network,
            "headerType": self.header_type,
            "host": self.host,
            "sni": self.sni,
            "remarks": self.remarks,
        }
        return _sha256_json(publicish)

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            "connectionId": self.connection_id,
            "scheme": self.scheme,
            "userId": self.user_id,
            "server": self.server,
            "port": self.port,
            "remarks": self.remarks,
            "encryption": self.encryption,
            "security": self.security,
            "network": self.network,
            "headerType": self.header_type,
            "host": self.host,
            "sni": self.sni,
            "alpn": list(self.alpn),
            "flow": self.flow,
            "path": self.path,
            "serviceName": self.service_name,
            "authority": self.authority,
            "xhttpMode": self.xhttp_mode,
            "xhttpExtra": self.xhttp_extra,
            "allowInsecure": self.allow_insecure,
            "kcpSeed": self.kcp_seed,
            "kcpMtu": self.kcp_mtu,
            "kcpTti": self.kcp_tti,
            "finalMask": self.final_mask,
            "rawQuery": dict(self.raw_query),
            "unknownQuery": dict(self.unknown_query),
            "importedAt": self.imported_at,
            "source": self.source,
            "sourceHash": self.source_hash,
            "normalizedHash": self.normalized_hash,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_storage_dict(cls, data: dict[str, Any]) -> "VlessConnectionProfile":
        return cls(
            connection_id=str(data["connectionId"]),
            scheme=str(data.get("scheme", "vless")),
            user_id=str(data["userId"]),
            server=str(data["server"]),
            port=int(data["port"]),
            remarks=str(data.get("remarks", "")),
            encryption=str(data.get("encryption", "none") or "none"),
            security=str(data.get("security", "none") or "none"),
            network=str(data.get("network", "tcp") or "tcp"),
            header_type=str(data.get("headerType", "none") or "none"),
            host=str(data.get("host", "")),
            sni=str(data.get("sni", "")),
            alpn=tuple(str(item) for item in data.get("alpn", [])),
            flow=str(data.get("flow", "")),
            path=str(data.get("path", "")),
            service_name=str(data.get("serviceName", "")),
            authority=str(data.get("authority", "")),
            xhttp_mode=str(data.get("xhttpMode", "")),
            xhttp_extra=str(data.get("xhttpExtra", "")),
            allow_insecure=bool(data.get("allowInsecure", False)),
            kcp_seed=str(data.get("kcpSeed", "")),
            kcp_mtu=int(data["kcpMtu"]) if data.get("kcpMtu") is not None else None,
            kcp_tti=int(data["kcpTti"]) if data.get("kcpTti") is not None else None,
            final_mask=str(data.get("finalMask", "")),
            raw_query={str(k): str(v) for k, v in dict(data.get("rawQuery", {})).items()},
            unknown_query={str(k): str(v) for k, v in dict(data.get("unknownQuery", {})).items()},
            imported_at=str(data.get("importedAt", _utc_now())),
            source=str(data.get("source", "stored")),
            source_hash=str(data.get("sourceHash", "")),
            normalized_hash=str(data.get("normalizedHash", data.get("fingerprint", ""))),
        )

    def redacted_dict(self) -> dict[str, Any]:
        redacted_server = _redact_host(self.server)
        return {
            "connectionId": self.connection_id,
            "scheme": self.scheme,
            "userId": _redact_uuid(self.user_id),
            "server": redacted_server,
            "port": self.port,
            "remarks": self.remarks,
            "encryption": self.encryption,
            "security": self.security,
            "network": self.network,
            "headerType": self.header_type,
            "host": _redact_host(self.host) if self.host else "",
            "sni": _redact_host(self.sni) if self.sni else "",
            "alpn": list(self.alpn),
            "flow": self.flow,
            "path": self.path,
            "serviceName": self.service_name,
            "authority": _redact_host(self.authority) if self.authority else "",
            "xhttpMode": self.xhttp_mode,
            "allowInsecure": self.allow_insecure,
            "unknownQueryKeys": sorted(self.unknown_query),
            "sourceHash": self.source_hash,
            "normalizedHash": self.normalized_hash,
            "fingerprint": self.fingerprint[:16],
        }




@dataclass(frozen=True)
class VlessImportPreview:
    candidate_count: int
    valid_profiles: tuple[VlessConnectionProfile, ...]
    rejected: tuple[str, ...]
    source: str

    @property
    def valid_count(self) -> int:
        return len(self.valid_profiles)

    def to_text(self) -> str:
        lines = [
            "VLESS import preview",
            f"source: {self.source}",
            f"candidates: {self.candidate_count}",
            f"valid: {self.valid_count}",
            f"rejected: {len(self.rejected)}",
        ]
        if self.valid_profiles:
            lines.append("profiles:")
            for index, profile in enumerate(self.valid_profiles, start=1):
                redacted = profile.redacted_dict()
                lines.extend(
                    [
                        f"  {index}. {profile.connection_id}",
                        f"     remarks: {profile.remarks}",
                        f"     destination: {redacted['server']}:{profile.port}",
                        f"     transport: {profile.network}/{profile.header_type}; security={profile.security}; encryption={profile.encryption}",
                        f"     host override: {redacted['host'] or 'нет'}",
                    ]
                )
        if self.rejected:
            lines.append("rejected samples:")
            for item in self.rejected[:5]:
                lines.append(f"  - {item}")
        lines.extend(["writes files now: no", "raw uri printed now: no"])
        return "\n".join(lines)


def _redact_uuid(value: str) -> str:
    value = str(value)
    if len(value) <= 8:
        return "<redacted-id>"
    return f"{value[:4]}…{value[-4:]}"


def _redact_host(value: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    if value.replace(".", "").isdigit():
        parts = value.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.x.x"
    labels = value.split(".")
    if len(labels) >= 2:
        first = labels[0][:2] or "h"
        tld = labels[-1]
        return f"{first}…*.{tld}"
    return f"{value[:2]}…"


def _normalize_security(value: str | None) -> str:
    return (value or "none").strip() or "none"


def _normalize_network(value: str | None) -> str:
    return (value or "tcp").strip() or "tcp"


def _parse_alpn(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _query_bool(query: dict[str, str], *keys: str) -> bool:
    for key in keys:
        if query.get(key) == "1":
            return True
        if query.get(key) == "0":
            return False
    return False


def _query_int(query: dict[str, str], key: str) -> int | None:
    try:
        return int(query[key]) if query.get(key) not in {None, ""} else None
    except ValueError:
        return None


def _receipt_source_kind(source: str) -> str:
    """Keep support receipts useful without leaking owner filesystem paths."""

    value = str(source or "unknown")
    if value.startswith("file:"):
        return "file"
    return value.split(":", 1)[0] if ":" in value else value


def _hashed_presence(value: str) -> dict[str, Any]:
    text = str(value or "")
    if not text:
        return {"present": False}
    return {"present": True, "sha256": sha256_text(text)}


def _connection_receipt_summary(profile: VlessConnectionProfile) -> dict[str, Any]:
    """Redacted semantic summary suitable for non-secret support evidence."""

    return {
        "connectionId": profile.connection_id,
        "scheme": profile.scheme,
        "userId": _hashed_presence(profile.user_id),
        "server": _redact_host(profile.server),
        "port": profile.port,
        "remarks": _hashed_presence(profile.remarks),
        "encryption": profile.encryption,
        "security": profile.security,
        "network": profile.network,
        "headerType": profile.header_type,
        "host": _redact_host(profile.host) if profile.host else "",
        "sni": _redact_host(profile.sni) if profile.sni else "",
        "alpn": list(profile.alpn),
        "flow": profile.flow,
        "path": _hashed_presence(profile.path),
        "serviceName": _hashed_presence(profile.service_name),
        "authority": _redact_host(profile.authority) if profile.authority else "",
        "xhttpMode": profile.xhttp_mode,
        "xhttpExtra": _hashed_presence(profile.xhttp_extra),
        "allowInsecure": profile.allow_insecure,
        "kcpSeed": _hashed_presence(profile.kcp_seed),
        "kcpMtu": profile.kcp_mtu,
        "kcpTti": profile.kcp_tti,
        "finalMask": _hashed_presence(profile.final_mask),
        "unknownQueryKeys": sorted(profile.unknown_query),
        "sourceHash": profile.source_hash or None,
        "normalizedHash": profile.normalized_hash or profile.fingerprint,
        "fingerprint": profile.fingerprint[:16],
    }


def _write_import_connection_receipt(paths: TunnelStorePaths, profile_id: str, profile: VlessConnectionProfile) -> Path:
    source_state = "captured" if profile.source_hash else "historically_unrecoverable"
    payload = {
        "schemaVersion": CONNECTION_RECEIPT_SCHEMA_VERSION,
        "receiptId": _connection_receipt_id(profile),
        "createdAt": _utc_now(),
        "profileId": profile_id,
        "connectionId": profile.connection_id,
        "source": {
            "kind": _receipt_source_kind(profile.source),
            "state": source_state,
            "sourceHash": profile.source_hash or None,
        },
        "normalizedHash": profile.normalized_hash or profile.fingerprint,
        "recognizedQueryKeys": sorted(key for key in profile.raw_query if key in KNOWN_VLESS_QUERY_KEYS),
        "unknownQueryKeys": sorted(profile.unknown_query),
        "connection": _connection_receipt_summary(profile),
        "generation": {
            "coreKind": None,
            "generatedSemanticHash": None,
            "semanticFidelity": "unbound",
            "requiredLoss": [],
            "support": SUPPORT_UNKNOWN,
            "reason": "generator/core not bound yet",
        },
        "rawUriStored": False,
    }
    path = _connection_receipt_path(paths, profile_id, profile)
    _write_json(path, payload, secret=False)
    return path


def parse_vless_uri(uri_text: str, *, source: str = "manual") -> VlessConnectionProfile:
    """Parse a VLESS share link without doing any network access."""

    raw = uri_text.strip()
    if raw.startswith("@"):  # defensive; callers normally expand @ files earlier
        raise ValueError("VLESS URI parser received @file marker; expand it before parsing")
    if not raw:
        raise ValueError("VLESS URI is empty")
    parsed = urlsplit(raw)
    if parsed.scheme.lower() != "vless":
        raise ValueError("Поддерживается только vless:// connection URI")
    if not parsed.username:
        raise ValueError("VLESS URI должен содержать UUID/user id до @")
    try:
        user_id = str(uuid.UUID(unquote(parsed.username)))
    except ValueError as exc:
        raise ValueError("VLESS user id должен быть корректным UUID") from exc
    if not parsed.hostname:
        raise ValueError("VLESS URI должен содержать server host")
    if parsed.port is None or parsed.port <= 0 or parsed.port > 65535:
        raise ValueError("VLESS URI должен содержать корректный port 1..65535")
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    seen_query_keys: set[str] = set()
    duplicate_query_keys: set[str] = set()
    for key, _value in query_items:
        if key in seen_query_keys:
            duplicate_query_keys.add(key)
        seen_query_keys.add(key)
    if duplicate_query_keys:
        raise ValueError(
            "VLESS URI содержит повторяющиеся query-параметры, которые нельзя нормализовать без риска потери семантики: "
            + ", ".join(sorted(duplicate_query_keys))
        )
    query = dict(query_items)
    if not query:
        raise ValueError("VLESS URI должен содержать query-параметры; минимум encryption=none")
    unknown = {key: value for key, value in query.items() if key not in KNOWN_VLESS_QUERY_KEYS}
    remarks = unquote(parsed.fragment or "").strip() or "unnamed-vless"
    raw_id_material = f"{parsed.scheme.lower()}://{user_id}@{parsed.hostname}:{parsed.port}?{parsed.query}#{parsed.fragment}"
    source_hash = sha256_text(raw)
    normalized_hash = evidence_hash_json(
        {
            "scheme": "vless",
            "userId": user_id,
            "server": parsed.hostname,
            "port": int(parsed.port),
            "query": {key: query[key] for key in sorted(query)},
            "remarks": remarks,
        }
    )
    return VlessConnectionProfile(
        connection_id=f"vless-{_sha12(raw_id_material)}",
        scheme="vless",
        user_id=user_id,
        server=parsed.hostname,
        port=int(parsed.port),
        remarks=remarks,
        encryption=query.get("encryption", "none") or "none",
        security=_normalize_security(query.get("security")),
        network=_normalize_network(query.get("type")),
        header_type=query.get("headerType", "none") or "none",
        host=query.get("host", ""),
        sni=query.get("sni", ""),
        alpn=_parse_alpn(query.get("alpn")),
        flow=query.get("flow", ""),
        path=query.get("path", ""),
        service_name=query.get("serviceName", ""),
        authority=query.get("authority", ""),
        xhttp_mode=query.get("mode", ""),
        xhttp_extra=query.get("extra", ""),
        allow_insecure=_query_bool(query, "insecure", "allowInsecure", "allow_insecure"),
        kcp_seed=query.get("seed", ""),
        kcp_mtu=_query_int(query, "mtu"),
        kcp_tti=_query_int(query, "tti"),
        final_mask=query.get("fm", ""),
        raw_query=query,
        unknown_query=unknown,
        imported_at=_utc_now(),
        source=source,
        source_hash=source_hash,
        normalized_hash=normalized_hash,
    )


def _ensure_import_text_is_small(text: str) -> str:
    if len(text.encode("utf-8")) > MAX_VLESS_IMPORT_TEXT_BYTES:
        raise ValueError(f"VLESS import text is too large; limit is {MAX_VLESS_IMPORT_TEXT_BYTES} bytes")
    return text


def _try_decode_base64_text(text: str) -> str:
    compact = "".join(text.strip().split())
    if not compact or len(compact) < 16:
        return ""
    padded = compact + ("=" * ((4 - len(compact) % 4) % 4))
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            decoded = decoder(padded.encode("ascii"))
        except (ValueError, UnicodeEncodeError, binascii.Error):
            continue
        try:
            text_decoded = decoded.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "vless://" in text_decoded.lower():
            return text_decoded
    return ""


def _clean_vless_candidate(value: str) -> str:
    # Chat messages and copied lists often leave trailing punctuation outside the URI.
    return value.strip().rstrip(".,;)]}")


def extract_vless_uris_from_text(text: str) -> list[str]:
    """Extract unique VLESS share links from plain text or base64 subscription text."""

    raw_text = _ensure_import_text_is_small(text or "")
    sources = [raw_text]
    decoded = _try_decode_base64_text(raw_text)
    if decoded and decoded not in sources:
        sources.append(_ensure_import_text_is_small(decoded))

    candidates: list[str] = []
    seen: set[str] = set()
    for source_text in sources:
        for match in VLESS_URI_RE.findall(source_text):
            candidate = _clean_vless_candidate(match)
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            candidates.append(candidate)
            if len(candidates) >= MAX_VLESS_IMPORT_CANDIDATES:
                return candidates
    return candidates


def preview_vless_import_text(text: str, *, source: str = "manual-text") -> VlessImportPreview:
    candidates = extract_vless_uris_from_text(text)
    valid: list[VlessConnectionProfile] = []
    rejected: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        try:
            valid.append(parse_vless_uri(candidate, source=source))
        except ValueError as exc:
            rejected.append(f"candidate {index}: {exc}")
    return VlessImportPreview(
        candidate_count=len(candidates),
        valid_profiles=tuple(valid),
        rejected=tuple(rejected),
        source=source,
    )


def preview_vless_import_text_to_text(text: str, *, source: str = "manual-text") -> str:
    preview = preview_vless_import_text(text, source=source)
    if preview.candidate_count == 0:
        return "\n".join(
            [
                "VLESS import preview",
                f"source: {source}",
                "candidates: 0",
                "valid: 0",
                "status: no vless:// URI found",
                "writes files now: no",
                "raw uri printed now: no",
            ]
        )
    return preview.to_text()


def tunnel_connection_import_vless_text_to_text(text: str, *, profile_id: str = DEFAULT_PROFILE_ID, source: str = "manual-text", root: Path | None = None) -> str:
    """Import one or more VLESS links from a clipboard/text/file payload."""

    paths = ensure_tunnel_store(root)
    preview = preview_vless_import_text(text, source=source)
    if preview.candidate_count == 0:
        raise ValueError("VLESS import text does not contain a vless:// URI")
    if not preview.valid_profiles:
        details = "; ".join(preview.rejected[:3]) if preview.rejected else "unknown parse error"
        raise ValueError(f"No valid VLESS profiles found: {details}")

    existing = [item for item in _load_connections(paths, profile_id)]
    by_id = {item.connection_id: item for item in existing}
    imported_ids: list[str] = []
    for profile in preview.valid_profiles:
        by_id[profile.connection_id] = profile
        imported_ids.append(profile.connection_id)
    connections = list(by_id.values())
    connections_path = _save_connections(paths, profile_id, connections)
    selected_id = imported_ids[0]
    select_text = select_tunnel_connection(selected_id, profile_id=profile_id, root=paths.root)
    receipt_paths: list[Path] = []
    for profile in preview.valid_profiles:
        receipt_paths.append(_write_import_connection_receipt(paths, profile_id, profile))
        _append_event(paths, profile_id, "connection-imported", "VLESS tunnel connection imported from text source", profile.redacted_dict())

    lines = [
        "Tunnel VLESS batch import",
        f"profile: {profile_id}",
        f"source: {source}",
        f"candidates: {preview.candidate_count}",
        f"imported valid profiles: {preview.valid_count}",
        f"rejected candidates: {len(preview.rejected)}",
        f"connections file: {connections_path}",
        f"connection receipts: {len(receipt_paths)} in {paths.receipts_dir}",
        "raw uri printed now: no",
        "raw uri committed to repo: no",
        f"auto-selected: {selected_id}",
        "",
        "Imported profiles:",
    ]
    for index, profile in enumerate(preview.valid_profiles, start=1):
        redacted = profile.redacted_dict()
        lines.extend(
            [
                f"  {index}. {profile.connection_id}",
                f"     remarks: {profile.remarks}",
                f"     destination: {redacted['server']}:{profile.port}",
                f"     transport: {profile.network}/{profile.header_type}; security={profile.security}; encryption={profile.encryption}",
                f"     host override: {redacted['host'] or 'нет'}",
                f"     unknown query keys: {', '.join(redacted['unknownQueryKeys']) if redacted['unknownQueryKeys'] else 'нет'}",
            ]
        )
    if preview.rejected:
        lines.append("Rejected candidates:")
        for item in preview.rejected[:5]:
            lines.append(f"  - {item}")
    lines.extend(["", select_text])
    return "\n".join(lines)


def _connections_path(paths: TunnelStorePaths, profile_id: str) -> Path:
    return paths.connections_dir / f"{profile_id}.connections.json"


def _active_connection_path(paths: TunnelStorePaths, profile_id: str) -> Path:
    return paths.tunnel_root / f"{profile_id}.active-connection.json"


def _session_path(paths: TunnelStorePaths, profile_id: str) -> Path:
    return paths.runtime_dir / f"{profile_id}.session.json"


def _discord_session_path(paths: TunnelStorePaths, profile_id: str) -> Path:
    return paths.runtime_dir / f"{profile_id}.discord-session.json"


def _generated_config_path(paths: TunnelStorePaths, profile_id: str) -> Path:
    return paths.generated_dir / f"{profile_id}.core.json"


def _plan_socks_auth_path(paths: TunnelStorePaths, profile_id: str) -> Path:
    return paths.runtime_dir / f"{profile_id}.plan-socks-auth.json"


def _session_socks_auth_path(paths: TunnelStorePaths, profile_id: str) -> Path:
    return paths.runtime_dir / f"{profile_id}.session-socks-auth.json"


def new_socks_credentials() -> tuple[str, str]:
    """Per-session random RFC1929 credentials for the loopback SOCKS inbound."""

    return f"zap2-{secrets.token_urlsafe(9)}", secrets.token_urlsafe(24)


def _socks_credential_fingerprint(credentials: tuple[str, str] | None) -> str:
    if not credentials:
        return ""
    return hashlib.sha256(f"{credentials[0]}\0{credentials[1]}".encode("utf-8")).hexdigest()[:16]


def _write_socks_credentials(path: Path, credentials: tuple[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"user": credentials[0], "pass": credentials[1], "createdAt": _utc_now()}, ensure_ascii=False, indent=2) + "\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _read_socks_credentials(path: Path) -> tuple[str, str] | None:
    try:
        data = _read_json(path)
    except (OSError, ValueError):
        return None
    user, password = str(data.get("user", "")), str(data.get("pass", ""))
    if not user or not password:
        return None
    return user, password


def _session_socks_auth_mode(session: dict[str, Any]) -> str:
    mode = str(session.get("socksAuth", ""))
    if mode in SUPPORTED_SOCKS_AUTH_MODES:
        return mode
    # Сессии до этого исправления запускались с noauth inbound.
    return SOCKS_AUTH_LEGACY_NOAUTH


def _session_socks_credentials(paths: TunnelStorePaths, profile_id: str, session: dict[str, Any]) -> tuple[str, str] | None:
    if _session_socks_auth_mode(session) != SOCKS_AUTH_PASSWORD:
        return None
    return _read_socks_credentials(_session_socks_auth_path(paths, profile_id))


def socks_proxy_url(host: str, port: int, credentials: tuple[str, str] | None, *, redact: bool = True, scheme: str = "socks5h") -> str:
    if not credentials:
        return f"{scheme}://{host}:{port}"
    from urllib.parse import quote

    password = SOCKS_REDACTED if redact else quote(credentials[1], safe="")
    return f"{scheme}://{quote(credentials[0], safe='')}:{password}@{host}:{port}"


def _socks_port_is_scanned(port: int) -> bool:
    return int(port) in SOCKS_SCANNED_PORTS


def pick_random_socks_port(host: str = "127.0.0.1", *, attempts: int = 64) -> int:
    rng = secrets.SystemRandom()
    low, high = SOCKS_AUTO_PORT_RANGE
    for _ in range(attempts):
        port = rng.randint(low, high)
        if _socks_port_is_scanned(port):
            continue
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((host, port))
        except OSError:
            continue
        finally:
            sock.close()
        return port
    raise ValueError("Не удалось подобрать свободный loopback-порт для SOCKS в диапазоне 20000-60999")


def _resolve_socks_port(socks_port: int, host: str = "127.0.0.1") -> int:
    port = int(socks_port or 0)
    if port == 0:
        return pick_random_socks_port(host)
    if port < 0 or port > 65535:
        raise ValueError("--tunnel-socks-port должен быть 0 (auto) или 1..65535")
    return port


def _normalize_socks_auth_mode(value: str | None) -> str:
    mode = (value or SOCKS_AUTH_PASSWORD).strip().lower()
    if mode not in SUPPORTED_SOCKS_AUTH_MODES:
        raise ValueError(f"Неизвестный режим SOCKS auth: {value}; допустимо: {', '.join(SUPPORTED_SOCKS_AUTH_MODES)}")
    return mode


def _log_path(paths: TunnelStorePaths, profile_id: str) -> Path:
    return paths.logs_dir / f"{profile_id}.tunnel.jsonl"


def _stdout_path(paths: TunnelStorePaths, profile_id: str) -> Path:
    return paths.logs_dir / f"{profile_id}.core.stdout.log"


def _stderr_path(paths: TunnelStorePaths, profile_id: str) -> Path:
    return paths.logs_dir / f"{profile_id}.core.stderr.log"


def _discord_stdout_path(paths: TunnelStorePaths, profile_id: str) -> Path:
    return paths.logs_dir / f"{profile_id}.discord.stdout.log"


def _discord_stderr_path(paths: TunnelStorePaths, profile_id: str) -> Path:
    return paths.logs_dir / f"{profile_id}.discord.stderr.log"


def _load_connections(paths: TunnelStorePaths, profile_id: str) -> list[VlessConnectionProfile]:
    path = _connections_path(paths, profile_id)
    if not path.exists():
        return []
    data = _read_json(path)
    return [VlessConnectionProfile.from_storage_dict(item) for item in data.get("connections", [])]


def _save_connections(paths: TunnelStorePaths, profile_id: str, connections: list[VlessConnectionProfile]) -> Path:
    payload = {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "marker": TUNNEL_MARKER,
        "profileId": profile_id,
        "updatedAt": _utc_now(),
        "connections": [item.to_storage_dict() for item in connections],
    }
    path = _connections_path(paths, profile_id)
    _write_json(path, payload, secret=True)
    return path


def _append_event(paths: TunnelStorePaths, profile_id: str, event_type: str, message: str, metadata: dict[str, Any] | None = None) -> Path:
    path = _log_path(paths, profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "eventType": event_type,
        "message": message,
        "createdAt": _utc_now(),
        "metadata": metadata or {},
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def select_tunnel_connection(connection_id: str, *, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> str:
    paths = ensure_tunnel_store(root)
    connections = _load_connections(paths, profile_id)
    by_id = {item.connection_id: item for item in connections}
    if connection_id not in by_id:
        raise ValueError(f"Tunnel connection не найден: {connection_id}")
    selected = by_id[connection_id]
    path = _active_connection_path(paths, profile_id)
    _write_json(
        path,
        {
            "schemaVersion": TUNNEL_SCHEMA_VERSION,
            "stage": TUNNEL_STAGE,
            "profileId": profile_id,
            "connectionId": selected.connection_id,
            "selectedAt": _utc_now(),
            "redacted": selected.redacted_dict(),
        },
        secret=True,
    )
    log_path = _append_event(paths, profile_id, "connection-selected", "Tunnel connection selected", selected.redacted_dict())
    return "\n".join(
        [
            "Tunnel connection selected",
            f"profile: {profile_id}",
            f"connection: {selected.connection_id}",
            f"remarks: {selected.remarks}",
            f"destination: {selected.redacted_dict()['server']}:{selected.port}",
            f"transport: {selected.network}/{selected.header_type}",
            f"active file: {path}",
            f"tunnel log: {log_path}",
            "executes now: no",
            "starts tunnel now: no",
        ]
    )


def _load_active_connection(paths: TunnelStorePaths, profile_id: str) -> VlessConnectionProfile:
    active_path = _active_connection_path(paths, profile_id)
    if not active_path.exists():
        raise ValueError("Tunnel connection не выбран. Сначала выполните --tunnel-connection-import-vless или --tunnel-select-connection.")
    active = _read_json(active_path)
    connection_id = str(active.get("connectionId", ""))
    for item in _load_connections(paths, profile_id):
        if item.connection_id == connection_id:
            return item
    raise ValueError(f"Active tunnel connection отсутствует в хранилище: {connection_id}")


def _expand_uri_source(value: str) -> tuple[str, str]:
    if value.startswith("@"):
        path = Path(value[1:]).expanduser()
        return path.read_text(encoding="utf-8").strip(), f"file:{path}"
    return value, "manual-cli"


def tunnel_connection_import_vless_to_text(value: str, *, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> str:
    paths = ensure_tunnel_store(root)
    uri_text, source = _expand_uri_source(value)
    profile = parse_vless_uri(uri_text, source=source)
    connections = [item for item in _load_connections(paths, profile_id) if item.connection_id != profile.connection_id]
    connections.append(profile)
    connections_path = _save_connections(paths, profile_id, connections)
    select_text = select_tunnel_connection(profile.connection_id, profile_id=profile_id, root=paths.root)
    redacted = profile.redacted_dict()
    receipt_path = _write_import_connection_receipt(paths, profile_id, profile)
    _append_event(paths, profile_id, "connection-imported", "VLESS tunnel connection imported", redacted)
    return "\n".join(
        [
            "Tunnel VLESS connection imported",
            f"profile: {profile_id}",
            f"connection: {profile.connection_id}",
            f"remarks: {profile.remarks}",
            f"destination: {redacted['server']}:{profile.port}",
            f"security: {profile.security}; encryption: {profile.encryption}",
            f"transport: {profile.network}; headerType: {profile.header_type}",
            f"host override: {redacted['host'] or 'нет'}",
            f"unknown query keys: {', '.join(redacted['unknownQueryKeys']) if redacted['unknownQueryKeys'] else 'нет'}",
            f"connections file: {connections_path}",
            f"connection receipt: {receipt_path}",
            "raw uri printed now: no",
            "raw uri committed to repo: no",
            "auto-selected: yes",
            "",
            select_text,
        ]
    )



def tunnel_connections_table_rows(*, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> tuple[dict[str, str], ...]:
    """Return redacted rows for GUI table rendering of imported tunnel profiles."""

    paths = ensure_tunnel_store(root)
    connections = _load_connections(paths, profile_id)
    active_id = ""
    active_path = _active_connection_path(paths, profile_id)
    if active_path.exists():
        try:
            active_id = str(_read_json(active_path).get("connectionId", ""))
        except Exception:
            active_id = ""
    rows: list[dict[str, str]] = []
    for item in connections:
        redacted = item.redacted_dict()
        rows.append(
            {
                "active": "yes" if item.connection_id == active_id else "no",
                "connectionId": item.connection_id,
                "remarks": item.remarks,
                "destination": f"{redacted['server']}:{item.port}",
                "transport": f"{item.network}/{item.header_type}",
                "security": f"{item.security}; enc={item.encryption}",
                "host": redacted["host"] or "нет",
                "fingerprint": redacted["fingerprint"],
            }
        )
    return tuple(rows)


def tunnel_connections_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> str:
    paths = ensure_tunnel_store(root)
    connections = _load_connections(paths, profile_id)
    active_id = ""
    active_path = _active_connection_path(paths, profile_id)
    if active_path.exists():
        active_id = str(_read_json(active_path).get("connectionId", ""))
    lines = ["Tunnel connections", f"profile: {profile_id}", f"connections file: {_connections_path(paths, profile_id)}"]
    if not connections:
        lines.extend(["status: empty", "next: --tunnel-connection-import-vless @/path/to/link.txt"])
    else:
        lines.append("status: available")
        for item in connections:
            redacted = item.redacted_dict()
            marker = "*" if item.connection_id == active_id else " "
            lines.extend(
                [
                    f"  {marker} {item.connection_id}",
                    f"      remarks: {item.remarks}",
                    f"      destination: {redacted['server']}:{item.port}",
                    f"      transport: {item.network}/{item.header_type}; security={item.security}; encryption={item.encryption}",
                    f"      host override: {redacted['host'] or 'нет'}",
                    f"      fingerprint: {redacted['fingerprint']}",
                ]
            )
    lines.extend(["read-only: yes", "starts tunnel now: no"])
    return "\n".join(lines)


def _core_kind_from_binary(binary: str, requested: str = DEFAULT_CORE_KIND) -> str:
    if requested and requested != "auto":
        if requested not in SUPPORTED_CORE_KINDS:
            raise ValueError(f"Unsupported tunnel core kind: {requested}")
        return requested
    name = Path(binary).name.lower()
    if "sing-box" in name or name == "singbox":
        return "sing-box"
    if "v2ray" in name:
        return "v2ray"
    return "xray"


def _resolve_core_binary(value: str | None) -> tuple[str, str]:
    if value:
        return str(Path(value).expanduser()), "explicit"
    env_value = os.environ.get("ZAP2_TUNNEL_CORE")
    if env_value:
        return str(Path(env_value).expanduser()), "ZAP2_TUNNEL_CORE"
    for candidate in ("xray", "v2ray", "sing-box"):
        found = shutil.which(candidate)
        if found:
            return found, f"PATH:{candidate}"
    return "", "not-found"


def _core_argv_candidates(core_binary: str, core_kind: str, config_path: Path) -> tuple[tuple[str, ...], ...]:
    """Runtime CLI candidates, modern first with compatibility fallbacks."""

    if core_kind == "sing-box":
        return ((core_binary, "run", "-c", str(config_path)),)
    if core_kind == "v2ray":
        return (
            (core_binary, "run", "-c", str(config_path)),
            (core_binary, "-config", str(config_path)),
        )
    return (
        (core_binary, "run", "-c", str(config_path)),
        (core_binary, "run", "-config", str(config_path)),
    )


def _core_argv(core_binary: str, core_kind: str, config_path: Path) -> tuple[str, ...]:
    return _core_argv_candidates(core_binary, core_kind, config_path)[0]


def _core_test_argv_candidates(core_binary: str, core_kind: str, config_path: Path) -> tuple[tuple[str, ...], ...]:
    if core_kind == "v2ray":
        return (
            (core_binary, "run", "-test", "-c", str(config_path)),
            (core_binary, "-test", "-config", str(config_path)),
        )
    if core_kind == "xray":
        return (
            (core_binary, "run", "-test", "-c", str(config_path)),
            (core_binary, "run", "-test", "-config", str(config_path)),
        )
    return ()


def _core_test_argv(core_binary: str, core_kind: str, config_path: Path) -> tuple[str, ...]:
    candidates = _core_test_argv_candidates(core_binary, core_kind, config_path)
    return candidates[0] if candidates else ()


def _stream_settings(profile: VlessConnectionProfile, *, core_kind: str = "xray") -> dict[str, Any]:
    """Translate a VLESS URI transport into the selected core schema.

    Xray's current schema uses ``method``/``rawSettings`` and REALITY
    ``password``.  V2Ray keeps the classic ``network``/``tcpSettings`` lane.
    The split is intentional: generating one hybrid JSON for both cores made
    dry-runs look successful while the real core could reject or misinterpret
    the transport.
    """

    security = (profile.security or "none").lower()
    network = (profile.network or "tcp").lower()
    kind = (core_kind or "xray").lower()
    modern_xray = kind == "xray"

    if modern_xray:
        method_map = {
            "tcp": "raw",
            "raw": "raw",
            "ws": "websocket",
            "websocket": "websocket",
            "kcp": "mkcp",
            "mkcp": "mkcp",
            "grpc": "grpc",
            "httpupgrade": "httpupgrade",
            "xhttp": "xhttp",
            "splithttp": "xhttp",
        }
        stream: dict[str, Any] = {"method": method_map.get(network, network)}
    else:
        stream = {"network": network}

    if security != "none":
        stream["security"] = security

    if security == "tls":
        tls: dict[str, Any] = {}
        server_name = profile.sni or profile.host
        if server_name:
            tls["serverName"] = server_name
        if profile.alpn:
            tls["alpn"] = list(profile.alpn)
        if profile.allow_insecure:
            tls["allowInsecure"] = True
        if profile.raw_query.get("fp"):
            tls["fingerprint"] = profile.raw_query["fp"]
        if profile.raw_query.get("ech"):
            tls["echConfigList"] = profile.raw_query["ech"]
        if profile.raw_query.get("vcn"):
            tls["verifyPeerCertByName"] = profile.raw_query["vcn"]
        if profile.raw_query.get("pcs"):
            tls["pinnedPeerCertSha256"] = profile.raw_query["pcs"]
        if tls:
            stream["tlsSettings"] = tls
    elif security == "reality":
        reality: dict[str, Any] = {}
        server_name = profile.sni or profile.host
        public_key = profile.raw_query.get("pbk", "")
        fingerprint = profile.raw_query.get("fp", "")
        short_id = profile.raw_query.get("sid", "")
        spider_x = profile.raw_query.get("spx", "")
        if server_name:
            reality["serverName"] = server_name
        if public_key:
            # Current Xray renamed the client field from publicKey to password.
            reality["password" if modern_xray else "publicKey"] = public_key
        if fingerprint:
            reality["fingerprint"] = fingerprint
        if short_id:
            reality["shortId"] = short_id
        if spider_x:
            reality["spiderX"] = spider_x
        if profile.raw_query.get("pqv"):
            reality["mldsa65Verify"] = profile.raw_query["pqv"]
        if profile.alpn:
            reality["alpn"] = list(profile.alpn)
        if reality:
            stream["realitySettings"] = reality

    if network in {"tcp", "raw"} and profile.header_type and profile.header_type != "none":
        header: dict[str, Any] = {"type": profile.header_type}
        if profile.header_type == "http" and profile.host:
            header["request"] = {"headers": {"Host": [profile.host]}}
        stream["rawSettings" if modern_xray else "tcpSettings"] = {"header": header}
    elif network in {"ws", "websocket"}:
        ws: dict[str, Any] = {}
        if profile.path:
            ws["path"] = profile.path
        if profile.host:
            ws["headers"] = {"Host": profile.host}
        if ws:
            stream["wsSettings"] = ws
    elif network in {"kcp", "mkcp"}:
        kcp: dict[str, Any] = {}
        if profile.kcp_mtu is not None:
            kcp["mtu"] = profile.kcp_mtu
        if profile.kcp_tti is not None:
            kcp["tti"] = profile.kcp_tti
        if profile.header_type and profile.header_type != "none":
            kcp["header"] = {"type": profile.header_type}
        if profile.kcp_seed:
            kcp["seed"] = profile.kcp_seed
        stream["kcpSettings"] = kcp
    elif network == "httpupgrade":
        stream["httpupgradeSettings"] = {"host": profile.host, "path": profile.path or "/"}
    elif network in {"http", "h2"}:
        # h2 is a legacy transport name. Keep the legacy representation rather
        # than silently converting it to a different transport.
        stream.pop("method", None)
        stream["network"] = "h2"
        stream["httpSettings"] = {
            "host": [item.strip() for item in profile.host.split(",") if item.strip()],
            "path": profile.path or "/",
        }
    elif network in XHTTP_LIKE_TRANSPORTS:
        xhttp: dict[str, Any] = {"host": profile.host, "path": profile.path or "/"}
        if profile.xhttp_mode:
            xhttp["mode"] = profile.xhttp_mode
        if profile.xhttp_extra:
            try:
                xhttp["extra"] = json.loads(profile.xhttp_extra)
            except json.JSONDecodeError:
                xhttp["extra"] = profile.xhttp_extra
        stream["xhttpSettings"] = xhttp
        if not modern_xray:
            stream["network"] = "xhttp"
    elif network == "grpc":
        grpc: dict[str, Any] = {"serviceName": profile.service_name}
        if profile.authority:
            grpc["authority"] = profile.authority
        if profile.raw_query.get("mode") == "multi":
            grpc["multiMode"] = True
        stream["grpcSettings"] = grpc

    if profile.final_mask:
        try:
            stream["finalmask"] = json.loads(profile.final_mask)
        except json.JSONDecodeError:
            pass
    return stream


def generate_xray_vless_socks_config(
    profile: VlessConnectionProfile,
    *,
    socks_host: str = DEFAULT_SOCKS_HOST,
    socks_port: int = DEFAULT_SOCKS_PORT,
    udp: bool = False,
    core_kind: str = "xray",
    socks_credentials: tuple[str, str] | None = None,
    legacy_noauth: bool = False,
) -> dict[str, Any]:
    """Build Xray/V2Ray JSON with a loopback SOCKS inbound.

    By default the inbound requires RFC1929 username/password auth. Without
    explicit credentials a fresh random pair is generated, so a default config
    never contains ``noauth``. ``legacy_noauth`` is an explicit opt-in only.
    """

    kind = (core_kind or "xray").lower()
    if legacy_noauth:
        inbound_settings: dict[str, Any] = {"auth": "noauth", "udp": bool(udp), "userLevel": 8}
    else:
        user_name, user_pass = socks_credentials or new_socks_credentials()
        inbound_settings = {
            "auth": "password",
            "accounts": [{"user": user_name, "pass": user_pass}],
            "udp": bool(udp),
            "userLevel": 8,
        }
    user: dict[str, Any] = {"id": profile.user_id, "encryption": profile.encryption or "none", "level": 8}
    if profile.flow:
        user["flow"] = profile.flow

    if kind == "xray":
        vless_settings: dict[str, Any] = {
            "address": profile.server,
            "port": profile.port,
            "id": profile.user_id,
            "encryption": profile.encryption or "none",
            "level": 8,
        }
        if profile.flow:
            vless_settings["flow"] = profile.flow
    else:
        # V2Ray's stable JSON schema remains vnext/users.
        vless_settings = {"vnext": [{"address": profile.server, "port": profile.port, "users": [user]}]}

    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "zap2-discord-socks",
                "listen": socks_host,
                "port": socks_port,
                "protocol": "socks",
                "settings": inbound_settings,
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
            }
        ],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": vless_settings,
                "streamSettings": _stream_settings(profile, core_kind=kind),
                "mux": {"enabled": False},
            },
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {"domainStrategy": "AsIs", "rules": []},
    }


def _canonical_transport_name(network: str, core_kind: str) -> str:
    value = (network or "tcp").lower()
    kind = (core_kind or "xray").lower()
    if kind == "xray":
        aliases = {
            "tcp": "raw",
            "raw": "raw",
            "ws": "websocket",
            "websocket": "websocket",
            "kcp": "mkcp",
            "mkcp": "mkcp",
            "splithttp": "xhttp",
            "xhttp": "xhttp",
        }
    else:
        aliases = {
            "raw": "tcp",
            "tcp": "tcp",
            "websocket": "ws",
            "ws": "ws",
            "mkcp": "kcp",
            "kcp": "kcp",
            "http": "h2",
            "h2": "h2",
        }
    return aliases.get(value, value)


def _json_or_raw(value: str) -> Any:
    text = str(value or "")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _source_semantic_projection(profile: VlessConnectionProfile, core_kind: str) -> dict[str, Any]:
    """Canonical semantics requested by the imported VLESS URI.

    This projection is intentionally independent from the generated JSON shape;
    it lets P01 compare meaning rather than just checking that query-key names
    appeared somewhere in generator code.
    """

    network = (profile.network or "tcp").lower()
    security = (profile.security or "none").lower()
    result: dict[str, Any] = {
        "protocol": "vless",
        "server": profile.server,
        "port": profile.port,
        "userId": profile.user_id,
        "encryption": profile.encryption or "none",
        "flow": profile.flow or "",
        "security": security,
        "transport": _canonical_transport_name(network, core_kind),
    }
    if security == "tls":
        result["tls"] = {
            "serverName": profile.sni or profile.host or "",
            "alpn": list(profile.alpn),
            "allowInsecure": bool(profile.allow_insecure),
            "fingerprint": profile.raw_query.get("fp", ""),
            "echConfigList": profile.raw_query.get("ech", ""),
            "verifyPeerCertByName": profile.raw_query.get("vcn", ""),
            "pinnedPeerCertSha256": profile.raw_query.get("pcs", ""),
        }
    elif security == "reality":
        result["reality"] = {
            "serverName": profile.sni or profile.host or "",
            "publicKey": profile.raw_query.get("pbk", ""),
            "fingerprint": profile.raw_query.get("fp", ""),
            "shortId": profile.raw_query.get("sid", ""),
            "spiderX": profile.raw_query.get("spx", ""),
            "mldsa65Verify": profile.raw_query.get("pqv", ""),
            "alpn": list(profile.alpn),
        }

    if network in {"tcp", "raw"}:
        result["transportSettings"] = {
            "headerType": profile.header_type or "none",
            "host": profile.host if profile.header_type == "http" else "",
        }
    elif network in {"ws", "websocket"}:
        result["transportSettings"] = {"path": profile.path or "", "host": profile.host or ""}
    elif network in {"kcp", "mkcp"}:
        result["transportSettings"] = {
            "headerType": profile.header_type or "none",
            "seed": profile.kcp_seed or "",
            "mtu": profile.kcp_mtu,
            "tti": profile.kcp_tti,
        }
    elif network == "httpupgrade":
        result["transportSettings"] = {"host": profile.host or "", "path": profile.path or "/"}
    elif network in {"http", "h2"}:
        result["transportSettings"] = {
            "host": [item.strip() for item in profile.host.split(",") if item.strip()],
            "path": profile.path or "/",
        }
    elif network in XHTTP_LIKE_TRANSPORTS:
        result["transportSettings"] = {
            "host": profile.host or "",
            "path": profile.path or "/",
            "mode": profile.xhttp_mode or "",
            "extra": _json_or_raw(profile.xhttp_extra),
        }
    elif network == "grpc":
        result["transportSettings"] = {
            "serviceName": profile.service_name or "",
            "authority": profile.authority or "",
            "multiMode": profile.raw_query.get("mode", "") == "multi",
        }

    if profile.final_mask:
        result["finalmask"] = _json_or_raw(profile.final_mask)
    return result


def _generated_semantic_projection(config: dict[str, Any], core_kind: str) -> dict[str, Any]:
    outbound = dict(config.get("outbounds", [{}])[0])
    settings = dict(outbound.get("settings", {}))
    stream = dict(outbound.get("streamSettings", {}))
    kind = (core_kind or "xray").lower()
    if "vnext" in settings:
        vnext = dict((settings.get("vnext") or [{}])[0])
        user = dict((vnext.get("users") or [{}])[0])
        server = vnext.get("address", "")
        port = vnext.get("port")
        user_id = user.get("id", "")
        encryption = user.get("encryption", "none") or "none"
        flow = user.get("flow", "") or ""
    else:
        server = settings.get("address", "")
        port = settings.get("port")
        user_id = settings.get("id", "")
        encryption = settings.get("encryption", "none") or "none"
        flow = settings.get("flow", "") or ""

    raw_transport = stream.get("method") if kind == "xray" and stream.get("method") else stream.get("network", "tcp")
    transport = _canonical_transport_name(str(raw_transport), core_kind)
    security = str(stream.get("security", "none") or "none").lower()
    result: dict[str, Any] = {
        "protocol": str(outbound.get("protocol", "")),
        "server": server,
        "port": port,
        "userId": user_id,
        "encryption": encryption,
        "flow": flow,
        "security": security,
        "transport": transport,
    }

    if security == "tls":
        tls = dict(stream.get("tlsSettings", {}))
        result["tls"] = {
            "serverName": tls.get("serverName", "") or "",
            "alpn": list(tls.get("alpn", []) or []),
            "allowInsecure": bool(tls.get("allowInsecure", False)),
            "fingerprint": tls.get("fingerprint", "") or "",
            "echConfigList": tls.get("echConfigList", "") or "",
            "verifyPeerCertByName": tls.get("verifyPeerCertByName", "") or "",
            "pinnedPeerCertSha256": tls.get("pinnedPeerCertSha256", "") or "",
        }
    elif security == "reality":
        reality = dict(stream.get("realitySettings", {}))
        result["reality"] = {
            "serverName": reality.get("serverName", "") or "",
            "publicKey": reality.get("password", reality.get("publicKey", "")) or "",
            "fingerprint": reality.get("fingerprint", "") or "",
            "shortId": reality.get("shortId", "") or "",
            "spiderX": reality.get("spiderX", "") or "",
            "mldsa65Verify": reality.get("mldsa65Verify", "") or "",
            "alpn": list(reality.get("alpn", []) or []),
        }

    if transport in {"raw", "tcp"}:
        raw = dict(stream.get("rawSettings" if kind == "xray" else "tcpSettings", {}))
        header = dict(raw.get("header", {}))
        host = ""
        try:
            host_values = header.get("request", {}).get("headers", {}).get("Host", [])
            host = str(host_values[0]) if host_values else ""
        except (AttributeError, IndexError, TypeError):
            host = ""
        result["transportSettings"] = {"headerType": header.get("type", "none") or "none", "host": host}
    elif transport in {"websocket", "ws"}:
        ws = dict(stream.get("wsSettings", {}))
        result["transportSettings"] = {
            "path": ws.get("path", "") or "",
            "host": dict(ws.get("headers", {})).get("Host", "") or "",
        }
    elif transport in {"mkcp", "kcp"}:
        kcp = dict(stream.get("kcpSettings", {}))
        result["transportSettings"] = {
            "headerType": dict(kcp.get("header", {})).get("type", "none") or "none",
            "seed": kcp.get("seed", "") or "",
            "mtu": kcp.get("mtu"),
            "tti": kcp.get("tti"),
        }
    elif transport == "httpupgrade":
        hu = dict(stream.get("httpupgradeSettings", {}))
        result["transportSettings"] = {"host": hu.get("host", "") or "", "path": hu.get("path", "/") or "/"}
    elif transport == "h2":
        h2 = dict(stream.get("httpSettings", {}))
        result["transportSettings"] = {"host": list(h2.get("host", []) or []), "path": h2.get("path", "/") or "/"}
    elif transport == "xhttp":
        xhttp = dict(stream.get("xhttpSettings", {}))
        result["transportSettings"] = {
            "host": xhttp.get("host", "") or "",
            "path": xhttp.get("path", "/") or "/",
            "mode": xhttp.get("mode", "") or "",
            "extra": xhttp.get("extra"),
        }
    elif transport == "grpc":
        grpc = dict(stream.get("grpcSettings", {}))
        result["transportSettings"] = {
            "serviceName": grpc.get("serviceName", "") or "",
            "authority": grpc.get("authority", "") or "",
            "multiMode": bool(grpc.get("multiMode", False)),
        }
    if "finalmask" in stream:
        result["finalmask"] = stream.get("finalmask")
    return result


def _semantic_diff_labels(expected: Any, observed: Any, prefix: str = "") -> list[str]:
    if isinstance(expected, dict) and isinstance(observed, dict):
        labels: list[str] = []
        for key in sorted(expected):
            child = f"{prefix}.{key}" if prefix else key
            if key not in observed:
                labels.append(child)
            else:
                labels.extend(_semantic_diff_labels(expected[key], observed[key], child))
        return labels
    if expected != observed:
        return [prefix or "semantic-root"]
    return []


def _represented_vless_query_keys(profile: VlessConnectionProfile, core_kind: str) -> set[str]:
    represented = {"encryption", "security", "type", "flow"}
    security = (profile.security or "none").lower()
    network = (profile.network or "tcp").lower()
    if security == "tls":
        represented.update({"sni", "alpn", "insecure", "allowInsecure", "allow_insecure", "fp", "ech", "vcn", "pcs"})
    elif security == "reality":
        represented.update({"sni", "alpn", "pbk", "fp", "sid", "spx", "pqv"})
    if network in {"tcp", "raw"}:
        represented.add("headerType")
        if profile.header_type == "http":
            represented.add("host")
    elif network in {"ws", "websocket"}:
        represented.update({"host", "path"})
    elif network in {"kcp", "mkcp"}:
        represented.update({"headerType", "seed", "mtu", "tti"})
    elif network == "httpupgrade":
        represented.update({"host", "path"})
    elif network in {"http", "h2"}:
        represented.update({"host", "path"})
    elif network in XHTTP_LIKE_TRANSPORTS:
        represented.update({"host", "path", "mode", "extra"})
    elif network == "grpc":
        represented.update({"serviceName", "authority"})
        if profile.raw_query.get("mode", "") == "multi":
            represented.add("mode")
    if profile.final_mask:
        represented.add("fm")
    return represented


def _generator_scope(core_kind: str) -> dict[str, list[str]]:
    kind = (core_kind or "xray").lower()
    if kind == "xray":
        transports = ["tcp", "raw", "ws", "websocket", "kcp", "mkcp", "grpc", "httpupgrade", "http", "h2", "xhttp", "splithttp"]
        securities = ["none", "tls", "reality"]
    elif kind == "v2ray":
        transports = ["tcp", "ws", "websocket", "kcp", "mkcp", "grpc", "httpupgrade", "http", "h2"]
        securities = ["none", "tls"]
    else:
        transports = []
        securities = []
    return {
        "transports": transports,
        "securities": securities,
        "fields": sorted(KNOWN_VLESS_QUERY_KEYS),
    }


def _generation_fidelity(profile: VlessConnectionProfile, config: dict[str, Any], core_kind: str) -> dict[str, Any]:
    scope = _generator_scope(core_kind)
    network = (profile.network or "tcp").lower()
    security = (profile.security or "none").lower()
    represented = _represented_vless_query_keys(profile, core_kind)
    required_loss: list[str] = []
    if network not in scope["transports"]:
        required_loss.append(f"transport:{network}")
    if security not in scope["securities"]:
        required_loss.append(f"security:{security}")

    # Do not normalize malformed recognized values into a different meaning and
    # then call the result lossless.  The owner must fix/re-import them first.
    for key in ("insecure", "allowInsecure", "allow_insecure"):
        value = profile.raw_query.get(key)
        if value not in {None, "", "0", "1"}:
            required_loss.append(f"query:{key}-invalid-bool")
    for key in ("mtu", "tti"):
        value = profile.raw_query.get(key)
        if value not in {None, ""} and _query_int(profile.raw_query, key) is None:
            required_loss.append(f"query:{key}-invalid-int")
    if network == "grpc" and profile.raw_query.get("mode") not in {None, "", "multi"}:
        required_loss.append("query:mode-unsupported-value")

    for key, value in sorted(profile.raw_query.items()):
        if key not in KNOWN_VLESS_QUERY_KEYS or value in {"", None}:
            continue
        if key not in represented:
            required_loss.append(f"query:{key}")
    if profile.final_mask:
        try:
            json.loads(profile.final_mask)
        except json.JSONDecodeError:
            required_loss.append("query:fm-invalid-json")

    source_projection = _source_semantic_projection(profile, core_kind)
    generated_projection = _generated_semantic_projection(config, core_kind)
    semantic_mismatches = _semantic_diff_labels(source_projection, generated_projection)
    required_loss.extend(f"semantic:{label}" for label in semantic_mismatches)
    # Deterministic, de-duplicated order keeps receipts stable and reviewable.
    required_loss = sorted(set(required_loss))

    unknown = sorted(profile.unknown_query)
    if required_loss:
        support = UNSUPPORTED
        fidelity = "loss"
        reason = "required VLESS semantics differ from the generated/core-lane representation"
    elif unknown or not profile.source_hash:
        support = EXPERIMENTAL
        fidelity = "partial"
        reason = "known semantics round-trip exactly, but unknown keys or historical source provenance prevent full support"
    else:
        support = SUPPORTED
        fidelity = "full"
        reason = "all recognized required semantics round-trip exactly and source provenance is captured"
    return {
        "coreKind": core_kind,
        "sourceSemanticHash": evidence_hash_json(source_projection),
        "generatedSemanticHash": evidence_hash_json(generated_projection),
        "semanticDiff": {
            "equal": not semantic_mismatches,
            "mismatchFields": semantic_mismatches,
        },
        "semanticFidelity": fidelity,
        "requiredLoss": required_loss,
        "unclassifiedQueryKeys": unknown,
        "representedQueryKeys": sorted(represented.intersection(profile.raw_query)),
        "support": support,
        "reason": reason,
    }


def _write_generated_connection_receipt(
    paths: TunnelStorePaths,
    profile_id: str,
    profile: VlessConnectionProfile,
    *,
    core_kind: str,
    config: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    path = _connection_receipt_path(paths, profile_id, profile)
    if path.exists():
        try:
            payload = _read_json(path)
        except Exception:
            payload = {}
    else:
        payload = {}
    generation = _generation_fidelity(profile, config, core_kind)
    payload.update(
        {
            "schemaVersion": CONNECTION_RECEIPT_SCHEMA_VERSION,
            "receiptId": _connection_receipt_id(profile),
            "createdAt": str(payload.get("createdAt") or _utc_now()),
            "updatedAt": _utc_now(),
            "profileId": profile_id,
            "connectionId": profile.connection_id,
            "source": {
                "kind": _receipt_source_kind(profile.source),
                "state": "captured" if profile.source_hash else "historically_unrecoverable",
                "sourceHash": profile.source_hash or None,
            },
            "normalizedHash": profile.normalized_hash or profile.fingerprint,
            "recognizedQueryKeys": sorted(key for key in profile.raw_query if key in KNOWN_VLESS_QUERY_KEYS),
            "unknownQueryKeys": sorted(profile.unknown_query),
            "connection": _connection_receipt_summary(profile),
            "generation": generation,
            "rawUriStored": False,
        }
    )
    _write_json(path, payload, secret=False)
    return path, payload


def _sha256_file(path: str) -> str:
    file_path = Path(path)
    if not file_path.is_file():
        return ""
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _core_version_text(core_binary: str, core_kind: str) -> str:
    if not core_binary or not Path(core_binary).is_file():
        return ""
    try:
        result = subprocess.run((core_binary, "version"), text=True, capture_output=True, timeout=0.5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    text = (result.stdout or result.stderr or "").strip().splitlines()
    return text[0][:240] if text else ""


def _core_capability_record(
    core_binary: str,
    core_kind: str,
    *,
    config_test: str,
    config_hash: str,
) -> dict[str, Any]:
    binary_hash = _sha256_file(core_binary)
    # Runtime start must not execute an arbitrary/owner test core a second time
    # merely to obtain cosmetic version text. Concrete preflight records may
    # probe version; runtime-local records remain hash-bound and truthful.
    version = _core_version_text(core_binary, core_kind) if config_test in {"PASS", "FAIL", "TIMEOUT", "UNAVAILABLE"} else ""
    scope = _generator_scope(core_kind)
    identity_hash = evidence_hash_json({"kind": core_kind, "binarySha256": binary_hash, "version": version})
    return {
        "kind": core_kind,
        "version": version or "unknown",
        "binarySha256": binary_hash or None,
        "identityHash": identity_hash,
        "configHash": config_hash,
        "configTest": config_test,
        "supportedFields": scope["fields"],
        "supportedTransports": scope["transports"],
        "supportedSecurity": scope["securities"],
        "scopeNote": "generator-declared scope; actual binary support requires configTest PASS for the concrete config",
    }


VESKTOP_MANDATORY_HTTP_TARGETS = ("updates.discord.com", "discord.com")
VESKTOP_GATEWAY_TARGET = "gateway.discord.gg"
VESKTOP_MAIN_WINDOW_TARGET = "vesktop-main-window"


def _probe_failure_class(kind: str, result: str, detail: dict[str, Any] | None = None) -> str:
    if result != FAIL:
        return ""
    info = detail or {}
    message = str(info.get("message", "")).lower()
    stage = str(info.get("stage", "")).lower()
    if kind == "process":
        return "core_process"
    if kind == "listener":
        return "local_listener"
    if kind == "socks_method":
        return "socks_method"
    if kind == "socks_connect":
        return "socks_connect"
    if kind == "target_tls":
        if "timeout" in message or "timed out" in message:
            return "target_tls_timeout"
        if "eof" in message or "closed" in message or "reset" in message:
            return "target_tls_eof_or_reset"
        if "certificate" in message or "cert" in message or "verify" in message:
            return "target_tls_validation"
        return "target_tls"
    if kind == "target_http":
        if "timeout" in message or "timed out" in message:
            return "target_http_timeout"
        if "eof" in message or "closed" in message or "reset" in message:
            return "target_http_eof_or_reset"
        return "target_http"
    if kind == "websocket":
        return "gateway_websocket"
    if kind == "electron_navigation":
        return "electron_navigation"
    return stage.replace("-", "_") or f"{kind}_failure"


def _probe_span(
    *,
    run_id: str,
    kind: str,
    result: str,
    target: str = "",
    deps: tuple[str, ...] = (),
    input_hashes: dict[str, str] | None = None,
    detail: dict[str, Any] | None = None,
    limits: tuple[str, ...] = (),
    failure_class: str = "",
) -> ProbeSpan:
    detail_payload = detail or {}
    return ProbeSpan(
        span_id=f"{run_id}:{kind}:{uuid.uuid4().hex[:12]}",
        kind=kind,
        run_id=run_id,
        result=result,
        failure_class=failure_class or _probe_failure_class(kind, result, detail_payload),
        target=target,
        deps=deps,
        input_hashes=input_hashes or {},
        detail=detail_payload,
        limits=limits,
    )


def _write_evidence_graph(paths: TunnelStorePaths, graph: EvidenceGraph) -> Path:
    path = _evidence_graph_path(paths, graph.profile_id, graph.run_id)
    _write_json(path, graph.to_dict(), secret=False)
    return path


def _load_evidence_graph(paths: TunnelStorePaths, profile_id: str, run_id: str) -> EvidenceGraph:
    path = _evidence_graph_path(paths, profile_id, run_id)
    if not path.exists():
        raise ValueError(f"EvidenceGraph не найден для runId={run_id}")
    return EvidenceGraph.from_dict(_read_json(path))


def _load_bound_evidence_graph(paths: TunnelStorePaths, profile_id: str, session: dict[str, Any]) -> EvidenceGraph:
    """Load current evidence only when every run/config/receipt/core binding matches."""

    run_id = str(session.get("runId", ""))
    if not run_id:
        raise ValueError("session has no runId; historical/unbound evidence cannot satisfy current capability")
    graph = _load_evidence_graph(paths, profile_id, run_id)
    core_capability = dict(session.get("coreCapability", {}))
    expected = {
        "runId": run_id,
        "profileId": profile_id,
        "connectionId": str(session.get("connectionId", "")),
        "connectionReceiptId": str(session.get("connectionReceiptId", "")),
        "configHash": str(session.get("configHash", "")),
        "coreIdentityHash": str(core_capability.get("identityHash", "")),
    }
    observed = {
        "runId": graph.run_id,
        "profileId": graph.profile_id,
        "connectionId": graph.connection_id,
        "connectionReceiptId": graph.connection_receipt_id,
        "configHash": graph.config_hash,
        "coreIdentityHash": graph.core_identity_hash,
    }
    mismatches: list[str] = []
    for key, expected_value in expected.items():
        if not expected_value:
            mismatches.append(f"{key}:missing-session-binding")
        elif observed.get(key) != expected_value:
            mismatches.append(f"{key}:expected={expected_value},observed={observed.get(key, '')}")
    span_ids: set[str] = set()
    for span in graph.spans:
        if span.run_id != graph.run_id:
            mismatches.append(f"span:{span.span_id}:runId={span.run_id}")
        if span.span_id in span_ids:
            mismatches.append(f"span:{span.span_id}:duplicate")
        span_ids.add(span.span_id)
    for verdict in graph.verdicts:
        if verdict.run_id != graph.run_id:
            mismatches.append(f"verdict:{verdict.capability_id}:runId={verdict.run_id}")
    if mismatches:
        raise ValueError("EvidenceGraph binding mismatch; current capability stays UNKNOWN: " + "; ".join(mismatches))
    return graph


def _route_capability(graph: EvidenceGraph, target_host: str):
    return capability_from_required_spans(
        capability_id=f"route.https:{target_host}",
        run_id=graph.run_id,
        spans=graph.spans,
        requirements=(
            ("process", None),
            ("listener", None),
            ("socks_method", None),
            ("socks_connect", target_host),
            ("target_tls", target_host),
            ("target_http", target_host),
        ),
        scope={"target": target_host, "transport": "HTTPS-over-SOCKS"},
        next_experiment=f"repeat current-run HTTPS probe for {target_host}; if TLS fails, inspect correlated core/server evidence before changing knobs",
    )


def _refresh_capability_verdicts(graph: EvidenceGraph, *, client_kind: str = "vesktop") -> None:
    route_verdicts = []
    for target in VESKTOP_MANDATORY_HTTP_TARGETS:
        verdict = _route_capability(graph, target)
        graph.add_verdict(verdict)
        route_verdicts.append(verdict)
    gateway = capability_from_required_spans(
        capability_id="discord.bootstrap.gateway",
        run_id=graph.run_id,
        spans=graph.spans,
        requirements=(("websocket", VESKTOP_GATEWAY_TARGET),),
        scope={"target": VESKTOP_GATEWAY_TARGET, "subsystem": "gateway-websocket"},
        next_experiment="capture a current-run Gateway WebSocket handshake through the managed proxy path",
    )
    graph.add_verdict(gateway)
    navigation = capability_from_required_spans(
        capability_id="vesktop.navigation",
        run_id=graph.run_id,
        spans=graph.spans,
        requirements=(("electron_navigation", VESKTOP_MAIN_WINDOW_TARGET),),
        scope={"client": client_kind, "subsystem": "main-window"},
        next_experiment="launch Vesktop with the managed proxy and record a current-run main-window navigation result",
    )
    graph.add_verdict(navigation)
    app = aggregate_capability_verdicts(
        capability_id="vesktop.bootstrap",
        run_id=graph.run_id,
        verdicts=(*route_verdicts, gateway, navigation),
        scope={
            "client": client_kind,
            "mandatoryHttpTargets": list(VESKTOP_MANDATORY_HTTP_TARGETS),
            "mandatoryGateway": VESKTOP_GATEWAY_TARGET,
        },
        next_experiment="satisfy the first missing/failed current-run mandatory predicate; bypass flags do not alter this verdict",
    )
    graph.add_verdict(app)


def _graph_summary_lines(graph: EvidenceGraph) -> list[str]:
    current = {item.capability_id: item for item in graph.verdicts}
    app = current.get("vesktop.bootstrap")
    lines = [
        f"evidence run: {graph.run_id}",
        f"evidence spans: {len(graph.spans)}",
        f"route updates.discord.com: {current.get('route.https:updates.discord.com').support if current.get('route.https:updates.discord.com') else SUPPORT_UNKNOWN}",
        f"route discord.com: {current.get('route.https:discord.com').support if current.get('route.https:discord.com') else SUPPORT_UNKNOWN}",
        f"gateway websocket: {current.get('discord.bootstrap.gateway').support if current.get('discord.bootstrap.gateway') else SUPPORT_UNKNOWN}",
        f"vesktop navigation: {current.get('vesktop.navigation').support if current.get('vesktop.navigation') else SUPPORT_UNKNOWN}",
        f"vesktop bootstrap capability: {app.support if app else SUPPORT_UNKNOWN}",
    ]
    if app and app.support != SUPPORTED:
        if app.failed_requirements:
            lines.append("failed mandatory predicates: " + ", ".join(app.failed_requirements))
        if app.missing_requirements:
            lines.append("missing mandatory predicates: " + ", ".join(app.missing_requirements))
        if app.next_experiment:
            lines.append("next experiment: " + app.next_experiment)
    return lines


def _redact_core_config(config: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(config))
    for inbound in redacted.get("inbounds", []) or []:
        for account in (inbound.get("settings", {}) or {}).get("accounts", []) or []:
            if isinstance(account, dict) and "pass" in account:
                account["pass"] = SOCKS_REDACTED
    try:
        settings = redacted["outbounds"][0]["settings"]
        if "vnext" in settings:
            vnext = settings["vnext"][0]
            vnext["address"] = _redact_host(vnext.get("address", ""))
            for user in vnext.get("users", []):
                if "id" in user:
                    user["id"] = _redact_uuid(str(user["id"]))
        else:
            if "address" in settings:
                settings["address"] = _redact_host(str(settings["address"]))
            if "id" in settings:
                settings["id"] = _redact_uuid(str(settings["id"]))
        reality = redacted["outbounds"][0].get("streamSettings", {}).get("realitySettings", {})
        if "serverName" in reality:
            reality["serverName"] = _redact_host(str(reality["serverName"]))
        for key in ("password", "publicKey"):
            if key in reality:
                reality[key] = str(reality[key])[:8] + "…"
        if "shortId" in reality:
            reality["shortId"] = str(reality["shortId"])[:4] + "…"
        tls = redacted["outbounds"][0].get("streamSettings", {}).get("tlsSettings", {})
        if "serverName" in tls:
            tls["serverName"] = _redact_host(str(tls["serverName"]))
    except (KeyError, IndexError, TypeError):
        pass
    return redacted


def _write_core_capability_report(
    paths: TunnelStorePaths,
    profile_id: str,
    *,
    core_binary: str,
    core_kind: str,
    config_hash: str,
    config_test: str,
    connection_receipt_id: str,
) -> tuple[Path, dict[str, Any]]:
    capability = _core_capability_record(
        core_binary,
        core_kind,
        config_test=config_test,
        config_hash=config_hash,
    )
    payload = {
        "schemaVersion": 1,
        "createdAt": _utc_now(),
        "profileId": profile_id,
        "connectionReceiptId": connection_receipt_id,
        "coreCapability": capability,
    }
    reports_dir = paths.tunnel_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    path = reports_dir / f"{profile_id}.core-capability-{stamp}.json"
    _write_json(path, payload, secret=False)
    return path, capability


def discord_tunnel_core_preflight_to_text(
    *,
    profile_id: str = DEFAULT_PROFILE_ID,
    core_binary: str | None = None,
    core_kind: str = DEFAULT_CORE_KIND,
    socks_port: int = DEFAULT_SOCKS_PORT,
    timeout_seconds: float = 15.0,
    root: Path | None = None,
) -> str:
    """Validate a generated Xray config using upstream ``run -test``.

    Xray parses and builds the configuration, then exits before ``server.Start``.
    The preflight therefore does not leave a SOCKS listener/core process running
    and does not touch nftables/systemd. It does write the generated secret
    config with mode 0600 so the exact file intended for runtime is validated.
    """

    if socks_port < 0 or socks_port > 65535:
        raise ValueError("--tunnel-socks-port должен быть 0 (auto) или 1..65535")
    socks_port = _resolve_socks_port(socks_port)
    if timeout_seconds <= 0 or timeout_seconds > 120:
        raise ValueError("tunnel core preflight timeout должен быть >0 и <=120 секунд")

    paths = ensure_tunnel_store(root)
    connection = _load_active_connection(paths, profile_id)
    resolved_binary, source = _resolve_core_binary(core_binary)
    kind = _core_kind_from_binary(resolved_binary or "xray", core_kind)
    binary_ready = bool(resolved_binary and Path(resolved_binary).is_file() and os.access(resolved_binary, os.X_OK))
    config_path = _generated_config_path(paths, profile_id)

    lines = [
        "Discord tunnel core preflight",
        f"stage: {TUNNEL_STAGE}",
        f"profile: {profile_id}",
        f"connection: {connection.connection_id}",
        f"core kind: {kind}",
        f"core binary: {resolved_binary or 'нет'}",
        f"core binary source: {source}",
        f"core binary exists/executable: {'yes' if binary_ready else 'no'}",
        f"generated config: {config_path}",
        "writes generated config: yes (0600)",
        "requires sudo: no",
        "mutates nftables/systemd: no",
        "starts persistent core/listener: no",
    ]

    if kind == "sing-box":
        lines.extend(
            [
                "verdict: UNSUPPORTED_CORE_PREFLIGHT",
                "reason: sing-box requires a separate native config generator; Xray/V2Ray JSON is not reused",
            ]
        )
        return "\n".join(lines)
    config = generate_xray_vless_socks_config(connection, socks_host=DEFAULT_SOCKS_HOST, socks_port=socks_port, core_kind=kind)
    config_hash = _sha256_json(config)
    receipt_path, receipt = _write_generated_connection_receipt(paths, profile_id, connection, core_kind=kind, config=config)
    receipt_id = str(receipt.get("receiptId", ""))
    _write_json(config_path, config, secret=True)
    if not binary_ready:
        capability_path, _ = _write_core_capability_report(
            paths, profile_id, core_binary=resolved_binary, core_kind=kind, config_hash=config_hash,
            config_test="UNAVAILABLE", connection_receipt_id=receipt_id,
        )
        lines.extend([
            "verdict: UNAVAILABLE_CORE",
            f"connection receipt: {receipt_path}",
            f"core capability: {capability_path}",
            "next: install/select executable Xray core and repeat preflight",
        ])
        return "\n".join(lines)

    candidates = _core_test_argv_candidates(resolved_binary, kind, config_path)
    result = None
    argv: tuple[str, ...] = ()
    timeout_error: subprocess.TimeoutExpired | None = None
    for candidate in candidates:
        argv = candidate
        try:
            attempt = subprocess.run(
                candidate,
                cwd=paths.root,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            timeout_error = exc
            continue
        result = attempt
        if attempt.returncode == 0:
            break
    if result is None and timeout_error is not None:
        stdout = _tail_file_text(timeout_error.stdout if isinstance(timeout_error.stdout, str) else "", max_chars=1200)
        stderr = _tail_file_text(timeout_error.stderr if isinstance(timeout_error.stderr, str) else "", max_chars=1600)
        capability_path, _ = _write_core_capability_report(
            paths, profile_id, core_binary=resolved_binary, core_kind=kind, config_hash=config_hash,
            config_test="TIMEOUT", connection_receipt_id=receipt_id,
        )
        lines.extend(["verdict: TIMEOUT", f"timeout seconds: {timeout_seconds:g}", f"connection receipt: {receipt_path}", f"core capability: {capability_path}"])
        if stdout:
            lines.extend(["stdout tail:", stdout])
        if stderr:
            lines.extend(["stderr tail:", stderr])
        return "\n".join(lines)
    if result is None:
        capability_path, _ = _write_core_capability_report(
            paths, profile_id, core_binary=resolved_binary, core_kind=kind, config_hash=config_hash,
            config_test="FAIL", connection_receipt_id=receipt_id,
        )
        lines.extend(["verdict: FAIL", "reason: no compatible core test CLI candidate completed", f"connection receipt: {receipt_path}", f"core capability: {capability_path}"])
        return "\n".join(lines)

    stdout = _tail_file_text(result.stdout, max_chars=1200)
    stderr = _tail_file_text(result.stderr, max_chars=1600)
    config_test = "PASS" if result.returncode == 0 else "FAIL"
    capability_path, _ = _write_core_capability_report(
        paths, profile_id, core_binary=resolved_binary, core_kind=kind, config_hash=config_hash,
        config_test=config_test, connection_receipt_id=receipt_id,
    )
    lines.extend([
        f"argv: {shlex.join(argv)}",
        f"exit code: {result.returncode}",
        f"verdict: {config_test}",
        f"connection receipt: {receipt_path}",
        f"core capability: {capability_path}",
    ])
    if stdout:
        lines.extend(["stdout tail:", stdout])
    if stderr:
        lines.extend(["stderr tail:", stderr])
    return "\n".join(lines)


def _tail_file_text(text: str, *, max_chars: int) -> str:
    value = (text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


@dataclass(frozen=True)
class TunnelPlan:
    plan_id: str
    plan_hash: str
    profile_id: str
    connection: VlessConnectionProfile
    core_binary: str
    core_binary_source: str
    core_kind: str
    socks_host: str
    socks_port: int
    config_path: Path
    plan_path: Path
    rollback_path: Path
    log_path: Path
    core_exists: bool
    socks_auth_mode: str = SOCKS_AUTH_PASSWORD
    socks_credentials: tuple[str, str] | None = None

    def to_text(self) -> str:
        redacted = self.connection.redacted_dict()
        lines = [
            "Discord tunnel SOCKS/VLESS start plan",
            f"stage: {TUNNEL_STAGE}",
            f"profile: {self.profile_id}",
            f"connection: {self.connection.connection_id}",
            f"remarks: {self.connection.remarks}",
            f"destination: {redacted['server']}:{self.connection.port}",
            f"transport: {self.connection.network}/{self.connection.header_type}; security={self.connection.security}",
            f"plan id: {self.plan_id}",
            f"plan hash: {self.plan_hash}",
            f"core binary: {self.core_binary or 'not found'} ({self.core_binary_source})",
            f"core kind: {self.core_kind}",
            f"core binary exists/executable: {'yes' if self.core_exists else 'no'}",
            f"local socks: {socks_proxy_url(self.socks_host, self.socks_port, self.socks_credentials)}",
            f"socks auth: {'password (RFC1929, per-session random credentials, pass redacted)' if self.socks_auth_mode == SOCKS_AUTH_PASSWORD else 'LEGACY NOAUTH (explicit opt-in)'}",
            f"socks port scanned-list: {'yes' if _socks_port_is_scanned(self.socks_port) else 'no'}",
            f"generated config: {self.config_path}",
            f"plan file: {self.plan_path}",
            f"rollback notes: {self.rollback_path}",
            f"tunnel log: {self.log_path}",
            "requires owner confirmation: yes",
            "requires sudo: no",
            "binds to loopback only: yes",
            "downloads external binaries now: no",
            "starts tunnel now: no",
            "executes Discord now: no",
        ]
        if self.socks_auth_mode == SOCKS_AUTH_LEGACY_NOAUTH:
            lines.append(LEGACY_NOAUTH_WARNING)
        else:
            lines.append("note: Chromium/Electron --proxy-server не поддерживает SOCKS-аутентификацию; запуск Discord/Vesktop через флаг требует явного --tunnel-socks-legacy-noauth")
        if _socks_port_is_scanned(self.socks_port):
            lines.append("ВНИМАНИЕ: выбранный SOCKS-порт входит в список портов, которые сканируют локальные приложения/сайты")
        if not self.core_exists:
            lines.extend(
                [
                    "NEXT:",
                    "  Install/select an external core manually, then rerun with --tunnel-core-binary /path/to/xray-or-v2ray-or-sing-box.",
                ]
            )
        else:
            lines.extend(
                [
                    "NEXT SHELL COMMANDS:",
                    f"  PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm {self.plan_id}",
                    f"  PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-start --confirm {self.plan_id}",
                    "  PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-probe",
                    "  PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-https-probe",
                    "  PYTHONPATH=gui python -m zap2_gui.app --discord-proxy-route-plan",
                    "  PYTHONPATH=gui python -m zap2_gui.app --discord-launch-through-socks --discord-binary \"flatpak run com.discordapp.Discord\"",
                ]
            )
        return "\n".join(lines)


def _tunnel_plan_id(profile_id: str) -> str:
    return f"runtime-{profile_id}-discord-tunnel-socks-start-plan"


def _build_plan_payload(*, root: Path, profile_id: str, connection: VlessConnectionProfile, core_binary: str, core_kind: str, socks_host: str, socks_port: int, config_path: Path, core_config_hash: str, socks_auth_mode: str = SOCKS_AUTH_PASSWORD, credential_fingerprint: str = "") -> dict[str, Any]:
    auth = "password" if socks_auth_mode == SOCKS_AUTH_PASSWORD else "noauth"
    return {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "marker": TUNNEL_MARKER,
        "planId": _tunnel_plan_id(profile_id),
        "action": "discord-tunnel-start",
        "profileId": profile_id,
        "connectionId": connection.connection_id,
        "connectionFingerprint": connection.fingerprint,
        "connectionRedacted": connection.redacted_dict(),
        "core": {
            "binary": core_binary,
            "kind": core_kind,
            "argvKind": core_kind,
        },
        "localSocks": {
            "host": socks_host,
            "port": socks_port,
            "udp": False,
            "auth": auth,
            "authMode": socks_auth_mode,
            "credentialFingerprint": credential_fingerprint,
            "accessScope": "loopback-explicit-app-proxy",
            "randomPortIsAuthentication": False,
        },
        "generatedConfigPath": str(config_path.relative_to(root)),
        "generatedConfigHash": core_config_hash,
        "safety": {
            "requiresOwnerConfirmation": True,
            "requiresSudoWhenExecutedByOwner": False,
            "mayMutateFirewallWhenExecutedByOwner": False,
            "mayLaunchExternalCoreWhenExecutedByOwner": True,
            "mayLaunchDiscordWhenExecutedByOwner": False,
            "bindsLoopbackOnly": socks_host == DEFAULT_SOCKS_HOST,
            "containsRemoteBootstrap": False,
            "containsUpstreamInstallerScript": False,
            "downloadsExternalBinaries": False,
            "socksContainment": {
                "loopbackOnly": socks_host == DEFAULT_SOCKS_HOST,
                "auth": auth,
                "udp": False,
                "appAccess": "explicit proxy env/flags only",
                "randomPortIsAuthentication": False,
            },
        },
        "execution": {"executesNow": False, "startsTunnelNow": False, "executesDiscordNow": False},
    }


def discord_tunnel_plan_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, core_binary: str | None = None, core_kind: str = DEFAULT_CORE_KIND, socks_port: int = DEFAULT_SOCKS_PORT, root: Path | None = None, socks_auth_mode: str = SOCKS_AUTH_PASSWORD) -> str:
    if socks_port < 0 or socks_port > 65535:
        raise ValueError("--tunnel-socks-port должен быть 0 (auto) или 1..65535")
    auth_mode = _normalize_socks_auth_mode(socks_auth_mode)
    paths = ensure_tunnel_store(root)
    connection = _load_active_connection(paths, profile_id)
    resolved_binary, source = _resolve_core_binary(core_binary)
    kind = _core_kind_from_binary(resolved_binary or "xray", core_kind)
    if kind == "sing-box":
        raise ValueError(
            "sing-box tunnel plan временно заблокирован: текущий generator создаёт Xray/V2Ray JSON, "
            "а sing-box использует другую config schema. Нужен отдельный native sing-box generator + `sing-box check`."
        )
    core_exists = bool(resolved_binary and Path(resolved_binary).exists() and os.access(resolved_binary, os.X_OK))
    socks_port = _resolve_socks_port(socks_port, DEFAULT_SOCKS_HOST)
    plan_auth_path = _plan_socks_auth_path(paths, profile_id)
    credentials: tuple[str, str] | None = None
    if auth_mode == SOCKS_AUTH_PASSWORD:
        credentials = new_socks_credentials()
        _write_socks_credentials(plan_auth_path, credentials)
    else:
        try:
            plan_auth_path.unlink()
        except OSError:
            pass
    config = generate_xray_vless_socks_config(
        connection,
        socks_host=DEFAULT_SOCKS_HOST,
        socks_port=socks_port,
        core_kind=kind,
        socks_credentials=credentials,
        legacy_noauth=auth_mode == SOCKS_AUTH_LEGACY_NOAUTH,
    )
    config_hash = _sha256_json(config)
    config_path = _generated_config_path(paths, profile_id)
    receipt_path, receipt = _write_generated_connection_receipt(
        paths, profile_id, connection, core_kind=kind, config=config
    )
    generation = dict(receipt.get("generation", {}))
    payload = _build_plan_payload(
        root=paths.root,
        profile_id=profile_id,
        connection=connection,
        core_binary=resolved_binary,
        core_kind=kind,
        socks_host=DEFAULT_SOCKS_HOST,
        socks_port=socks_port,
        config_path=config_path,
        core_config_hash=config_hash,
        socks_auth_mode=auth_mode,
        credential_fingerprint=_socks_credential_fingerprint(credentials),
    )
    payload["connectionReceipt"] = {
        "receiptId": receipt.get("receiptId"),
        "path": str(receipt_path.relative_to(paths.root)),
        "normalizedHash": receipt.get("normalizedHash"),
        "generationSupport": generation.get("support", SUPPORT_UNKNOWN),
        "semanticFidelity": generation.get("semanticFidelity", "unbound"),
        "requiredLoss": list(generation.get("requiredLoss", [])),
        "unknownQueryKeys": list(receipt.get("unknownQueryKeys", [])),
    }
    plan_hash = plan_payload_hash(payload)
    record = {
        **payload,
        "planHash": plan_hash,
        "preparedAt": _utc_now(),
        "confirmationRequired": True,
        "confirmed": False,
        "expiresWhenPlanChanges": True,
        "allowsAutomaticReuse": False,
    }
    plan_path = paths.plans_dir / f"{payload['planId']}.json"
    rollback_path = paths.tunnel_root / "rollback" / f"{payload['planId']}.md"
    _write_json(plan_path, record, secret=False)
    rollback_path.parent.mkdir(parents=True, exist_ok=True)
    rollback_path.write_text(
        "\n".join(
            [
                f"# Rollback notes for {payload['planId']}",
                "",
                f"- plan hash: `{plan_hash}`",
                "- Stop only the managed core PID recorded in `.zap2/tunnel/runtime/default.session.json`.",
                "- Remove generated config only after the managed process has stopped.",
                "- This tunnel lane does not mutate nftables, systemd, or firewall rules.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    log_path = _append_event(paths, profile_id, "tunnel-plan-prepared", "Discord tunnel start plan prepared", {"planId": payload["planId"], "planHash": plan_hash, "connection": connection.redacted_dict()})
    text = TunnelPlan(
        plan_id=str(payload["planId"]),
        plan_hash=plan_hash,
        profile_id=profile_id,
        connection=connection,
        core_binary=resolved_binary,
        core_binary_source=source,
        core_kind=kind,
        socks_host=DEFAULT_SOCKS_HOST,
        socks_port=socks_port,
        config_path=config_path,
        plan_path=plan_path,
        rollback_path=rollback_path,
        log_path=log_path,
        core_exists=core_exists,
        socks_auth_mode=auth_mode,
        socks_credentials=credentials,
    ).to_text()
    text += "\n" + f"connection receipt: {receipt_path}"
    text += "\n" + f"semantic fidelity: {generation.get('semanticFidelity', 'unbound')}"
    text += "\n" + f"generation support: {generation.get('support', SUPPORT_UNKNOWN)}"
    if generation.get("requiredLoss"):
        text += "\nrequired semantic loss: " + ", ".join(str(item) for item in generation.get("requiredLoss", []))
    if receipt.get("unknownQueryKeys"):
        text += "\nunclassified query keys: " + ", ".join(str(item) for item in receipt.get("unknownQueryKeys", []))
    warning = _core_transport_warning(connection, kind)
    if warning:
        text += "\n\ncompatibility warning:\n" + warning
    return text


def _load_confirmed_tunnel_plan(paths: TunnelStorePaths, profile_id: str, plan_id: str) -> dict[str, Any]:
    if not plan_id:
        raise ValueError("Для --discord-tunnel-start нужен --confirm <plan-id>")
    plan_path = paths.plans_dir / f"{plan_id}.json"
    confirmation_path = paths.confirmations_dir / f"{plan_id}.confirmation.json"
    if not plan_path.exists():
        raise ValueError(f"Prepared tunnel plan не найден: {plan_id}. Сначала выполните --discord-tunnel-plan.")
    if not confirmation_path.exists():
        raise ValueError(f"Confirmation не найден для {plan_id}. Сначала выполните --runtime-confirm {plan_id}.")
    plan = _read_json(plan_path)
    confirmation = _read_json(confirmation_path)
    if str(plan.get("marker")) != TUNNEL_MARKER:
        raise ValueError(f"Plan не является Discord tunnel plan: {plan_id}")
    if str(plan.get("profileId")) != profile_id:
        raise ValueError(f"Plan profile mismatch: expected {profile_id}, got {plan.get('profileId')}")
    if str(confirmation.get("planHash")) != str(plan.get("planHash")):
        raise ValueError("Tunnel plan hash не совпадает с confirmation hash")
    payload_for_hash = {key: value for key, value in plan.items() if key not in {"planHash", "preparedAt", "confirmationRequired", "confirmed", "expiresWhenPlanChanges", "allowsAutomaticReuse", "confirmationId", "confirmedAt"}}
    if plan_payload_hash(payload_for_hash) != str(plan.get("planHash")):
        raise ValueError("Saved tunnel plan hash не совпадает с содержимым plan file")
    return plan


def _proc_state(pid: int) -> str:
    if pid <= 0:
        return "none"
    stat_path = Path("/proc") / str(pid) / "stat"
    try:
        text = stat_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "missing"
    # /proc/<pid>/stat format: pid (comm) state ...; comm can contain spaces.
    tail = text.rsplit(")", 1)[-1].strip().split()
    return tail[0] if tail else "unknown"


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # os.kill(pid, 0) is still true for zombies. Treat zombies as not running
    # because they no longer listen on SOCKS and cannot serve Discord traffic.
    state = _proc_state(pid)
    return state not in {"Z", "X", "x", "missing"}


def _read_cmdline(pid: int) -> str:
    path = Path("/proc") / str(pid) / "cmdline"
    try:
        return path.read_text(encoding="utf-8", errors="ignore").replace("\x00", " ").strip()
    except OSError:
        return ""


def discord_tunnel_status_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> str:
    paths = ensure_tunnel_store(root)
    session_path = _session_path(paths, profile_id)
    lines = ["Discord tunnel status", f"stage: {TUNNEL_STAGE}", f"profile: {profile_id}", f"session file: {session_path}"]
    if not session_path.exists():
        lines.extend(["state: not-started", "core running: no"])
    else:
        session = _read_json(session_path)
        pid = int(session.get("pid", 0) or 0)
        stored_state = str(session.get("state", "running" if pid else "not-started"))
        proc_state = _proc_state(pid) if pid else "none"
        running = stored_state == "running" and _pid_running(pid)
        lines.extend(
            [
                f"state: {'running' if running else stored_state if stored_state in {'stopped', 'failed'} else 'stale'}",
                f"stored state: {stored_state}",
                f"proc state: {proc_state}",
                f"pid: {pid if pid else 'нет'}",
                f"core running: {'yes' if running else 'no'}",
                f"connection: {session.get('connectionId', 'нет')}",
                f"local socks: {socks_proxy_url(str(session.get('socksHost', DEFAULT_SOCKS_HOST)), int(session.get('socksPort', DEFAULT_SOCKS_PORT) or 0), _session_socks_credentials(paths, profile_id, session))}",
                f"socks auth: {_session_socks_auth_mode(session)}",
                f"config: {session.get('configPath', 'нет')}",
                f"stdout: {session.get('stdoutLog', 'нет')}",
                f"stderr: {session.get('stderrLog', 'нет')}",
            ]
        )
        if not running and stored_state == "failed":
            failure = _last_core_failure_summary(paths, profile_id)
            if failure:
                lines.extend(["", "core failure details:", failure])
    try:
        active = _load_active_connection(paths, profile_id)
        lines.extend([f"active connection: {active.connection_id}", f"active remarks: {active.remarks}"])
        session_core_kind = ""
        if session_path.exists():
            try:
                session_for_warning = _read_json(session_path)
                session_core_kind = str(session_for_warning.get("coreKind", ""))
            except Exception:
                session_core_kind = ""
        warning = _core_transport_warning(active, session_core_kind)
        if warning:
            lines.extend(["", "compatibility warning:", warning])
    except ValueError:
        lines.append("active connection: none")
    lines.extend(["read-only: yes", "starts/stops now: no"])
    return "\n".join(lines)


def _assert_zapret_workflow_not_running(profile_id: str) -> None:
    try:
        status = default_workflow_status(profile_id=profile_id)
    except Exception:
        return
    if status.workflow_state == "started" or status.session_status.state == "running":
        raise ValueError(
            "Default zapret workflow уже running. Для чистого tunnel experiment сначала остановите его через --default-stop-plan/--default-stop или GUI stop."
        )


def discord_tunnel_start_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, confirm_plan_id: str = "", root: Path | None = None, allow_parallel_with_zapret: bool = False) -> str:
    paths = ensure_tunnel_store(root)
    if not allow_parallel_with_zapret:
        _assert_zapret_workflow_not_running(profile_id)
    plan = _load_confirmed_tunnel_plan(paths, profile_id, confirm_plan_id)
    connection = _load_active_connection(paths, profile_id)
    if connection.connection_id != str(plan.get("connectionId")):
        raise ValueError("Active tunnel connection changed after plan confirmation. Re-run --discord-tunnel-plan and --runtime-confirm.")
    core_binary = str(plan["core"].get("binary", ""))
    core_kind = str(plan["core"].get("kind", "xray"))
    receipt_ref = dict(plan.get("connectionReceipt", {}))
    if str(receipt_ref.get("generationSupport", SUPPORT_UNKNOWN)) == UNSUPPORTED:
        blocked_lines = [
            "Discord tunnel start: blocked",
            f"profile: {profile_id}",
            f"connection: {connection.connection_id}",
            "reason: VLESS generation has required semantic loss",
            "required loss: " + ", ".join(str(item) for item in receipt_ref.get("requiredLoss", [])),
            "capability: UNSUPPORTED",
        ]
        compatibility_warning = _core_transport_warning(connection, core_kind)
        if compatibility_warning:
            blocked_lines.extend(["", "compatibility issue:", compatibility_warning])
        blocked_lines.extend(
            [
                "next: import a compatible profile or use a generator/core lane that represents every required semantic",
                "executes core now: no",
            ]
        )
        return "\n".join(blocked_lines)
    if core_kind == "sing-box":
        return "\n".join(
            [
                "Discord tunnel start: blocked",
                f"profile: {profile_id}",
                f"connection: {connection.connection_id}",
                f"core: {core_binary} ({core_kind})",
                "reason: saved plan targets sing-box but generated config schema is Xray/V2Ray-specific",
                "next: re-plan with Xray/V2Ray or implement native sing-box generator + `sing-box check`",
                "executes core now: no",
                "executes Discord now: no",
            ]
        )
    if not core_binary or not Path(core_binary).exists() or not os.access(core_binary, os.X_OK):
        raise ValueError("Tunnel core binary отсутствует или не исполняемый. Re-run --discord-tunnel-plan --tunnel-core-binary /path/to/core.")
    compatibility_warning = _core_transport_warning(connection, core_kind)
    if compatibility_warning:
        return "\n".join(
            [
                "Discord tunnel start: blocked",
                f"profile: {profile_id}",
                f"connection: {connection.connection_id}",
                f"core: {core_binary} ({core_kind})",
                f"transport: {connection.network}",
                "",
                "compatibility issue:",
                compatibility_warning,
                "",
                "Что делать в GUI:",
                "- выбрать core binary, который поддерживает этот VLESS transport;",
                "- или импортировать другой VLESS profile без type=xhttp/splithttp;",
                "- затем нажать «Запустить tunnel core».",
                "executes core now: no",
                "executes Discord now: no",
            ]
        )
    session_path = _session_path(paths, profile_id)
    if session_path.exists():
        session = _read_json(session_path)
        pid = int(session.get("pid", 0) or 0)
        stored_state = str(session.get("state", "running" if pid else "not-started"))
        if stored_state == "running" and _pid_running(pid):
            return "\n".join(
                [
                    "Discord tunnel start: already-running",
                    f"profile: {profile_id}",
                    f"pid: {pid}",
                    f"session file: {session_path}",
                    "NEXT: --discord-tunnel-probe or --discord-launch-through-socks",
                ]
            )
    socks = dict(plan.get("localSocks", {}))
    socks_host = str(socks.get("host", DEFAULT_SOCKS_HOST))
    socks_port = int(socks.get("port", DEFAULT_SOCKS_PORT))
    auth_mode = SOCKS_AUTH_PASSWORD if str(socks.get("auth", "")) == "password" else SOCKS_AUTH_LEGACY_NOAUTH
    credentials: tuple[str, str] | None = None
    if auth_mode == SOCKS_AUTH_PASSWORD:
        credentials = _read_socks_credentials(_plan_socks_auth_path(paths, profile_id))
        if credentials is None or _socks_credential_fingerprint(credentials) != str(socks.get("credentialFingerprint", "")):
            raise ValueError("SOCKS credentials для plan отсутствуют или изменились. Re-run --discord-tunnel-plan and --runtime-confirm.")
    config = generate_xray_vless_socks_config(
        connection,
        socks_host=socks_host,
        socks_port=socks_port,
        core_kind=core_kind,
        socks_credentials=credentials,
        legacy_noauth=auth_mode == SOCKS_AUTH_LEGACY_NOAUTH,
    )
    config_hash = _sha256_json(config)
    if config_hash != str(plan.get("generatedConfigHash", "")):
        raise ValueError("Generated tunnel config changed after plan confirmation. Re-run --discord-tunnel-plan and --runtime-confirm.")
    config_path = _generated_config_path(paths, profile_id)
    _write_json(config_path, config, secret=True)
    session_auth_path = _session_socks_auth_path(paths, profile_id)
    if credentials:
        _write_socks_credentials(session_auth_path, credentials)
    else:
        try:
            session_auth_path.unlink()
        except OSError:
            pass
    run_id = new_run_id("tunnel")
    stdout_path = _stdout_path(paths, profile_id)
    stderr_path = _stderr_path(paths, profile_id)
    process: subprocess.Popen[bytes] | None = None
    argv: tuple[str, ...] = ()
    socks_probe: dict[str, Any] = {"ok": False, "message": "core was not started"}
    running = False
    attempted_argv: list[list[str]] = []
    for candidate in _core_argv_candidates(core_binary, core_kind, config_path):
        argv = candidate
        attempted_argv.append(list(candidate))
        stdout_handle = stdout_path.open("ab")
        stderr_handle = stderr_path.open("ab")
        try:
            process = subprocess.Popen(candidate, cwd=str(paths.root), stdout=stdout_handle, stderr=stderr_handle, start_new_session=True)
        finally:
            stdout_handle.close()
            stderr_handle.close()
        socks_probe = _wait_for_socks5_handshake(socks_host, socks_port, deadline_seconds=3.0, timeout=0.35, credentials=credentials)
        process_alive = process.poll() is None
        running = process_alive and bool(socks_probe.get("ok"))
        if running:
            break
        if process_alive:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass
    assert process is not None
    process_alive = process.poll() is None
    core_capability = _core_capability_record(
        core_binary,
        core_kind,
        config_test="RUNTIME_LOCAL_ACCEPTANCE" if running else "RUNTIME_LOCAL_REJECTED",
        config_hash=config_hash,
    )
    session_payload = {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "marker": TUNNEL_MARKER,
        "profileId": profile_id,
        "planId": confirm_plan_id,
        "planHash": str(plan.get("planHash")),
        "runId": run_id,
        "connectionId": connection.connection_id,
        "connectionReceiptId": str(receipt_ref.get("receiptId", "")),
        "connectionReceiptPath": str(receipt_ref.get("path", "")),
        "generationSupport": str(receipt_ref.get("generationSupport", SUPPORT_UNKNOWN)),
        "coreBinary": core_binary,
        "coreKind": core_kind,
        "argv": list(argv),
        "attemptedArgv": attempted_argv,
        "pid": process.pid,
        "startedAt": _utc_now(),
        "socksHost": socks_host,
        "socksPort": socks_port,
        "socksAuth": auth_mode,
        "socksCredentialFingerprint": _socks_credential_fingerprint(credentials),
        "containment": {
            "loopbackOnly": socks_host == DEFAULT_SOCKS_HOST,
            "auth": "password" if credentials else "noauth",
            "udp": False,
            "appAccess": "explicit proxy env/flags only",
            "randomPortIsAuthentication": False,
        },
        "configPath": str(config_path),
        "configHash": config_hash,
        "coreCapability": core_capability,
        "stdoutLog": str(stdout_path),
        "stderrLog": str(stderr_path),
        "runningAfterGrace": running,
        "socksReady": bool(socks_probe.get("ok")),
        "socksProbe": socks_probe,
        "state": "running" if running else "failed",
    }
    graph = EvidenceGraph(
        run_id=run_id,
        profile_id=profile_id,
        connection_id=connection.connection_id,
        connection_receipt_id=str(receipt_ref.get("receiptId", "")),
        core_identity_hash=str(core_capability.get("identityHash", "")),
        config_hash=config_hash,
        environment={"coreKind": core_kind, "socksBind": socks_host, "socksPort": socks_port},
    )
    process_span = _probe_span(
        run_id=run_id,
        kind="process",
        result=PASS if process_alive else FAIL,
        detail={"pid": process.pid, "coreKind": core_kind},
        input_hashes={"config": config_hash, "core": str(core_capability.get("binarySha256") or "")},
    )
    graph.add_span(process_span)
    listener_span = _probe_span(
        run_id=run_id,
        kind="listener",
        result=PASS if bool(socks_probe.get("portOpen")) else FAIL,
        deps=(process_span.span_id,),
        detail={"bind": socks_host, "port": socks_port, "message": socks_probe.get("message", "")},
    )
    graph.add_span(listener_span)
    method_span = _probe_span(
        run_id=run_id,
        kind="socks_method",
        result=PASS if bool(socks_probe.get("ok")) else FAIL,
        deps=(listener_span.span_id,),
        detail={"method": "password" if credentials else "noauth", "insecureNoAuth": bool(socks_probe.get("insecureNoAuth")), "message": socks_probe.get("message", "")},
        limits=("SOCKS method PASS proves only local proxy protocol readiness, not remote route/TLS/app capability",),
    )
    graph.add_span(method_span)
    _refresh_capability_verdicts(graph)
    evidence_path = _write_evidence_graph(paths, graph)
    session_payload["evidenceGraphPath"] = str(evidence_path)
    _write_json(session_path, session_payload, secret=True)
    log_path = _append_event(
        paths,
        profile_id,
        "tunnel-started" if running else "tunnel-start-failed",
        "External tunnel core launched and SOCKS5 became ready" if running else "External tunnel core did not expose a valid SOCKS5 listener",
        {"pid": process.pid, "running": running, "socksProbe": socks_probe, "connection": connection.redacted_dict()},
    )
    failure_tail = _last_core_failure_summary(paths, profile_id) if not running else ""
    result_lines = [
            f"Discord tunnel start: {'started' if running else 'failed'}",
            f"profile: {profile_id}",
            f"connection: {connection.connection_id}",
            f"pid: {process.pid}",
            f"core: {core_binary} ({core_kind})",
            f"local socks: {socks_proxy_url(socks_host, socks_port, credentials)}",
            f"socks auth: {auth_mode}",
            f"config: {config_path}",
            f"session file: {session_path}",
            f"stdout: {stdout_path}",
            f"stderr: {stderr_path}",
            f"tunnel log: {log_path}",
            f"run id: {run_id}",
            f"evidence graph: {evidence_path}",
            f"generation support: {receipt_ref.get('generationSupport', SUPPORT_UNKNOWN)}",
            "network truth: local SOCKS readiness does NOT imply remote route/TLS/Vesktop support",
            "owner confirmation verified: yes",
            "requires sudo: no",
            "mutates firewall/services: no",
            f"parallel with zapret allowed: {'yes' if allow_parallel_with_zapret else 'no'}",
            "executes Discord now: no",
            *([LEGACY_NOAUTH_WARNING] if auth_mode == SOCKS_AUTH_LEGACY_NOAUTH else []),
            "NEXT: PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-probe" if running else "NEXT: inspect core stderr/config, fix profile/core compatibility, then start again",
        ]
    if not running:
        result_lines.extend([f"SOCKS readiness: failed ({socks_probe.get('message', 'unknown')})"] )
        if failure_tail:
            result_lines.extend(["", "core failure details:", failure_tail])
    return "\n".join(result_lines)


def discord_tunnel_stop_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> str:
    paths = ensure_tunnel_store(root)
    session_path = _session_path(paths, profile_id)
    if not session_path.exists():
        return "\n".join(["Discord tunnel stop: not-started", f"profile: {profile_id}", f"session file: {session_path}", "stops now: no"])
    session = _read_json(session_path)
    pid = int(session.get("pid", 0) or 0)
    core_binary = str(session.get("coreBinary", ""))
    cmdline = _read_cmdline(pid) if pid else ""
    if not pid or not _pid_running(pid):
        session["stoppedAt"] = _utc_now()
        session["state"] = "stale"
        _write_json(session_path, session, secret=True)
        return "\n".join(["Discord tunnel stop: stale", f"profile: {profile_id}", f"pid: {pid if pid else 'нет'}", f"session file: {session_path}"])
    if core_binary and cmdline and Path(core_binary).name not in cmdline and core_binary not in cmdline:
        raise ValueError("Recorded PID command line no longer looks like the managed core; refusing to kill it.")
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if not _pid_running(pid):
            break
        time.sleep(0.1)
    if _pid_running(pid):
        os.kill(pid, signal.SIGKILL)
    session["stoppedAt"] = _utc_now()
    session["state"] = "stopped"
    _write_json(session_path, session, secret=True)
    log_path = _append_event(paths, profile_id, "tunnel-stopped", "Managed tunnel core stopped", {"pid": pid})
    return "\n".join(
        [
            "Discord tunnel stop: stopped",
            f"profile: {profile_id}",
            f"pid: {pid}",
            f"session file: {session_path}",
            f"tunnel log: {log_path}",
            "kills only recorded pid: yes",
            "mutates firewall/services: no",
        ]
    )


def _connect_loopback(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _socks5_negotiate(sock: socket.socket, credentials: tuple[str, str] | None) -> dict[str, Any]:
    """SOCKS5 method negotiation (+ RFC1929 username/password when credentials are given).

    With credentials the client offers both NO_AUTH (0x00) and USERNAME/PASSWORD
    (0x02): a listener that picks 0x00 accepts unauthenticated clients and is
    reported as an insecure finding instead of a ready proxy.
    """

    if credentials:
        sock.sendall(b"\x05\x02\x00\x02")
    else:
        sock.sendall(b"\x05\x01\x00")
    hello = _read_exact(sock, 2)
    if hello[0:1] != b"\x05":
        return {"ok": False, "methodOk": False, "stage": "socks5-greeting", "responseHex": hello.hex(), "insecureNoAuth": False,
                "message": "loopback port did not return a SOCKS5 greeting"}
    method = hello[1]
    if method == 0x00:
        if credentials:
            return {"ok": False, "methodOk": False, "stage": "socks5-greeting", "responseHex": hello.hex(), "insecureNoAuth": True,
                    "message": "INSECURE: SOCKS5 listener accepts NO_AUTH (0x00); любой локальный процесс может использовать proxy"}
        return {"ok": True, "methodOk": True, "stage": "socks5-greeting", "responseHex": hello.hex(), "insecureNoAuth": True,
                "message": "SOCKS5 no-auth greeting accepted (legacy noauth, insecure)"}
    if method == 0x02 and credentials:
        user = credentials[0].encode("utf-8")
        password = credentials[1].encode("utf-8")
        if len(user) > 255 or len(password) > 255:
            raise ValueError("SOCKS credentials are too long for RFC1929")
        sock.sendall(b"\x01" + bytes([len(user)]) + user + bytes([len(password)]) + password)
        reply = _read_exact(sock, 2)
        ok = reply == b"\x01\x00"
        return {"ok": ok, "methodOk": ok, "stage": "socks5-auth", "responseHex": hello.hex() + reply.hex(), "insecureNoAuth": False,
                "message": "SOCKS5 username/password auth accepted" if ok else "SOCKS5 username/password auth rejected"}
    return {"ok": False, "methodOk": False, "stage": "socks5-greeting", "responseHex": hello.hex(), "insecureNoAuth": False,
            "message": f"SOCKS5 listener did not accept offered auth method (got 0x{method:02x})"}


def _socks5_handshake_probe(host: str, port: int, timeout: float = 2.0, *, credentials: tuple[str, str] | None = None) -> dict[str, Any]:
    """Verify that the loopback listener speaks SOCKS5 with the expected auth.

    A plain TCP connect followed by close makes v2ray/xray log
    `proxy/socks: insufficient header > EOF`, which looks scarier than it is.
    The handshake probe sends a real SOCKS5 greeting (and RFC1929 auth when the
    session has credentials) so the report can separate "port is open" from
    "this is a usable, authenticated SOCKS listener".
    """

    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            try:
                result = _socks5_negotiate(sock, credentials)
            except (OSError, ValueError) as exc:
                return {
                    "ok": False,
                    "portOpen": True,
                    "stage": "socks5-greeting",
                    "insecureNoAuth": False,
                    "message": f"SOCKS5 negotiation failed: {exc}",
                    "elapsedMs": int((time.monotonic() - started) * 1000),
                }
    except OSError as exc:
        return {
            "ok": False,
            "portOpen": False,
            "stage": "connect",
            "message": str(exc),
            "elapsedMs": int((time.monotonic() - started) * 1000),
        }
    result.pop("methodOk", None)
    return {**result, "portOpen": True, "authMethod": "password" if credentials else "noauth", "elapsedMs": int((time.monotonic() - started) * 1000)}


def _wait_for_socks5_handshake(host: str, port: int, *, deadline_seconds: float = 5.0, timeout: float = 0.5, credentials: tuple[str, str] | None = None) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.1, deadline_seconds)
    last: dict[str, Any] = {"ok": False, "message": "probe not started"}
    while time.monotonic() < deadline:
        last = _socks5_handshake_probe(host, port, timeout=timeout, credentials=credentials)
        if bool(last.get("ok")) or bool(last.get("insecureNoAuth")):
            return last
        time.sleep(0.1)
    return last


def discord_tunnel_probe_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> str:
    paths = ensure_tunnel_store(root)
    session_path = _session_path(paths, profile_id)
    lines = ["Discord tunnel probe", f"stage: {TUNNEL_STAGE}", f"profile: {profile_id}"]
    if not session_path.exists():
        lines.extend(["state: not-started", "verdict: T0_NOT_RUNNING", "next: --discord-tunnel-plan; --runtime-confirm; --discord-tunnel-start"])
        return "\n".join(lines)
    session = _read_json(session_path)
    pid = int(session.get("pid", 0) or 0)
    stored_state = str(session.get("state", "running" if pid else "not-started"))
    running = stored_state == "running" and _pid_running(pid)
    socks_host = str(session.get("socksHost", DEFAULT_SOCKS_HOST))
    socks_port = int(session.get("socksPort", DEFAULT_SOCKS_PORT))
    socks_credentials = _session_socks_credentials(paths, profile_id, session)
    socks_probe = _socks5_handshake_probe(socks_host, socks_port, credentials=socks_credentials)
    port_open = bool(socks_probe.get("portOpen"))
    handshake_ok = bool(socks_probe.get("ok"))
    if running and socks_probe.get("insecureNoAuth") and socks_credentials:
        verdict = "T0_SOCKS_INSECURE_NOAUTH"
    elif running and handshake_ok:
        verdict = "T0_SOCKS_READY"
    elif running and port_open:
        verdict = "T0_PORT_OPEN_NOT_SOCKS"
    elif stored_state == "failed":
        verdict = "T0_CORE_FAILED"
    else:
        verdict = "T0_CORE_NOT_READY"

    run_id = str(session.get("runId", ""))
    evidence_path = ""
    graph: EvidenceGraph | None = None
    if run_id:
        try:
            graph = _load_bound_evidence_graph(paths, profile_id, session)
            input_hashes = {
                "configHash": str(session.get("configHash", "")),
                "coreIdentityHash": str((session.get("coreCapability") or {}).get("identityHash", "")),
            }
            process_span = _probe_span(
                run_id=run_id,
                kind="process",
                result=PASS if running else FAIL,
                input_hashes=input_hashes,
                detail={"pid": pid, "storedState": stored_state, "procState": _proc_state(pid) if pid else "none"},
                limits=("process liveness does not prove listener, route, TLS, HTTP, or application readiness",),
            )
            graph.add_span(process_span)
            listener_span = _probe_span(
                run_id=run_id,
                kind="listener",
                result=PASS if port_open else FAIL,
                deps=(process_span.span_id,),
                input_hashes=input_hashes,
                detail={"host": socks_host, "port": socks_port, "portOpen": port_open},
                limits=("local TCP listener does not prove SOCKS semantics or upstream reachability",),
            )
            graph.add_span(listener_span)
            method_span = _probe_span(
                run_id=run_id,
                kind="socks_method",
                result=PASS if handshake_ok else FAIL,
                deps=(listener_span.span_id,),
                input_hashes=input_hashes,
                detail={"method": "USERNAME_PASSWORD" if socks_credentials else "NO_AUTH", "insecureNoAuth": bool(socks_probe.get("insecureNoAuth")), "probeStage": socks_probe.get("stage", ""), "message": socks_probe.get("message", "")},
                limits=("SOCKS method negotiation is local-only evidence; it cannot satisfy remote route/TLS/application predicates",),
            )
            graph.add_span(method_span)
            _refresh_capability_verdicts(graph)
            evidence_path = str(_write_evidence_graph(paths, graph))
        except (ValueError, OSError, TypeError):
            graph = None

    report = {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "createdAt": _utc_now(),
        "profileId": profile_id,
        "runId": run_id or None,
        "connectionReceiptId": session.get("connectionReceiptId"),
        "configHash": session.get("configHash"),
        "pid": pid,
        "coreRunning": running,
        "storedState": stored_state,
        "procState": _proc_state(pid) if pid else "none",
        "socksHost": socks_host,
        "socksPort": socks_port,
        "socksPortOpen": port_open,
        "socksHandshakeOk": handshake_ok,
        "socksAuth": _session_socks_auth_mode(session),
        "socksInsecureNoAuth": bool(socks_probe.get("insecureNoAuth")),
        "socksHandshake": socks_probe,
        "upstreamTested": False,
        "localVerdict": verdict,
        "evidenceGraph": evidence_path or None,
        "capabilityNote": "local SOCKS evidence cannot satisfy remote route/TLS/HTTP/Vesktop predicates",
        "verdict": verdict,
    }
    reports_dir = paths.tunnel_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{profile_id}.tunnel-probe.json"
    _write_json(report_path, report, secret=False)
    _append_event(paths, profile_id, "tunnel-probed", "Tunnel SOCKS handshake probe completed", {"runId": run_id or None, "verdict": verdict, "socksPortOpen": port_open, "socksHandshakeOk": handshake_ok})
    lines.extend(
        [
            f"pid: {pid if pid else 'нет'}",
            f"stored state: {stored_state}",
            f"proc state: {_proc_state(pid) if pid else 'none'}",
            f"core running: {'yes' if running else 'no'}",
            f"local socks: {socks_proxy_url(socks_host, socks_port, socks_credentials)}",
            f"socks auth: {_session_socks_auth_mode(session)}",
            f"socks port open: {'yes' if port_open else 'no'}",
            f"socks handshake: {'ok' if handshake_ok else 'no'}",
            f"probe message: {socks_probe.get('message', 'n/a')}",
            *(["insecure finding: SOCKS listener accepts NO_AUTH (localhost ≠ private)"] if socks_probe.get("insecureNoAuth") else []),
            "upstream tested: no",
            f"verdict: {verdict}",
            "verdict scope: local compatibility status only; remote/application capability is separate",
            "capability truth: local SOCKS readiness != remote route/TLS/HTTP/Vesktop support",
            f"report: {report_path}",
        ]
    )
    if graph is not None:
        lines.extend(["", "Typed EvidenceGraph (authoritative for capability):", *_graph_summary_lines(graph), f"evidence graph: {evidence_path}"])
    else:
        lines.extend(["", "Typed EvidenceGraph: unavailable/legacy-unbound session; no remote capability may be inferred."])
    failure = _last_core_failure_summary(paths, profile_id) if verdict == "T0_CORE_FAILED" else ""
    if failure:
        lines.extend(["", "core failure details:", failure])
    if verdict == "T0_CORE_FAILED":
        lines.append("NEXT: fix the core/profile compatibility, then run tunnel start again. Do not launch Discord yet.")
    else:
        lines.append("NEXT: run --discord-tunnel-https-probe for each required remote target; local SOCKS PASS is insufficient.")
    lines.extend(["executes Discord now: no", "mutates firewall/services: no"])
    return "\n".join(lines)


def discord_tunnel_evidence_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> str:
    """Render the current run-bound evidence graph and capability verdicts read-only."""

    paths = ensure_tunnel_store(root)
    session_path = _session_path(paths, profile_id)
    lines = ["Discord tunnel typed evidence", f"stage: {TUNNEL_STAGE}", f"profile: {profile_id}"]
    if not session_path.exists():
        return "\n".join([*lines, "state: no tunnel session", "capability: UNKNOWN", "reason: no current run-bound evidence"])
    session = _read_json(session_path)
    run_id = str(session.get("runId", ""))
    if not run_id:
        return "\n".join([*lines, "state: legacy/unbound session", "capability: UNKNOWN", "reason: session has no runId; stale/legacy success is not accepted as current evidence"])
    try:
        graph = _load_bound_evidence_graph(paths, profile_id, session)
    except (ValueError, OSError, TypeError) as exc:
        return "\n".join([*lines, f"run: {run_id}", "capability: UNKNOWN", f"reason: {exc}"])

    _refresh_capability_verdicts(graph)
    evidence_path = _write_evidence_graph(paths, graph)
    lines.extend(
        [
            f"run: {graph.run_id}",
            f"connection receipt: {graph.connection_receipt_id or 'unknown'}",
            f"config hash: {graph.config_hash or 'unknown'}",
            f"core identity hash: {graph.core_identity_hash or 'unknown'}",
            f"evidence graph: {evidence_path}",
            "",
            "Capability summary:",
            *_graph_summary_lines(graph),
            "",
            "Probe spans (current graph):",
        ]
    )
    for span in graph.spans:
        target = f" @{span.target}" if span.target else ""
        deps = f" deps={','.join(span.deps)}" if span.deps else ""
        failure = f" failureClass={span.failure_class}" if span.failure_class else ""
        lines.append(f"  {span.result:8} {span.kind}{target}; id={span.span_id}{deps}{failure}")
        for limit in span.limits:
            lines.append(f"    limit: {limit}")
    lines.extend(["", "Capability verdicts:"])
    for verdict in sorted(graph.verdicts, key=lambda item: item.capability_id):
        lines.append(f"  {verdict.capability_id}: {verdict.support} — {verdict.reason}")
        if verdict.failed_requirements:
            lines.append("    failed: " + ", ".join(verdict.failed_requirements))
        if verdict.missing_requirements:
            lines.append("    missing/unknown: " + ", ".join(verdict.missing_requirements))
        if verdict.stale_evidence_ignored:
            lines.append("    stale ignored: " + ", ".join(verdict.stale_evidence_ignored))
        if verdict.next_experiment and verdict.support != SUPPORTED:
            lines.append("    next: " + verdict.next_experiment)
    lines.extend(
        [
            "",
            "Truth rule: process/listener/SOCKS PASS never implies route/TLS/HTTP/application PASS.",
            "Truth rule: bypass/force-launch controls execution only; they never alter CapabilityVerdict.",
            "read-only: yes",
            "executes Discord now: no",
            "mutates firewall/services: no",
        ]
    )
    return "\n".join(lines)


def _flatpak_app_installed(app_id: str) -> bool:
    flatpak = shutil.which("flatpak")
    if not flatpak:
        return False
    try:
        result = subprocess.run(
            (flatpak, "info", app_id),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _auto_discord_command() -> str:
    # Prefer Vesktop because it is the requested compatibility target, then
    # fall back to the official Discord clients.  No installation is attempted.
    if shutil.which(VESKTOP_COMMAND):
        return VESKTOP_COMMAND
    if _flatpak_app_installed("dev.vencord.Vesktop"):
        return FLATPAK_VESKTOP_COMMAND
    if shutil.which(DEFAULT_DISCORD_COMMAND):
        return DEFAULT_DISCORD_COMMAND
    if _flatpak_app_installed("com.discordapp.Discord"):
        return FLATPAK_DISCORD_COMMAND
    raise ValueError(
        "Discord/Vesktop command не найден. Установите native/Flatpak client или передайте явный --discord-binary."
    )


def _client_kind_from_command(argv: tuple[str, ...], raw: str) -> str:
    haystack = " ".join((*argv, raw)).lower()
    if "vesktop" in haystack or "dev.vencord.vesktop" in haystack:
        return "vesktop"
    if "discord" in haystack or "com.discordapp.discord" in haystack:
        return "discord"
    return "electron-client"


def _resolve_discord_launch_command(discord_command: str) -> tuple[tuple[str, ...], str]:
    raw = (discord_command or AUTO_DISCORD_COMMAND).strip()
    if raw.lower() == AUTO_DISCORD_COMMAND:
        raw = _auto_discord_command()
    if not raw:
        raise ValueError("Discord/Vesktop command пустой.")
    parts = tuple(shlex.split(raw)) if any(ch.isspace() for ch in raw) else (raw,)
    if not parts:
        raise ValueError("Discord/Vesktop command пустой после parsing.")
    first = parts[0]
    resolved_first = shutil.which(first) or str(Path(first).expanduser())
    if not resolved_first or not Path(resolved_first).exists():
        raise ValueError(
            "Discord/Vesktop command не найден. Примеры: vesktop, 'flatpak run dev.vencord.Vesktop', discord."
        )
    return (resolved_first, *parts[1:]), raw


def _discord_launch_argv(discord_command: str, socks_host: str, socks_port: int, mode: str) -> tuple[tuple[str, ...], str]:
    base_argv, raw = _resolve_discord_launch_command(discord_command)
    proxy = f"socks5://{socks_host}:{socks_port}"
    if mode == "socks-env-only":
        return base_argv, raw
    extra: list[str] = [f"--proxy-server={proxy}"]
    # Discord/Vesktop are Chromium/Electron. Disabling QUIC keeps updater/web
    # traffic on the TCP SOCKS path instead of allowing UDP/443 to bypass it.
    if not any(item == "--disable-quic" for item in base_argv):
        extra.append("--disable-quic")
    return (*base_argv, *extra), raw


def _is_flatpak_command(argv: tuple[str, ...]) -> bool:
    return bool(argv) and Path(argv[0]).name == "flatpak" and "run" in argv[:3]


def discord_proxy_route_plan_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> str:
    """Explain the missing routing step between local SOCKS and Discord."""

    paths = ensure_tunnel_store(root)
    session_path = _session_path(paths, profile_id)
    socks_host = DEFAULT_SOCKS_HOST
    socks_port = DEFAULT_SOCKS_PORT
    state = "not-started"
    credentials: tuple[str, str] | None = None
    auth_mode = SOCKS_AUTH_PASSWORD
    if session_path.exists():
        session = _read_json(session_path)
        socks_host = str(session.get("socksHost", DEFAULT_SOCKS_HOST))
        socks_port = int(session.get("socksPort", DEFAULT_SOCKS_PORT))
        pid = int(session.get("pid", 0) or 0)
        stored_state = str(session.get("state", "running" if pid else "not-started"))
        state = "running" if stored_state == "running" and _pid_running(pid) else stored_state if stored_state in {"stopped", "failed"} else "stale"
        auth_mode = _session_socks_auth_mode(session)
        credentials = _session_socks_credentials(paths, profile_id, session)
    proxy = socks_proxy_url(socks_host, socks_port, credentials)
    curl_proxy = socks_proxy_url(socks_host, socks_port, credentials) if credentials else f"socks5h://{socks_host}:{socks_port}"
    return "\n".join(
        [
            "Discord proxy route plan",
            f"stage: {TUNNEL_STAGE}",
            f"profile: {profile_id}",
            f"tunnel session state: {state}",
            f"local socks: {proxy}",
            "",
            "What this means:",
            "- Starting VLESS tunnel only opens a local SOCKS listener.",
            "- It does not transparently route Discord, Firefox, Telegram, or Flatpak apps by itself.",
            "- Zapret owner-rules and SOCKS tunnel are separate lanes unless a client is explicitly launched/configured to use SOCKS.",
            "",
            "Useful commands:",
            f"- Auto (Vesktop first): PYTHONPATH=gui python -m zap2_gui.app --discord-launch-through-socks --discord-binary auto",
            f"- Flatpak Vesktop: PYTHONPATH=gui python -m zap2_gui.app --discord-launch-through-socks --discord-binary \"{FLATPAK_VESKTOP_COMMAND}\"",
            f"- Flatpak Discord: PYTHONPATH=gui python -m zap2_gui.app --discord-launch-through-socks --discord-binary \"{FLATPAK_DISCORD_COMMAND}\"",
            f"- Curl check:      curl --proxy '{curl_proxy}' -I https://updates.discord.com/",
            f"- SOCKS auth: {auth_mode}" + (" (пароль хранится в .zap2/tunnel/runtime/<profile>.session-socks-auth.json, 0600; здесь скрыт)" if credentials else ""),
            "- Chromium/Electron --proxy-server не поддерживает SOCKS-аутентификацию: запуск через флаг требует явного --tunnel-socks-legacy-noauth (небезопасно).",
            *([LEGACY_NOAUTH_WARNING] if auth_mode == SOCKS_AUTH_LEGACY_NOAUTH and state != "not-started" else []),
            "",
            "Firefox/web Discord:",
            f"- Set manual SOCKS v5 host={socks_host}, port={socks_port}, and enable remote DNS through SOCKS if available.",
            "- Firefox не задаёт логин/пароль SOCKS в настройках; для password-режима используйте приложение с поддержкой socks5h://user:pass@ или HTTP-прокси-обёртку.",
            "- Browser windows opened without that proxy setting will keep using the normal direct route.",
            "",
            "Telegram note:",
            "- If Telegram shows the proxy as unavailable while the SOCKS handshake is OK, the local port is alive but the upstream VLESS path or target reachability still needs HTTPS/TCP testing.",
            "read-only: yes",
        ]
    )


def discord_launch_through_socks_to_text(
    *,
    profile_id: str = DEFAULT_PROFILE_ID,
    discord_binary: str = DEFAULT_DISCORD_COMMAND,
    launch_mode: str = "socks-updater-window",
    root: Path | None = None,
    upstream_preflight: bool = False,
    preflight_host: str = "updates.discord.com",
    preflight_path: str = "/",
    preflight_timeout: float = 8.0,
    allow_failed_preflight: bool = False,
) -> str:
    if launch_mode not in SUPPORTED_LAUNCH_MODES:
        raise ValueError(f"Unsupported launch mode: {launch_mode}")
    paths = ensure_tunnel_store(root)
    session_path = _session_path(paths, profile_id)
    if not session_path.exists():
        raise ValueError("Tunnel session не найден. Сначала запустите --discord-tunnel-start.")
    session = _read_json(session_path)
    pid = int(session.get("pid", 0) or 0)
    stored_state = str(session.get("state", "running" if pid else "not-started"))
    if stored_state != "running" or not _pid_running(pid):
        failure = _last_core_failure_summary(paths, profile_id)
        message = (
            "Tunnel core не running. Сейчас session state="
            f"{stored_state}, pid={pid if pid else 'нет'}, proc={_proc_state(pid) if pid else 'none'}."
        )
        if failure:
            message += "\n\n" + failure
        if stored_state == "failed":
            message += (
                "\n\nGUI next: исправьте core/profile compatibility и снова нажмите «Запустить tunnel core». "
                "Если в stderr есть 'unknown transport protocol: xhttp', выбранный core не поддерживает VLESS type=xhttp."
            )
        else:
            message += "\n\nGUI next: сначала нажмите «Запустить tunnel core», затем SOCKS probe."
        raise ValueError(message)
    socks_host = str(session.get("socksHost", DEFAULT_SOCKS_HOST))
    socks_port = int(session.get("socksPort", DEFAULT_SOCKS_PORT))
    socks_auth_mode = _session_socks_auth_mode(session)
    socks_credentials = _session_socks_credentials(paths, profile_id, session)
    if socks_auth_mode == SOCKS_AUTH_PASSWORD and socks_credentials is None:
        raise ValueError("SOCKS credentials для tunnel session не найдены. Перезапустите tunnel (plan → confirm → start).")
    if socks_auth_mode == SOCKS_AUTH_PASSWORD and launch_mode != "socks-env-only":
        raise ValueError(
            "Chromium/Electron (Discord/Vesktop) флаг --proxy-server не поддерживает SOCKS-аутентификацию, "
            "а tunnel запущен в безопасном режиме с паролем. Варианты: launch mode socks-env-only "
            "(proxy с логином/паролем передаётся через env), или явно пересоздать plan с "
            "--tunnel-socks-legacy-noauth (небезопасно: localhost ≠ private, любой локальный процесс сможет "
            "использовать SOCKS и узнать IP VPN-сервера)."
        )
    socks_probe = _wait_for_socks5_handshake(socks_host, socks_port, credentials=socks_credentials)
    if not bool(socks_probe.get("ok")):
        raise ValueError(
            "Tunnel core process найден, но SOCKS handshake не прошёл: "
            f"{socks_probe.get('message', 'unknown')}. Discord не будет запущен, чтобы не получить ERR_PROXY_CONNECTION_FAILED. "
            "Запустите --discord-tunnel-probe и проверьте core stdout/stderr."
        )
    preflight_result: dict[str, Any] | None = None
    preflight_report_path: Path | None = None
    preflight_evidence_path: Path | None = None
    preflight_route_support = SUPPORT_UNKNOWN
    if upstream_preflight:
        try:
            preflight_result = _https_head_through_socks(
                socks_host=socks_host,
                socks_port=socks_port,
                target_host=preflight_host,
                target_path=preflight_path,
                timeout=float(preflight_timeout),
                credentials=socks_credentials,
            )
        except Exception as exc:  # captured into report so the owner can attach it
            preflight_result = {
                "ok": False,
                "stage": "exception",
                "socksMethodOk": None,
                "socksConnectOk": None,
                "targetTlsOk": None,
                "targetHttpOk": None,
                "message": str(exc),
                "elapsedMs": None,
            }
        preflight_evidence_path, preflight_route_support = _record_https_probe_evidence(
            paths,
            profile_id,
            session,
            target_host=preflight_host,
            target_path=preflight_path,
            result=preflight_result,
            producer="discord-launch-preflight",
        )
        reports_dir = paths.tunnel_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        preflight_report_path = reports_dir / f"{profile_id}.launch-preflight-{stamp}.json"
        _write_json(
            preflight_report_path,
            {
                "schemaVersion": TUNNEL_SCHEMA_VERSION,
                "stage": TUNNEL_STAGE,
                "createdAt": _utc_now(),
                "profileId": profile_id,
                "targetHost": preflight_host,
                "targetPath": _hashed_presence(preflight_path),
                "socksHost": socks_host,
                "socksPort": socks_port,
                "runId": session.get("runId"),
                "connectionReceiptId": session.get("connectionReceiptId"),
                "configHash": session.get("configHash"),
                "result": preflight_result,
                "verdict": "T1_HTTPS_THROUGH_SOCKS_OK" if preflight_result.get("ok") else "T1_HTTPS_THROUGH_SOCKS_FAILED",
                "routeCapability": preflight_route_support,
                "evidenceGraph": str(preflight_evidence_path) if preflight_evidence_path else None,
            },
            secret=False,
        )
        if not bool(preflight_result.get("ok")) and not allow_failed_preflight:
            _append_event(
                paths,
                profile_id,
                "discord-launch-blocked-upstream-preflight",
                "Discord launch blocked because HTTPS-over-SOCKS preflight failed",
                {"targetHost": preflight_host, "stage": preflight_result.get("stage"), "report": str(preflight_report_path)},
            )
            raise ValueError(
                "Upstream preflight не прошёл, поэтому Discord не запущен. "
                f"target=https://{preflight_host}{preflight_path if preflight_path.startswith('/') else '/' + preflight_path}; "
                f"stage={preflight_result.get('stage', 'n/a')}; message={preflight_result.get('message', 'n/a')}. "
                f"report: {preflight_report_path}. routeCapability={preflight_route_support}. "
                "Это защищает от запуска Electron в заведомо сломанный VLESS route. "
                "Для ручного эксперимента можно повторить с --discord-launch-allow-failed-preflight."
            )

    env_proxy = socks_proxy_url(socks_host, socks_port, socks_credentials, redact=False) if socks_credentials else f"socks5://{socks_host}:{socks_port}"
    proxy = socks_proxy_url(socks_host, socks_port, socks_credentials) if socks_credentials else f"socks5://{socks_host}:{socks_port}"
    env = dict(os.environ)
    if launch_mode != "socks-flag-only":
        env.update({"ALL_PROXY": env_proxy, "HTTPS_PROXY": env_proxy, "HTTP_PROXY": env_proxy, "all_proxy": env_proxy, "https_proxy": env_proxy, "http_proxy": env_proxy})
    argv, raw_command = _discord_launch_argv(discord_binary, socks_host, socks_port, launch_mode)
    client_kind = _client_kind_from_command(argv, raw_command)
    flatpak = _is_flatpak_command(argv)
    stdout_path = _discord_stdout_path(paths, profile_id)
    stderr_path = _discord_stderr_path(paths, profile_id)
    stdout_handle = stdout_path.open("ab")
    stderr_handle = stderr_path.open("ab")
    try:
        process = subprocess.Popen(argv, cwd=str(paths.root), env=env, stdout=stdout_handle, stderr=stderr_handle, start_new_session=True)
    finally:
        stdout_handle.close()
        stderr_handle.close()
    time.sleep(0.3)
    discord_running = _pid_running(process.pid)
    discord_session = {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "profileId": profile_id,
        "runId": session.get("runId"),
        "connectionReceiptId": session.get("connectionReceiptId"),
        "configHash": session.get("configHash"),
        "evidenceGraph": str(preflight_evidence_path or session.get("evidenceGraphPath", "")),
        "launchMode": launch_mode,
        "discordCommand": raw_command,
        "clientKind": client_kind,
        "argv": list(argv),
        "pid": process.pid,
        "startedAt": _utc_now(),
        "proxy": proxy,
        "tunnelSession": str(session_path),
        "flatpakCommand": flatpak,
        "state": "running" if discord_running else "exited-after-launch",
        "stdoutLog": str(stdout_path),
        "stderrLog": str(stderr_path),
        "runningAfterGrace": discord_running,
        "upstreamPreflight": {
            "enabled": bool(upstream_preflight),
            "targetHost": preflight_host if upstream_preflight else "",
            "targetPath": _hashed_presence(preflight_path) if upstream_preflight else {"present": False},
            "ok": bool(preflight_result.get("ok")) if preflight_result else None,
            "stage": preflight_result.get("stage") if preflight_result else "",
            "report": str(preflight_report_path) if preflight_report_path else "",
            "allowFailed": bool(allow_failed_preflight),
            "routeCapability": preflight_route_support if upstream_preflight else SUPPORT_UNKNOWN,
            "bypassChangesVerdict": False,
        },
    }
    discord_session_path = _discord_session_path(paths, profile_id)
    _write_json(discord_session_path, discord_session, secret=False)
    _append_event(paths, profile_id, "discord-launched-through-socks", "Discord/Vesktop launched with SOCKS env/flag candidates", {"pid": process.pid, "clientKind": client_kind, "launchMode": launch_mode, "socks": proxy, "runningAfterGrace": discord_running, "upstreamPreflight": bool(upstream_preflight), "upstreamPreflightOk": bool(preflight_result.get("ok")) if preflight_result else None})
    return "\n".join(
        [
            "Discord launch through SOCKS: started",
            f"profile: {profile_id}",
            f"launch mode: {launch_mode}",
            f"discord/vesktop command: {raw_command}",
            f"client kind: {client_kind}",
            f"discord/vesktop pid: {process.pid}",
            f"discord running after grace: {'yes' if discord_running else 'no'}",
            f"argv: {shlex.join(argv)}",
            f"proxy env: {proxy}",
            f"socks auth: {socks_auth_mode}",
            *([LEGACY_NOAUTH_WARNING] if socks_auth_mode == SOCKS_AUTH_LEGACY_NOAUTH else []),
            f"flatpak command: {'yes' if flatpak else 'no'}",
            f"discord session: {discord_session_path}",
            f"discord stdout: {stdout_path}",
            f"discord stderr: {stderr_path}",
            f"upstream preflight: {'ok' if preflight_result and preflight_result.get('ok') else 'skipped' if not upstream_preflight else 'failed-but-allowed'}",
            f"preflight route capability: {preflight_route_support if upstream_preflight else SUPPORT_UNKNOWN}",
            f"preflight report: {preflight_report_path if preflight_report_path else 'нет'}",
            f"evidence graph: {preflight_evidence_path or session.get('evidenceGraphPath', 'нет')}",
            f"failed-preflight bypass changes capability verdict: no",
            "ROUTING NOTE:",
            "  The tunnel is not transparent. Discord must be launched/configured through SOCKS; already-open app/browser windows are not rerouted.",
            "MANUAL ACTION:",
            "  Watch Discord. If it reaches the main window, keep the tunnel running and record that result.",
            "  If it stays on Checking for updates, run --discord-tunnel-probe and attach .zap2/tunnel/runtime + reports.",
            "executes Discord now: yes",
            "mutates firewall/services: no",
        ]
    )


def discord_stop_launched_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> str:
    """Stop only the Discord process group launched by this tunnel adapter."""

    paths = ensure_tunnel_store(root)
    session_path = _discord_session_path(paths, profile_id)
    if not session_path.exists():
        return "\n".join([
            "Discord launched-through-SOCKS stop: not-started",
            f"profile: {profile_id}",
            f"discord session: {session_path}",
            "stops now: no",
        ])
    session = _read_json(session_path)
    pid = int(session.get("pid", 0) or 0)
    argv = [str(item) for item in session.get("argv", [])]
    cmdline = _read_cmdline(pid) if pid else ""
    running = _pid_running(pid)
    if not pid or not running:
        session["state"] = "stale"
        session["stoppedAt"] = _utc_now()
        _write_json(session_path, session, secret=False)
        return "\n".join([
            "Discord launched-through-SOCKS stop: stale",
            f"profile: {profile_id}",
            f"pid: {pid if pid else 'нет'}",
            f"proc state: {_proc_state(pid) if pid else 'none'}",
            f"discord session: {session_path}",
        ])
    first = Path(argv[0]).name if argv else ""
    if cmdline and first and first not in cmdline and "flatpak" not in cmdline and "Discord" not in cmdline and "discord" not in cmdline.lower():
        raise ValueError("Recorded Discord PID command line no longer looks like the managed Discord launcher; refusing to kill it.")
    try:
        os.killpg(pid, signal.SIGTERM)
        kill_scope = "process-group"
    except ProcessLookupError:
        kill_scope = "already-gone"
    except OSError:
        os.kill(pid, signal.SIGTERM)
        kill_scope = "pid"
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if not _pid_running(pid):
            break
        time.sleep(0.1)
    if _pid_running(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
            kill_scope = f"{kill_scope}+sigkill-group"
        except OSError:
            os.kill(pid, signal.SIGKILL)
            kill_scope = f"{kill_scope}+sigkill-pid"
    session["state"] = "stopped"
    session["stoppedAt"] = _utc_now()
    session["killScope"] = kill_scope
    _write_json(session_path, session, secret=False)
    log_path = _append_event(paths, profile_id, "discord-launched-stop", "Managed launched Discord process stopped", {"pid": pid, "killScope": kill_scope})
    return "\n".join([
        "Discord launched-through-SOCKS stop: stopped",
        f"profile: {profile_id}",
        f"pid: {pid}",
        f"kill scope: {kill_scope}",
        f"discord session: {session_path}",
        f"tunnel log: {log_path}",
        "kills only recorded launched Discord process: yes",
        "mutates firewall/services: no",
    ])


# ---- Stage 7p5: guided SOCKS/VLESS experiment helpers ----

DEFAULT_TUNNEL_HTTPS_HOST = "updates.discord.com"
DEFAULT_TUNNEL_HTTPS_PATH = "/"
DEFAULT_TUNNEL_OBSERVE_SECONDS = 45
SUPPORTED_UPDATER_RESULTS = ("passed", "stuck", "unknown")


def _read_exact(sock: socket.socket, count: int) -> bytes:
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise OSError("SOCKS peer closed connection")
        data += chunk
    return data


def _socks5_connect(sock: socket.socket, host: str, port: int, credentials: tuple[str, str] | None = None) -> dict[str, Any]:
    host_bytes = host.encode("idna")
    if len(host_bytes) > 255:
        raise ValueError("SOCKS target host is too long")
    negotiation = _socks5_negotiate(sock, credentials)
    if not negotiation.get("ok"):
        return {
            "ok": False,
            "methodOk": False,
            "connectOk": False,
            "stage": "socks-auth",
            "replyHex": negotiation.get("responseHex", ""),
            "insecureNoAuth": bool(negotiation.get("insecureNoAuth")),
            "message": str(negotiation.get("message", "SOCKS5 auth was not accepted")),
        }
    request = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + int(port).to_bytes(2, "big")
    sock.sendall(request)
    header = _read_exact(sock, 4)
    if len(header) != 4 or header[0] != 5:
        return {
            "ok": False,
            "methodOk": True,
            "connectOk": False,
            "stage": "socks-connect",
            "replyHex": header.hex(),
            "message": "SOCKS5 connect returned malformed header",
        }
    atyp = header[3]
    if atyp == 1:
        _read_exact(sock, 4)
    elif atyp == 3:
        size = _read_exact(sock, 1)[0]
        _read_exact(sock, size)
    elif atyp == 4:
        _read_exact(sock, 16)
    else:
        return {
            "ok": False,
            "methodOk": True,
            "connectOk": False,
            "stage": "socks-connect",
            "replyHex": header.hex(),
            "message": f"SOCKS5 connect returned unsupported ATYP {atyp}",
        }
    _read_exact(sock, 2)
    rep = header[1]
    if rep != 0:
        return {
            "ok": False,
            "methodOk": True,
            "connectOk": False,
            "stage": "socks-connect",
            "replyCode": rep,
            "message": f"SOCKS5 connect failed with REP={rep}",
        }
    return {
        "ok": True,
        "methodOk": True,
        "connectOk": True,
        "stage": "socks-connect",
        "message": "SOCKS5 connect established",
    }


def _https_head_through_socks(*, socks_host: str, socks_port: int, target_host: str, target_path: str, timeout: float, credentials: tuple[str, str] | None = None) -> dict[str, Any]:
    """Probe SOCKS method/connect, TLS and HTTP as distinct evidence stages."""

    started = time.monotonic()
    target_path = target_path if target_path.startswith("/") else f"/{target_path}"
    try:
        raw_sock = socket.create_connection((socks_host, int(socks_port)), timeout=timeout)
    except OSError as exc:
        return {
            "ok": False,
            "stage": "socks-listener",
            "socksMethodOk": False,
            "socksConnectOk": False,
            "targetTlsOk": None,
            "targetHttpOk": None,
            "message": str(exc),
            "elapsedMs": int((time.monotonic() - started) * 1000),
        }
    with raw_sock:
        raw_sock.settimeout(timeout)
        try:
            socks_result = _socks5_connect(raw_sock, target_host, 443, credentials)
        except (OSError, ValueError) as exc:
            return {
                "ok": False,
                "stage": "socks-connect",
                "socksMethodOk": None,
                "socksConnectOk": False,
                "targetTlsOk": None,
                "targetHttpOk": None,
                "message": str(exc),
                "elapsedMs": int((time.monotonic() - started) * 1000),
            }
        method_ok = bool(socks_result.get("methodOk"))
        connect_ok = bool(socks_result.get("connectOk"))
        if not socks_result.get("ok"):
            return {
                **socks_result,
                "socksMethodOk": method_ok,
                "socksConnectOk": connect_ok,
                "targetTlsOk": None,
                "targetHttpOk": None,
                "elapsedMs": int((time.monotonic() - started) * 1000),
            }
        context = ssl.create_default_context()
        try:
            tls_sock = context.wrap_socket(raw_sock, server_hostname=target_host)
        except (ssl.SSLError, OSError, socket.timeout) as exc:
            return {
                "ok": False,
                "stage": "target-tls",
                "socksMethodOk": True,
                "socksConnectOk": True,
                "targetTlsOk": False,
                "targetHttpOk": None,
                "message": str(exc),
                "elapsedMs": int((time.monotonic() - started) * 1000),
            }
        with tls_sock:
            tls_sock.settimeout(timeout)
            request = (
                f"HEAD {target_path} HTTP/1.1\r\n"
                f"Host: {target_host}\r\n"
                "User-Agent: Zap2GUIfLin-tunnel-probe/1\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            try:
                tls_sock.sendall(request)
                response = tls_sock.recv(768)
            except (ssl.SSLError, OSError, socket.timeout) as exc:
                return {
                    "ok": False,
                    "stage": "target-http",
                    "socksMethodOk": True,
                    "socksConnectOk": True,
                    "targetTlsOk": True,
                    "targetHttpOk": False,
                    "message": str(exc),
                    "elapsedMs": int((time.monotonic() - started) * 1000),
                }
    first_line = response.splitlines()[0].decode("iso-8859-1", errors="replace") if response else ""
    status_code = None
    if first_line.startswith("HTTP/"):
        parts = first_line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            status_code = int(parts[1])
    ok = status_code is not None and 100 <= status_code < 600
    return {
        "ok": ok,
        "stage": "target-http",
        "socksMethodOk": True,
        "socksConnectOk": True,
        "targetTlsOk": True,
        "targetHttpOk": ok,
        "statusLine": first_line,
        "statusCode": status_code,
        "elapsedMs": int((time.monotonic() - started) * 1000),
        "message": "HTTPS HEAD through SOCKS completed" if ok else "HTTPS HEAD through SOCKS did not return an HTTP status line",
    }


def _probe_state(value: Any, *, failed_if_false: bool = True) -> str:
    if value is True:
        return PASS
    if value is False and failed_if_false:
        return FAIL
    return UNKNOWN


def _record_https_probe_evidence(
    paths: TunnelStorePaths,
    profile_id: str,
    session: dict[str, Any],
    *,
    target_host: str,
    target_path: str,
    result: dict[str, Any],
    producer: str,
) -> tuple[Path | None, str]:
    run_id = str(session.get("runId", ""))
    if not run_id:
        return None, SUPPORT_UNKNOWN
    try:
        graph = _load_bound_evidence_graph(paths, profile_id, session)
    except ValueError:
        return None, SUPPORT_UNKNOWN
    local_method = next((item for item in reversed(graph.spans) if item.kind == "socks_method" and item.run_id == run_id), None)
    method_result = _probe_state(result.get("socksMethodOk"))
    connect_result = _probe_state(result.get("socksConnectOk"))
    tls_result = _probe_state(result.get("targetTlsOk"))
    http_result = _probe_state(result.get("targetHttpOk"))
    method_span = _probe_span(
        run_id=run_id,
        kind="socks_method",
        result=method_result,
        target=target_host,
        deps=(local_method.span_id,) if local_method else (),
        detail={"producer": producer, "message": result.get("message", "")},
        limits=("target-bound method observation does not prove remote TLS/HTTP",),
    )
    graph.add_span(method_span)
    connect_span = _probe_span(
        run_id=run_id,
        kind="socks_connect",
        result=connect_result,
        target=target_host,
        deps=(method_span.span_id,),
        detail={"port": 443, "producer": producer, "stage": result.get("stage", "")},
        limits=("SOCKS CONNECT acceptance proves only proxy-side acceptance of the target request",),
    )
    graph.add_span(connect_span)
    tls_span = _probe_span(
        run_id=run_id,
        kind="target_tls",
        result=tls_result,
        target=target_host,
        deps=(connect_span.span_id,),
        detail={"producer": producer, "stage": result.get("stage", ""), "message": result.get("message", "")},
    )
    graph.add_span(tls_span)
    http_span = _probe_span(
        run_id=run_id,
        kind="target_http",
        result=http_result,
        target=target_host,
        deps=(tls_span.span_id,),
        detail={
            "producer": producer,
            "path": _hashed_presence(target_path),
            "statusCode": result.get("statusCode"),
            "statusLine": result.get("statusLine", ""),
            "message": result.get("message", ""),
        },
    )
    graph.add_span(http_span)
    # Every explicitly probed target receives its own route verdict, including
    # neutral/control hosts. Mandatory Vesktop endpoints are refreshed as a
    # separate aggregate and never inherit success from the control target.
    route = _route_capability(graph, target_host)
    graph.add_verdict(route)
    _refresh_capability_verdicts(graph)
    path = _write_evidence_graph(paths, graph)
    return path, route.support

def _load_running_tunnel_session(paths: TunnelStorePaths, profile_id: str) -> dict[str, Any]:
    session_path = _session_path(paths, profile_id)
    if not session_path.exists():
        raise ValueError("Tunnel session не найден. Сначала запустите --discord-tunnel-start или --discord-tunnel-guided-run.")
    session = _read_json(session_path)
    pid = int(session.get("pid", 0) or 0)
    if not _pid_running(pid):
        raise ValueError("Tunnel core не running; сначала проверьте --discord-tunnel-status или перезапустите tunnel guided run.")
    return session


def discord_tunnel_https_probe_to_text(
    *,
    profile_id: str = DEFAULT_PROFILE_ID,
    target_host: str = DEFAULT_TUNNEL_HTTPS_HOST,
    target_path: str = DEFAULT_TUNNEL_HTTPS_PATH,
    timeout_seconds: float = 8.0,
    root: Path | None = None,
) -> str:
    """Run a harmless HTTPS HEAD through the managed local SOCKS listener."""

    if timeout_seconds <= 0 or timeout_seconds > 60:
        raise ValueError("--tunnel-probe-timeout должен быть в диапазоне 1..60 секунд")
    paths = ensure_tunnel_store(root)
    session = _load_running_tunnel_session(paths, profile_id)
    socks_host = str(session.get("socksHost", DEFAULT_SOCKS_HOST))
    socks_port = int(session.get("socksPort", DEFAULT_SOCKS_PORT))
    socks_credentials = _session_socks_credentials(paths, profile_id, session)
    report_base = {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "createdAt": _utc_now(),
        "profileId": profile_id,
        "targetHost": target_host,
        "targetPath": _hashed_presence(target_path),
        "socksHost": socks_host,
        "socksPort": socks_port,
        "tunnelPid": int(session.get("pid", 0) or 0),
    }
    try:
        result = _https_head_through_socks(
            socks_host=socks_host,
            socks_port=socks_port,
            target_host=target_host,
            target_path=target_path,
            timeout=float(timeout_seconds),
            credentials=socks_credentials,
        )
    except Exception as exc:  # deliberately captured into report for owner diagnosis
        result = {"ok": False, "stage": "exception", "message": str(exc), "elapsedMs": None}
    verdict = "T1_HTTPS_THROUGH_SOCKS_OK" if result.get("ok") else "T1_HTTPS_THROUGH_SOCKS_FAILED"
    evidence_path, route_support = _record_https_probe_evidence(
        paths,
        profile_id,
        session,
        target_host=target_host,
        target_path=target_path,
        result=result,
        producer="discord-tunnel-https-probe",
    )
    report = {
        **report_base,
        "runId": session.get("runId"),
        "connectionReceiptId": session.get("connectionReceiptId"),
        "configHash": session.get("configHash"),
        "result": result,
        "verdict": verdict,
        "routeCapability": route_support,
        "evidenceGraph": str(evidence_path) if evidence_path else None,
    }
    reports_dir = paths.tunnel_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = reports_dir / f"{profile_id}.https-probe-{stamp}.json"
    _write_json(report_path, report, secret=False)
    _append_event(paths, profile_id, "tunnel-https-probed", "HTTPS-over-SOCKS tunnel probe completed", {"verdict": verdict, "targetHost": target_host, "stage": result.get("stage")})
    return "\n".join(
        [
            "Discord tunnel HTTPS probe",
            f"stage: {TUNNEL_STAGE}",
            f"profile: {profile_id}",
            f"target: https://{target_host}{target_path if target_path.startswith('/') else '/' + target_path}",
            f"local socks: socks5://{socks_host}:{socks_port}",
            f"verdict: {verdict}",
            f"route capability: {route_support}",
            f"run id: {session.get('runId', 'legacy-unbound')}",
            f"evidence graph: {evidence_path if evidence_path else 'legacy/unbound'}",
            f"probe stage: {result.get('stage', 'n/a')}",
            f"message: {result.get('message', 'n/a')}",
            f"status line: {result.get('statusLine', 'n/a')}",
            f"elapsed ms: {result.get('elapsedMs', 'n/a')}",
            f"report: {report_path}",
            "executes Discord now: no",
            "mutates firewall/services: no",
        ]
    )



def _read_log_tail(path: Path, *, max_bytes: int = 262144) -> str:
    try:
        if not path.exists() or not path.is_file():
            return ""
        with path.open("rb") as handle:
            if path.stat().st_size > max_bytes:
                handle.seek(-max_bytes, os.SEEK_END)
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _last_matching_line(text: str, patterns: tuple[str, ...]) -> str:
    lowered = tuple(item.lower() for item in patterns)
    for line in reversed(text.splitlines()):
        sample = line.lower()
        if any(pattern in sample for pattern in lowered):
            return line.strip()
    return ""


def _count_contains(text: str, needle: str) -> int:
    return text.lower().count(needle.lower())


def _latest_report_path(paths: TunnelStorePaths, profile_id: str, suffix_glob: str) -> Path | None:
    reports_dir = paths.tunnel_root / "reports"
    if not reports_dir.exists():
        return None
    matches = sorted(reports_dir.glob(f"{profile_id}.{suffix_glob}"), key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _report_verdict(path: Path | None) -> str:
    if path is None:
        return "нет"
    try:
        data = _read_json(path)
        verdict = str(data.get("verdict", "unknown"))
        result = data.get("result", {}) if isinstance(data.get("result"), dict) else {}
        stage = str(result.get("stage", ""))
        message = str(result.get("message", ""))
        tail = f"; stage={stage}; message={message}" if stage or message else ""
        return f"{verdict}{tail}; report={path}"
    except Exception:
        return f"unreadable; report={path}"


def discord_tunnel_route_diagnose_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> str:
    """Summarize local SOCKS, upstream probe, managed Discord launch, and log symptoms."""

    paths = ensure_tunnel_store(root)
    session_path = _session_path(paths, profile_id)
    discord_session_path = _discord_session_path(paths, profile_id)
    socks_host = DEFAULT_SOCKS_HOST
    socks_port = DEFAULT_SOCKS_PORT
    tunnel_state = "not-started"
    tunnel_pid = 0
    socks_probe: dict[str, Any] = {"ok": False, "message": "no tunnel session"}
    session: dict[str, Any] = {}
    if session_path.exists():
        session = _read_json(session_path)
        tunnel_pid = int(session.get("pid", 0) or 0)
        stored = str(session.get("state", "running" if tunnel_pid else "not-started"))
        socks_host = str(session.get("socksHost", DEFAULT_SOCKS_HOST))
        socks_port = int(session.get("socksPort", DEFAULT_SOCKS_PORT))
        tunnel_state = "running" if stored == "running" and _pid_running(tunnel_pid) else stored if stored in {"stopped", "failed"} else "stale"
        diag_credentials = _session_socks_credentials(paths, profile_id, session)
        socks_probe = _socks5_handshake_probe(socks_host, socks_port, credentials=diag_credentials) if diag_credentials else _socks5_handshake_probe(socks_host, socks_port)

    discord_state = "not-started"
    discord_pid = 0
    discord_command = ""
    if discord_session_path.exists():
        discord_session = _read_json(discord_session_path)
        discord_pid = int(discord_session.get("pid", 0) or 0)
        stored_discord = str(discord_session.get("state", "running" if discord_pid else "not-started"))
        discord_state = "running" if stored_discord == "running" and _pid_running(discord_pid) else stored_discord if stored_discord in {"stopped", "failed", "exited-after-launch", "stale"} else "stale"
        discord_command = str(discord_session.get("discordCommand", ""))

    core_stdout = _read_log_tail(_stdout_path(paths, profile_id))
    core_stderr = _read_log_tail(_stderr_path(paths, profile_id))
    discord_stdout = _read_log_tail(_discord_stdout_path(paths, profile_id))
    discord_stderr = _read_log_tail(_discord_stderr_path(paths, profile_id))
    discord_logs = f"{discord_stdout}\n{discord_stderr}"
    core_logs = f"{core_stdout}\n{core_stderr}"

    accepted_discord = _count_contains(core_logs, "accepted tcp:discordapp.com:443") + _count_contains(core_logs, "accepted tcp:discord.com:443")
    accepted_gateway = _count_contains(core_logs, "accepted tcp:gateway.discord.gg:443")
    accepted_telegram = _count_contains(core_logs, "accepted tcp:149.154.") + _count_contains(core_logs, "accepted tcp:91.108.")
    socks_eof = _count_contains(core_logs, "proxy/socks: insufficient header")
    err_proxy_failed = _count_contains(discord_logs, "ERR_PROXY_CONNECTION_FAILED")
    err_closed = _count_contains(discord_logs, "ERR_CONNECTION_CLOSED")
    err_timed_out = _count_contains(discord_logs, "ERR_TIMED_OUT")
    ssl_net_error_100 = _count_contains(discord_logs, "net_error -100")
    retry_lines = _count_contains(discord_logs, "retrying load https://discordapp.com/app")
    last_error = _last_matching_line(discord_logs, ("ERR_PROXY_CONNECTION_FAILED", "ERR_CONNECTION_CLOSED", "ERR_TIMED_OUT", "net_error -100", "did-fail-load"))

    latest_https = _latest_report_path(paths, profile_id, "https-probe-*.json")
    latest_preflight = _latest_report_path(paths, profile_id, "launch-preflight-*.json")

    typed_graph: EvidenceGraph | None = None
    typed_graph_path = ""
    typed_run_id = str(session.get("runId", "")) if session else ""
    if typed_run_id:
        try:
            typed_graph = _load_bound_evidence_graph(paths, profile_id, session)
            _refresh_capability_verdicts(typed_graph)
            typed_graph_path = str(_write_evidence_graph(paths, typed_graph))
        except (ValueError, OSError, TypeError):
            typed_graph = None

    if not session_path.exists():
        verdict = "TD_NO_TUNNEL_SESSION"
        meaning = "tunnel core ещё не запускался"
        next_step = "импортируй/выбери VLESS, затем tunnel plan -> confirm -> start"
    elif (tunnel_state != "running" or not bool(socks_probe.get("ok"))) and (err_closed or ssl_net_error_100) and accepted_discord:
        verdict = "TD_LAST_RUN_ROUTED_BUT_UPSTREAM_TLS_CLOSED"
        meaning = "сейчас SOCKS уже не готов, но в последнем запуске Discord был направлен через tunnel и TLS/HTTPS закрывался"
        next_step = "перезапусти tunnel и сначала выполни HTTPS/preflight probe; если он failed, меняй VLESS профиль или параметры upstream"
    elif (tunnel_state != "running" or not bool(socks_probe.get("ok"))) and err_proxy_failed:
        verdict = "TD_LAST_RUN_PROXY_WAS_UNAVAILABLE"
        meaning = "сейчас SOCKS не готов, а последний Discord launch падал на недоступном proxy"
        next_step = "перезапусти tunnel, дождись SOCKS probe ok и запускай только с upstream preflight"
    elif tunnel_state != "running" or not bool(socks_probe.get("ok")):
        verdict = "TD_SOCKS_NOT_READY"
        meaning = "локальный SOCKS сейчас не готов"
        next_step = "перезапусти tunnel и проверь --discord-tunnel-probe"
    elif not discord_session_path.exists():
        verdict = "TD_TUNNEL_READY_APP_NOT_LAUNCHED"
        meaning = "SOCKS жив, но managed Discord launch ещё не запускался"
        next_step = "сначала выполни HTTPS/preflight probe, потом launch через SOCKS"
    elif err_proxy_failed:
        verdict = "TD_APP_USED_PROXY_BUT_SOCKS_FAILED"
        meaning = "Discord получил proxy flag, но proxy был недоступен в момент загрузки"
        next_step = "останови managed Discord, перезапусти tunnel, затем запускай с upstream preflight"
    elif (err_closed or ssl_net_error_100) and accepted_discord:
        verdict = "TD_APP_ROUTED_BUT_UPSTREAM_TLS_CLOSED"
        meaning = "Discord был направлен через SOCKS, core видел discordapp.com:443, но TLS/HTTPS соединение закрывалось"
        next_step = "проверь VLESS профиль через HTTPS probe на несколько host; вероятнее всего проблема в upstream-профиле или его маршруте"
    elif accepted_discord or accepted_gateway:
        verdict = "TD_APP_ROUTED_OBSERVE_RESULT"
        meaning = "Discord-трафик виден в tunnel core; нужен owner-result по окну Discord"
        next_step = "если окно не открылось, запусти route diagnose после свежего HTTPS probe"
    elif discord_session_path.exists():
        verdict = "TD_APP_LAUNCHED_NO_DISCORD_PROXY_TRAFFIC"
        meaning = "managed launch был, но в core-логе нет Discord destination"
        next_step = "проверь launch mode и Flatpak/Electron proxy flags"
    else:
        verdict = "TD_UNKNOWN"
        meaning = "данных недостаточно"
        next_step = "приложи .zap2/tunnel/runtime, logs и reports"

    lines = [
        "Discord tunnel route diagnosis",
        f"stage: {TUNNEL_STAGE}",
        f"profile: {profile_id}",
        f"verdict: {verdict}",
        f"meaning: {meaning}",
        "",
        "State:",
        f"  tunnel: {tunnel_state}; pid={tunnel_pid if tunnel_pid else 'нет'}; proc={_proc_state(tunnel_pid) if tunnel_pid else 'none'}",
        f"  socks: socks5://{socks_host}:{socks_port}; handshake={'ok' if socks_probe.get('ok') else 'no'}; message={socks_probe.get('message', 'n/a')}",
        f"  Discord launch: {discord_state}; pid={discord_pid if discord_pid else 'нет'}; command={discord_command or 'нет'}",
        "",
        "Evidence from recent logs:",
        f"  core accepted Discord destinations: {accepted_discord + accepted_gateway}",
        f"  core accepted Telegram-like destinations: {accepted_telegram}",
        f"  harmless SOCKS EOF probe noise: {socks_eof}",
        f"  Discord ERR_PROXY_CONNECTION_FAILED: {err_proxy_failed}",
        f"  Discord ERR_CONNECTION_CLOSED / net_error -100: {err_closed + ssl_net_error_100}",
        f"  Discord ERR_TIMED_OUT: {err_timed_out}",
        f"  Discord retry lines: {retry_lines}",
        f"  last error line: {last_error or 'нет'}",
        "",
        "Latest upstream probes:",
        f"  HTTPS probe: {_report_verdict(latest_https)}",
        f"  launch preflight: {_report_verdict(latest_preflight)}",
        "",
        "Typed evidence (authoritative for capability; log heuristics above are diagnostic only):",
    ]
    if typed_graph is not None:
        lines.extend([f"  evidence graph: {typed_graph_path}", *[f"  {item}" for item in _graph_summary_lines(typed_graph)]])
    else:
        lines.append("  unavailable/legacy-unbound: capability remains UNKNOWN; no log symptom may promote it")
    lines.extend([
        "",
        "Invariant: bypass/force-launch or historical log traffic cannot turn a failed/unknown CapabilityVerdict green.",
        f"Next: {next_step}",
        "read-only: yes",
        "executes Discord now: no",
        "mutates firewall/services: no",
    ])
    return "\n".join(lines)


def _updater_verdict_from_result(owner_result: str, https_verdict: str, discord_pid: int) -> str:
    normalized = (owner_result or "unknown").strip().lower()
    if normalized == "passed":
        return "TU_UPDATER_PASSED_OWNER_OBSERVED"
    if normalized == "stuck":
        return "TU_UPDATER_STUCK_OWNER_OBSERVED"
    if https_verdict == "T1_HTTPS_THROUGH_SOCKS_OK" and discord_pid > 0:
        return "TU_DISCORD_LAUNCHED_TUNNEL_READY_OWNER_OBSERVATION_NEEDED"
    return "TU_TUNNEL_NOT_READY_OR_DISCORD_NOT_CONFIRMED"


def _prompt_updater_result(*, emit: Any | None = None) -> str:
    message = (
        "MANUAL OBSERVATION — type one word and press Enter:\n"
        "  passed  — Discord reached the main window / updater passed\n"
        "  stuck   — Discord is still on Checking for updates\n"
        "  unknown — you cannot tell yet\n"
        "Updater result [passed/stuck/unknown]: "
    )
    if emit is not None:
        emit(message.rstrip())
    try:
        answer = input("Updater result [passed/stuck/unknown]: ").strip().lower()
    except EOFError:
        return "unknown"
    return answer if answer in SUPPORTED_UPDATER_RESULTS else "unknown"


def discord_tunnel_guided_run_to_text(
    *,
    profile_id: str = DEFAULT_PROFILE_ID,
    core_binary: str | None = None,
    core_kind: str = DEFAULT_CORE_KIND,
    socks_port: int = DEFAULT_SOCKS_PORT,
    discord_binary: str = "discord",
    launch_mode: str = "socks-updater-window",
    observe_seconds: int = DEFAULT_TUNNEL_OBSERVE_SECONDS,
    updater_result: str = "unknown",
    interactive: bool = True,
    root: Path | None = None,
    emit: Any | None = None,
    socks_auth_mode: str = SOCKS_AUTH_PASSWORD,
) -> str:
    """One-command owner-phase for the Discord tunnel experiment.

    This intentionally stays user-space only: no sudo, no nftables, no service mutation.
    The command is explicit enough to auto-prepare and auto-confirm the local tunnel
    start plan, then keep the tunnel running for the owner-observed Discord session.
    """

    if observe_seconds < 0 or observe_seconds > 600:
        raise ValueError("--tunnel-observe-seconds должен быть 0..600")
    if updater_result and updater_result not in SUPPORTED_UPDATER_RESULTS:
        raise ValueError("--discord-updater-result должен быть: passed, stuck или unknown")
    paths = ensure_tunnel_store(root)
    plan_text = discord_tunnel_plan_to_text(
        profile_id=profile_id,
        core_binary=core_binary,
        core_kind=core_kind,
        socks_port=socks_port,
        root=paths.root,
        socks_auth_mode=socks_auth_mode,
    )
    plan_id = _tunnel_plan_id(profile_id)
    confirmation = confirm_runtime_plan(root=paths.root, plan_id=plan_id)
    start_text = discord_tunnel_start_to_text(profile_id=profile_id, confirm_plan_id=plan_id, root=paths.root)
    core_probe_text = discord_tunnel_probe_to_text(profile_id=profile_id, root=paths.root)
    try:
        https_text = discord_tunnel_https_probe_to_text(profile_id=profile_id, root=paths.root)
    except ValueError as exc:
        https_text = "\n".join(
            [
                "Discord tunnel HTTPS probe: blocked",
                f"reason: {exc}",
                "verdict: T1_HTTPS_THROUGH_SOCKS_FAILED",
            ]
        )
    try:
        launch_text = discord_launch_through_socks_to_text(profile_id=profile_id, discord_binary=discord_binary, launch_mode=launch_mode, root=paths.root)
    except ValueError as exc:
        launch_text = "\n".join(
            [
                "Discord launch through SOCKS: blocked",
                f"reason: {exc}",
                "executes Discord now: no",
                "next: fix tunnel/core readiness before launching Discord through SOCKS",
            ]
        )

    discord_session = _read_json(_discord_session_path(paths, profile_id)) if _discord_session_path(paths, profile_id).exists() else {}
    discord_pid = int(discord_session.get("pid", 0) or 0)
    if observe_seconds and interactive:
        if emit is not None:
            emit(f"Observation window: keep Discord open for {observe_seconds} seconds before verdict prompt...")
        time.sleep(observe_seconds)
    observed_result = updater_result
    if interactive and updater_result == "unknown":
        observed_result = _prompt_updater_result(emit=emit)
    https_verdict = "T1_HTTPS_THROUGH_SOCKS_OK" if "verdict: T1_HTTPS_THROUGH_SOCKS_OK" in https_text else "T1_HTTPS_THROUGH_SOCKS_FAILED"
    evidence_path: Path | None = None
    app_support = SUPPORT_UNKNOWN
    run_id = str(discord_session.get("runId", ""))
    client_kind = str(discord_session.get("clientKind", ""))
    if run_id and client_kind == "vesktop" and observed_result in {"passed", "stuck"}:
        try:
            tunnel_session = _read_json(_session_path(paths, profile_id))
            graph = _load_bound_evidence_graph(paths, profile_id, tunnel_session)
            navigation_span = _probe_span(
                run_id=run_id,
                kind="electron_navigation",
                result=PASS if observed_result == "passed" else FAIL,
                target=VESKTOP_MAIN_WINDOW_TARGET,
                detail={
                    "source": "owner-observation",
                    "ownerUpdaterResult": observed_result,
                    "discordPid": discord_pid,
                    "clientKind": client_kind,
                },
                limits=("owner observation proves this run/client window only; it does not prove Gateway/media capability",),
            )
            graph.add_span(navigation_span)
            _refresh_capability_verdicts(graph, client_kind=client_kind)
            evidence_path = _write_evidence_graph(paths, graph)
            app = next((item for item in graph.verdicts if item.capability_id == "vesktop.bootstrap"), None)
            app_support = app.support if app else SUPPORT_UNKNOWN
        except ValueError:
            pass
    verdict = _updater_verdict_from_result(observed_result, https_verdict, discord_pid)
    report = {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "createdAt": _utc_now(),
        "profileId": profile_id,
        "planId": plan_id,
        "planHash": confirmation.plan_hash,
        "launchMode": launch_mode,
        "discordBinary": discord_binary,
        "discordPid": discord_pid,
        "observeSeconds": observe_seconds,
        "ownerUpdaterResult": observed_result,
        "httpsProbeVerdict": https_verdict,
        "runId": run_id or None,
        "vesktopCapability": app_support,
        "evidenceGraph": str(evidence_path or discord_session.get("evidenceGraph", "")) or None,
        "verdict": verdict,
    }
    reports_dir = paths.tunnel_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = reports_dir / f"{profile_id}.guided-run-{stamp}.json"
    _write_json(report_path, report, secret=False)
    _append_event(paths, profile_id, "tunnel-guided-run", "Discord tunnel guided run completed", {"verdict": verdict, "discordPid": discord_pid, "ownerUpdaterResult": observed_result})
    return "\n".join(
        [
            "Discord tunnel guided run result",
            f"stage: {TUNNEL_STAGE}",
            f"profile: {profile_id}",
            f"launch mode: {launch_mode}",
            f"plan auto-confirmed: {plan_id}",
            f"tunnel core local state: {'started/SOCKS-local' if 'Discord tunnel start: started' in start_text or 'already-running' in start_text else 'check start output'}",
            f"https probe verdict: {https_verdict}",
            f"discord pid: {discord_pid if discord_pid else 'нет'}",
            f"owner updater result: {observed_result}",
            f"legacy guided verdict: {verdict}",
            f"vesktop bootstrap capability: {app_support}",
            f"evidence run: {run_id or 'legacy/unbound'}",
            f"evidence graph: {evidence_path or discord_session.get('evidenceGraph', 'legacy/unbound')}",
            f"report: {report_path}",
            "",
            "SUMMARY OF SUB-STEPS:",
            _indent_block(plan_text, "  plan> "),
            _indent_block(start_text, "  start> "),
            _indent_block(core_probe_text, "  core-probe> "),
            _indent_block(https_text, "  https-probe> "),
            _indent_block(launch_text, "  launch> "),
            "",
            "NEXT:",
            "  If Discord reached the main window, keep the tunnel running for this Discord process.",
            "  When finished: PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-stop",
            "  If stuck: attach .zap2/tunnel/runtime + .zap2/tunnel/reports.",
            "mutates firewall/services: no",
            "requires sudo: no",
        ]
    )


def _indent_block(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def discord_tunnel_tun_plan_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> str:
    paths = ensure_tunnel_store(root)
    report = {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "createdAt": _utc_now(),
        "profileId": profile_id,
        "mode": "tun-tproxy-research-plan-only",
        "executesNow": False,
        "requiresSudoForFutureImplementation": True,
    }
    reports_dir = paths.tunnel_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{profile_id}.tun-tproxy-plan.json"
    _write_json(report_path, report, secret=False)
    return "\n".join(
        [
            "Discord tunnel TUN/TProxy research plan",
            f"stage: {TUNNEL_STAGE}",
            f"profile: {profile_id}",
            "status: plan-only",
            "why not implemented as a blind switch:",
            "  SOCKS must prove whether Discord respects proxy flags/env first.",
            "  TUN/TProxy needs root, DNS/routing policy, nft rollback, leak checks and conflict checks with zapret NFQUEUE.",
            "future implementation gates:",
            "  1. keep SOCKS/VLESS core as backend;",
            "  2. add explicit DNS policy for Discord domains;",
            "  3. add owner-confirmed nft routing plan;",
            "  4. add rollback + kill-switch;",
            "  5. prove no conflict with Default zapret workflow.",
            f"report: {report_path}",
            "executes now: no",
            "applies firewall/services now: no",
        ]
    )
