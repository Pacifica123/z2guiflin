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

TUNNEL_STAGE = "v0.4-alpha_stage7p5"
TUNNEL_SCHEMA_VERSION = 1
TUNNEL_MARKER = "zap2-discord-tunnel-v1"
DEFAULT_PROFILE_ID = "default"
DEFAULT_SOCKS_HOST = "127.0.0.1"
DEFAULT_SOCKS_PORT = 10808
DEFAULT_CORE_KIND = "auto"
SUPPORTED_CORE_KINDS = ("auto", "xray", "v2ray", "sing-box")
SUPPORTED_LAUNCH_MODES = ("socks-updater-window", "socks-full-session", "socks-env-only", "socks-flag-only")
DEFAULT_DISCORD_COMMAND = "discord"
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
    kind = (core_kind or "auto").lower()
    if network in XHTTP_LIKE_TRANSPORTS and kind == "v2ray":
        return (
            f"transport {network} обычно не поддерживается V2Ray core. "
            "В этом workspace уже типичный симптом: core stderr может содержать "
            "'unknown transport protocol'. Используйте Xray/sing-box с поддержкой этого transport "
            "или импортируйте VLESS profile с type=tcp/ws/grpc."
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
    )


def ensure_tunnel_store(root: Path | None = None) -> TunnelStorePaths:
    paths = tunnel_store_paths(root)
    for directory in paths.required_dirs:
        directory.mkdir(parents=True, exist_ok=True)
    return paths


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
    raw_query: dict[str, str]
    unknown_query: dict[str, str]
    imported_at: str
    source: str

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
            "rawQuery": dict(self.raw_query),
            "unknownQuery": dict(self.unknown_query),
            "importedAt": self.imported_at,
            "source": self.source,
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
            raw_query={str(k): str(v) for k, v in dict(data.get("rawQuery", {})).items()},
            unknown_query={str(k): str(v) for k, v in dict(data.get("unknownQuery", {})).items()},
            imported_at=str(data.get("importedAt", _utc_now())),
            source=str(data.get("source", "stored")),
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
            "unknownQueryKeys": sorted(self.unknown_query),
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
    query = {key: value for key, value in parse_qsl(parsed.query, keep_blank_values=True)}
    if not query:
        raise ValueError("VLESS URI должен содержать query-параметры; минимум encryption=none")
    unknown = {key: value for key, value in query.items() if key not in KNOWN_VLESS_QUERY_KEYS}
    remarks = unquote(parsed.fragment or "").strip() or "unnamed-vless"
    raw_id_material = f"{parsed.scheme.lower()}://{user_id}@{parsed.hostname}:{parsed.port}?{parsed.query}#{parsed.fragment}"
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
        raw_query=query,
        unknown_query=unknown,
        imported_at=_utc_now(),
        source=source,
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
    for profile in preview.valid_profiles:
        _append_event(paths, profile_id, "connection-imported", "VLESS tunnel connection imported from text source", profile.redacted_dict())

    lines = [
        "Tunnel VLESS batch import",
        f"profile: {profile_id}",
        f"source: {source}",
        f"candidates: {preview.candidate_count}",
        f"imported valid profiles: {preview.valid_count}",
        f"rejected candidates: {len(preview.rejected)}",
        f"connections file: {connections_path}",
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


def _core_argv(core_binary: str, core_kind: str, config_path: Path) -> tuple[str, ...]:
    if core_kind == "sing-box":
        return (core_binary, "run", "-c", str(config_path))
    return (core_binary, "run", "-config", str(config_path))


def _stream_settings(profile: VlessConnectionProfile) -> dict[str, Any]:
    security = profile.security or "none"
    network = profile.network or "tcp"
    stream: dict[str, Any] = {"network": network}
    if security != "none":
        stream["security"] = security
    if security == "tls":
        tls: dict[str, Any] = {}
        server_name = profile.sni or profile.host
        if server_name:
            tls["serverName"] = server_name
        if profile.alpn:
            tls["alpn"] = list(profile.alpn)
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
            reality["publicKey"] = public_key
        if fingerprint:
            reality["fingerprint"] = fingerprint
        if short_id:
            reality["shortId"] = short_id
        if spider_x:
            reality["spiderX"] = spider_x
        if profile.alpn:
            reality["alpn"] = list(profile.alpn)
        if reality:
            stream["realitySettings"] = reality
    if network == "tcp" and profile.header_type and profile.header_type != "none":
        header: dict[str, Any] = {"type": profile.header_type}
        if profile.header_type == "http" and profile.host:
            header["request"] = {"headers": {"Host": [profile.host]}}
        stream["tcpSettings"] = {"header": header}
    elif network == "ws":
        ws: dict[str, Any] = {}
        if profile.path:
            ws["path"] = profile.path
        if profile.host:
            ws["headers"] = {"Host": profile.host}
        if ws:
            stream["wsSettings"] = ws
    elif network == "grpc":
        service_name = profile.raw_query.get("serviceName") or profile.raw_query.get("serviceName", "")
        if service_name:
            stream["grpcSettings"] = {"serviceName": service_name}
    return stream


def generate_xray_vless_socks_config(profile: VlessConnectionProfile, *, socks_host: str = DEFAULT_SOCKS_HOST, socks_port: int = DEFAULT_SOCKS_PORT, udp: bool = False) -> dict[str, Any]:
    user: dict[str, Any] = {"id": profile.user_id, "encryption": profile.encryption or "none", "level": 8}
    if profile.flow:
        user["flow"] = profile.flow
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "zap2-discord-socks",
                "listen": socks_host,
                "port": socks_port,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": bool(udp), "userLevel": 8},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
            }
        ],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": {"vnext": [{"address": profile.server, "port": profile.port, "users": [user]}]},
                "streamSettings": _stream_settings(profile),
                "mux": {"enabled": False},
            },
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {"domainStrategy": "AsIs", "rules": []},
    }


def _redact_core_config(config: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(config))
    try:
        vnext = redacted["outbounds"][0]["settings"]["vnext"][0]
        vnext["address"] = _redact_host(vnext.get("address", ""))
        for user in vnext.get("users", []):
            if "id" in user:
                user["id"] = _redact_uuid(str(user["id"]))
        reality = redacted["outbounds"][0].get("streamSettings", {}).get("realitySettings", {})
        if "serverName" in reality:
            reality["serverName"] = _redact_host(str(reality["serverName"]))
        if "publicKey" in reality:
            reality["publicKey"] = str(reality["publicKey"])[:8] + "…"
        if "shortId" in reality:
            reality["shortId"] = str(reality["shortId"])[:4] + "…"
        tls = redacted["outbounds"][0].get("streamSettings", {}).get("tlsSettings", {})
        if "serverName" in tls:
            tls["serverName"] = _redact_host(str(tls["serverName"]))
    except (KeyError, IndexError, TypeError):
        pass
    return redacted


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
            f"local socks: socks5://{self.socks_host}:{self.socks_port}",
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


def _build_plan_payload(*, root: Path, profile_id: str, connection: VlessConnectionProfile, core_binary: str, core_kind: str, socks_host: str, socks_port: int, config_path: Path, core_config_hash: str) -> dict[str, Any]:
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
        "localSocks": {"host": socks_host, "port": socks_port, "udp": False},
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
        },
        "execution": {"executesNow": False, "startsTunnelNow": False, "executesDiscordNow": False},
    }


def discord_tunnel_plan_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, core_binary: str | None = None, core_kind: str = DEFAULT_CORE_KIND, socks_port: int = DEFAULT_SOCKS_PORT, root: Path | None = None) -> str:
    if socks_port <= 0 or socks_port > 65535:
        raise ValueError("--tunnel-socks-port должен быть 1..65535")
    paths = ensure_tunnel_store(root)
    connection = _load_active_connection(paths, profile_id)
    resolved_binary, source = _resolve_core_binary(core_binary)
    kind = _core_kind_from_binary(resolved_binary or "xray", core_kind)
    core_exists = bool(resolved_binary and Path(resolved_binary).exists() and os.access(resolved_binary, os.X_OK))
    config = generate_xray_vless_socks_config(connection, socks_host=DEFAULT_SOCKS_HOST, socks_port=socks_port)
    config_hash = _sha256_json(config)
    config_path = _generated_config_path(paths, profile_id)
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
    )
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
    ).to_text()
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
                f"local socks: socks5://{session.get('socksHost', DEFAULT_SOCKS_HOST)}:{session.get('socksPort', DEFAULT_SOCKS_PORT)}",
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
    config = generate_xray_vless_socks_config(connection, socks_host=socks_host, socks_port=socks_port)
    config_path = _generated_config_path(paths, profile_id)
    _write_json(config_path, config, secret=True)
    argv = _core_argv(core_binary, core_kind, config_path)
    stdout_path = _stdout_path(paths, profile_id)
    stderr_path = _stderr_path(paths, profile_id)
    stdout_handle = stdout_path.open("ab")
    stderr_handle = stderr_path.open("ab")
    try:
        process = subprocess.Popen(argv, cwd=str(paths.root), stdout=stdout_handle, stderr=stderr_handle, start_new_session=True)
    finally:
        stdout_handle.close()
        stderr_handle.close()
    time.sleep(0.5)
    running = process.poll() is None
    session_payload = {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "marker": TUNNEL_MARKER,
        "profileId": profile_id,
        "planId": confirm_plan_id,
        "planHash": str(plan.get("planHash")),
        "connectionId": connection.connection_id,
        "coreBinary": core_binary,
        "coreKind": core_kind,
        "argv": list(argv),
        "pid": process.pid,
        "startedAt": _utc_now(),
        "socksHost": socks_host,
        "socksPort": socks_port,
        "configPath": str(config_path),
        "configHash": _sha256_json(config),
        "stdoutLog": str(stdout_path),
        "stderrLog": str(stderr_path),
        "runningAfterGrace": running,
        "state": "running" if running else "failed",
    }
    _write_json(session_path, session_payload, secret=True)
    log_path = _append_event(paths, profile_id, "tunnel-started" if running else "tunnel-start-failed", "External tunnel core launched" if running else "External tunnel core exited during start grace", {"pid": process.pid, "running": running, "connection": connection.redacted_dict()})
    return "\n".join(
        [
            f"Discord tunnel start: {'started' if running else 'failed'}",
            f"profile: {profile_id}",
            f"connection: {connection.connection_id}",
            f"pid: {process.pid}",
            f"core: {core_binary} ({core_kind})",
            f"local socks: socks5://{socks_host}:{socks_port}",
            f"config: {config_path}",
            f"session file: {session_path}",
            f"stdout: {stdout_path}",
            f"stderr: {stderr_path}",
            f"tunnel log: {log_path}",
            "owner confirmation verified: yes",
            "requires sudo: no",
            "mutates firewall/services: no",
            f"parallel with zapret allowed: {'yes' if allow_parallel_with_zapret else 'no'}",
            "executes Discord now: no",
            "NEXT: PYTHONPATH=gui python -m zap2_gui.app --discord-tunnel-probe",
        ]
    )


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


def _socks5_handshake_probe(host: str, port: int, timeout: float = 2.0) -> dict[str, Any]:
    """Verify that the loopback listener speaks no-auth SOCKS5.

    A plain TCP connect followed by close makes v2ray/xray log
    `proxy/socks: insufficient header > EOF`, which looks scarier than it is.
    The handshake probe sends the minimal SOCKS5 greeting instead, so the report
    can separate "port is open" from "this is a usable SOCKS listener".
    """

    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(b"\x05\x01\x00")
            response = sock.recv(2)
    except OSError as exc:
        return {
            "ok": False,
            "portOpen": False,
            "stage": "connect",
            "message": str(exc),
            "elapsedMs": int((time.monotonic() - started) * 1000),
        }
    ok = response == b"\x05\x00"
    return {
        "ok": ok,
        "portOpen": True,
        "stage": "socks5-greeting",
        "responseHex": response.hex(),
        "message": "SOCKS5 no-auth greeting accepted" if ok else "loopback port did not return SOCKS5 no-auth greeting",
        "elapsedMs": int((time.monotonic() - started) * 1000),
    }


def _wait_for_socks5_handshake(host: str, port: int, *, deadline_seconds: float = 5.0, timeout: float = 0.5) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.1, deadline_seconds)
    last: dict[str, Any] = {"ok": False, "message": "probe not started"}
    while time.monotonic() < deadline:
        last = _socks5_handshake_probe(host, port, timeout=timeout)
        if bool(last.get("ok")):
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
    socks_probe = _socks5_handshake_probe(socks_host, socks_port)
    port_open = bool(socks_probe.get("portOpen"))
    handshake_ok = bool(socks_probe.get("ok"))
    if running and handshake_ok:
        verdict = "T0_SOCKS_READY"
    elif running and port_open:
        verdict = "T0_PORT_OPEN_NOT_SOCKS"
    elif stored_state == "failed":
        verdict = "T0_CORE_FAILED"
    else:
        verdict = "T0_CORE_NOT_READY"
    report = {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "createdAt": _utc_now(),
        "profileId": profile_id,
        "pid": pid,
        "coreRunning": running,
        "storedState": stored_state,
        "procState": _proc_state(pid) if pid else "none",
        "socksHost": socks_host,
        "socksPort": socks_port,
        "socksPortOpen": port_open,
        "socksHandshakeOk": handshake_ok,
        "socksHandshake": socks_probe,
        "upstreamTested": False,
        "verdict": verdict,
    }
    reports_dir = paths.tunnel_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{profile_id}.tunnel-probe.json"
    _write_json(report_path, report, secret=False)
    _append_event(paths, profile_id, "tunnel-probed", "Tunnel SOCKS handshake probe completed", {"verdict": verdict, "socksPortOpen": port_open, "socksHandshakeOk": handshake_ok})
    lines.extend(
        [
            f"pid: {pid if pid else 'нет'}",
            f"stored state: {stored_state}",
            f"proc state: {_proc_state(pid) if pid else 'none'}",
            f"core running: {'yes' if running else 'no'}",
            f"local socks: socks5://{socks_host}:{socks_port}",
            f"socks port open: {'yes' if port_open else 'no'}",
            f"socks handshake: {'ok' if handshake_ok else 'no'}",
            f"probe message: {socks_probe.get('message', 'n/a')}",
            "upstream tested: no",
            f"verdict: {verdict}",
            f"report: {report_path}",
        ]
    )
    failure = _last_core_failure_summary(paths, profile_id) if verdict == "T0_CORE_FAILED" else ""
    if failure:
        lines.extend(["", "core failure details:", failure])
    if verdict == "T0_CORE_FAILED":
        lines.append("NEXT: fix the core/profile compatibility, then run tunnel start again. Do not launch Discord yet.")
    else:
        lines.append("NEXT: run --discord-tunnel-https-probe to test the VLESS upstream path through this SOCKS listener.")
    lines.extend(
        [
            "executes Discord now: no",
            "mutates firewall/services: no",
        ]
    )
    return "\n".join(lines)


def _resolve_discord_launch_command(discord_command: str) -> tuple[tuple[str, ...], str]:
    raw = (discord_command or DEFAULT_DISCORD_COMMAND).strip()
    if not raw:
        raise ValueError("Discord command пустой. Передайте --discord-binary discord или --discord-binary 'flatpak run com.discordapp.Discord'.")
    parts = tuple(shlex.split(raw)) if any(ch.isspace() for ch in raw) else (raw,)
    if not parts:
        raise ValueError("Discord command пустой после parsing.")
    first = parts[0]
    resolved_first = shutil.which(first) or str(Path(first).expanduser())
    if not resolved_first or not Path(resolved_first).exists():
        raise ValueError(
            "Discord command не найден. Примеры: --discord-binary discord или --discord-binary 'flatpak run com.discordapp.Discord'."
        )
    return (resolved_first, *parts[1:]), raw


def _discord_launch_argv(discord_command: str, socks_host: str, socks_port: int, mode: str) -> tuple[tuple[str, ...], str]:
    base_argv, raw = _resolve_discord_launch_command(discord_command)
    proxy = f"socks5://{socks_host}:{socks_port}"
    # Electron/Chromium candidate flag. Environment variables are set separately.
    if mode == "socks-env-only":
        return base_argv, raw
    return (*base_argv, f"--proxy-server={proxy}"), raw


def _is_flatpak_command(argv: tuple[str, ...]) -> bool:
    return bool(argv) and Path(argv[0]).name == "flatpak" and "run" in argv[:3]


def discord_proxy_route_plan_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> str:
    """Explain the missing routing step between local SOCKS and Discord."""

    paths = ensure_tunnel_store(root)
    session_path = _session_path(paths, profile_id)
    socks_host = DEFAULT_SOCKS_HOST
    socks_port = DEFAULT_SOCKS_PORT
    state = "not-started"
    if session_path.exists():
        session = _read_json(session_path)
        socks_host = str(session.get("socksHost", DEFAULT_SOCKS_HOST))
        socks_port = int(session.get("socksPort", DEFAULT_SOCKS_PORT))
        pid = int(session.get("pid", 0) or 0)
        stored_state = str(session.get("state", "running" if pid else "not-started"))
        state = "running" if stored_state == "running" and _pid_running(pid) else stored_state if stored_state in {"stopped", "failed"} else "stale"
    proxy = f"socks5://{socks_host}:{socks_port}"
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
            f"- Flatpak Discord: PYTHONPATH=gui python -m zap2_gui.app --discord-launch-through-socks --discord-binary \"{FLATPAK_DISCORD_COMMAND}\"",
            f"- Native Discord:  PYTHONPATH=gui python -m zap2_gui.app --discord-launch-through-socks --discord-binary discord",
            f"- Curl check:      curl --socks5-hostname {socks_host}:{socks_port} -I https://updates.discord.com/",
            "",
            "Firefox/web Discord:",
            f"- Set manual SOCKS v5 host={socks_host}, port={socks_port}, and enable remote DNS through SOCKS if available.",
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
    socks_probe = _wait_for_socks5_handshake(socks_host, socks_port)
    if not bool(socks_probe.get("ok")):
        raise ValueError(
            "Tunnel core process найден, но SOCKS handshake не прошёл: "
            f"{socks_probe.get('message', 'unknown')}. Discord не будет запущен, чтобы не получить ERR_PROXY_CONNECTION_FAILED. "
            "Запустите --discord-tunnel-probe и проверьте core stdout/stderr."
        )
    preflight_result: dict[str, Any] | None = None
    preflight_report_path: Path | None = None
    if upstream_preflight:
        try:
            preflight_result = _https_head_through_socks(
                socks_host=socks_host,
                socks_port=socks_port,
                target_host=preflight_host,
                target_path=preflight_path,
                timeout=float(preflight_timeout),
            )
        except Exception as exc:  # captured into report so the owner can attach it
            preflight_result = {"ok": False, "stage": "exception", "message": str(exc), "elapsedMs": None}
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
                "targetPath": preflight_path,
                "socksHost": socks_host,
                "socksPort": socks_port,
                "result": preflight_result,
                "verdict": "T1_HTTPS_THROUGH_SOCKS_OK" if preflight_result.get("ok") else "T1_HTTPS_THROUGH_SOCKS_FAILED",
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
                f"report: {preflight_report_path}. "
                "Это защищает от запуска Electron в заведомо сломанный VLESS route. "
                "Для ручного эксперимента можно повторить с --discord-launch-allow-failed-preflight."
            )

    proxy = f"socks5://{socks_host}:{socks_port}"
    env = dict(os.environ)
    if launch_mode != "socks-flag-only":
        env.update({"ALL_PROXY": proxy, "HTTPS_PROXY": proxy, "HTTP_PROXY": proxy, "all_proxy": proxy, "https_proxy": proxy, "http_proxy": proxy})
    argv, raw_command = _discord_launch_argv(discord_binary, socks_host, socks_port, launch_mode)
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
        "launchMode": launch_mode,
        "discordCommand": raw_command,
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
            "targetPath": preflight_path if upstream_preflight else "",
            "ok": bool(preflight_result.get("ok")) if preflight_result else None,
            "stage": preflight_result.get("stage") if preflight_result else "",
            "report": str(preflight_report_path) if preflight_report_path else "",
            "allowFailed": bool(allow_failed_preflight),
        },
    }
    discord_session_path = _discord_session_path(paths, profile_id)
    _write_json(discord_session_path, discord_session, secret=False)
    _append_event(paths, profile_id, "discord-launched-through-socks", "Discord launched with SOCKS env/flag candidates", {"pid": process.pid, "launchMode": launch_mode, "socks": proxy, "runningAfterGrace": discord_running, "upstreamPreflight": bool(upstream_preflight), "upstreamPreflightOk": bool(preflight_result.get("ok")) if preflight_result else None})
    return "\n".join(
        [
            "Discord launch through SOCKS: started",
            f"profile: {profile_id}",
            f"launch mode: {launch_mode}",
            f"discord command: {raw_command}",
            f"discord pid: {process.pid}",
            f"discord running after grace: {'yes' if discord_running else 'no'}",
            f"argv: {shlex.join(argv)}",
            f"proxy env: {proxy}",
            f"flatpak command: {'yes' if flatpak else 'no'}",
            f"discord session: {discord_session_path}",
            f"discord stdout: {stdout_path}",
            f"discord stderr: {stderr_path}",
            f"upstream preflight: {'ok' if preflight_result and preflight_result.get('ok') else 'skipped' if not upstream_preflight else 'failed-but-allowed'}",
            f"preflight report: {preflight_report_path if preflight_report_path else 'нет'}",
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


def _socks5_connect(sock: socket.socket, host: str, port: int) -> dict[str, Any]:
    host_bytes = host.encode("idna")
    if len(host_bytes) > 255:
        raise ValueError("SOCKS target host is too long")
    sock.sendall(b"\x05\x01\x00")
    hello = _read_exact(sock, 2)
    if hello != b"\x05\x00":
        return {"ok": False, "stage": "socks-auth", "replyHex": hello.hex(), "message": "SOCKS5 no-auth was not accepted"}
    request = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + int(port).to_bytes(2, "big")
    sock.sendall(request)
    header = _read_exact(sock, 4)
    if len(header) != 4 or header[0] != 5:
        return {"ok": False, "stage": "socks-connect", "replyHex": header.hex(), "message": "SOCKS5 connect returned malformed header"}
    atyp = header[3]
    if atyp == 1:
        _read_exact(sock, 4)
    elif atyp == 3:
        size = _read_exact(sock, 1)[0]
        _read_exact(sock, size)
    elif atyp == 4:
        _read_exact(sock, 16)
    else:
        return {"ok": False, "stage": "socks-connect", "replyHex": header.hex(), "message": f"SOCKS5 connect returned unsupported ATYP {atyp}"}
    _read_exact(sock, 2)
    rep = header[1]
    if rep != 0:
        return {"ok": False, "stage": "socks-connect", "replyCode": rep, "message": f"SOCKS5 connect failed with REP={rep}"}
    return {"ok": True, "stage": "socks-connect", "message": "SOCKS5 connect established"}


def _https_head_through_socks(*, socks_host: str, socks_port: int, target_host: str, target_path: str, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    target_path = target_path if target_path.startswith("/") else f"/{target_path}"
    with socket.create_connection((socks_host, int(socks_port)), timeout=timeout) as raw_sock:
        raw_sock.settimeout(timeout)
        socks_result = _socks5_connect(raw_sock, target_host, 443)
        if not socks_result.get("ok"):
            socks_result["elapsedMs"] = int((time.monotonic() - started) * 1000)
            return socks_result
        context = ssl.create_default_context()
        with context.wrap_socket(raw_sock, server_hostname=target_host) as tls_sock:
            tls_sock.settimeout(timeout)
            request = (
                f"HEAD {target_path} HTTP/1.1\r\n"
                f"Host: {target_host}\r\n"
                "User-Agent: Zap2GUIfLin-tunnel-probe/1\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            tls_sock.sendall(request)
            response = tls_sock.recv(768)
    first_line = response.splitlines()[0].decode("iso-8859-1", errors="replace") if response else ""
    status_code = None
    if first_line.startswith("HTTP/"):
        parts = first_line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            status_code = int(parts[1])
    ok = status_code is not None and 100 <= status_code < 600
    return {
        "ok": ok,
        "stage": "https-head",
        "statusLine": first_line,
        "statusCode": status_code,
        "elapsedMs": int((time.monotonic() - started) * 1000),
        "message": "HTTPS HEAD through SOCKS completed" if ok else "HTTPS HEAD through SOCKS did not return an HTTP status line",
    }


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
    report_base = {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "createdAt": _utc_now(),
        "profileId": profile_id,
        "targetHost": target_host,
        "targetPath": target_path,
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
        )
    except Exception as exc:  # deliberately captured into report for owner diagnosis
        result = {"ok": False, "stage": "exception", "message": str(exc), "elapsedMs": None}
    verdict = "T1_HTTPS_THROUGH_SOCKS_OK" if result.get("ok") else "T1_HTTPS_THROUGH_SOCKS_FAILED"
    report = {**report_base, "result": result, "verdict": verdict}
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
    if session_path.exists():
        session = _read_json(session_path)
        tunnel_pid = int(session.get("pid", 0) or 0)
        stored = str(session.get("state", "running" if tunnel_pid else "not-started"))
        socks_host = str(session.get("socksHost", DEFAULT_SOCKS_HOST))
        socks_port = int(session.get("socksPort", DEFAULT_SOCKS_PORT))
        tunnel_state = "running" if stored == "running" and _pid_running(tunnel_pid) else stored if stored in {"stopped", "failed"} else "stale"
        socks_probe = _socks5_handshake_probe(socks_host, socks_port)

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
        f"Next: {next_step}",
        "read-only: yes",
        "executes Discord now: no",
        "mutates firewall/services: no",
    ]
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
    )
    plan_id = _tunnel_plan_id(profile_id)
    confirmation = confirm_runtime_plan(root=paths.root, plan_id=plan_id)
    start_text = discord_tunnel_start_to_text(profile_id=profile_id, confirm_plan_id=plan_id, root=paths.root)
    core_probe_text = discord_tunnel_probe_to_text(profile_id=profile_id, root=paths.root)
    https_text = discord_tunnel_https_probe_to_text(profile_id=profile_id, root=paths.root)
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
            f"tunnel core: {'started/ready' if 'Discord tunnel start: started' in start_text or 'already-running' in start_text else 'check start output'}",
            f"https probe verdict: {https_verdict}",
            f"discord pid: {discord_pid if discord_pid else 'нет'}",
            f"owner updater result: {observed_result}",
            f"verdict: {verdict}",
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
