"""Discord SOCKS/VLESS tunnel lane for Stage 7p1..7p4.

This adapter deliberately does not implement the VLESS protocol itself.  It
stores owner-provided connection profiles, generates a local loopback SOCKS core
configuration for an owner-selected external core, and manages only the process
recorded in Zap2's local tunnel session file.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, unquote, urlsplit

from .runtime_default import default_workflow_status
from .runtime_state import ensure_runtime_store, plan_payload_hash
from ..project_paths import discover_layout

TUNNEL_STAGE = "v0.4-alpha_stage7p1-7p4"
TUNNEL_SCHEMA_VERSION = 1
TUNNEL_MARKER = "zap2-discord-tunnel-v1"
DEFAULT_PROFILE_ID = "default"
DEFAULT_SOCKS_HOST = "127.0.0.1"
DEFAULT_SOCKS_PORT = 10808
DEFAULT_CORE_KIND = "auto"
SUPPORTED_CORE_KINDS = ("auto", "xray", "v2ray", "sing-box")
SUPPORTED_LAUNCH_MODES = ("socks-updater-window", "socks-full-session")
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
                    "  PYTHONPATH=gui python -m zap2_gui.app --discord-launch-through-socks",
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
    return TunnelPlan(
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


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


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
        running = _pid_running(pid)
        lines.extend(
            [
                f"state: {'running' if running else 'stale'}",
                f"pid: {pid if pid else 'нет'}",
                f"core running: {'yes' if running else 'no'}",
                f"connection: {session.get('connectionId', 'нет')}",
                f"local socks: socks5://{session.get('socksHost', DEFAULT_SOCKS_HOST)}:{session.get('socksPort', DEFAULT_SOCKS_PORT)}",
                f"config: {session.get('configPath', 'нет')}",
                f"stdout: {session.get('stdoutLog', 'нет')}",
                f"stderr: {session.get('stderrLog', 'нет')}",
            ]
        )
    try:
        active = _load_active_connection(paths, profile_id)
        lines.extend([f"active connection: {active.connection_id}", f"active remarks: {active.remarks}"])
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


def discord_tunnel_start_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, confirm_plan_id: str = "", root: Path | None = None) -> str:
    paths = ensure_tunnel_store(root)
    _assert_zapret_workflow_not_running(profile_id)
    plan = _load_confirmed_tunnel_plan(paths, profile_id, confirm_plan_id)
    connection = _load_active_connection(paths, profile_id)
    if connection.connection_id != str(plan.get("connectionId")):
        raise ValueError("Active tunnel connection changed after plan confirmation. Re-run --discord-tunnel-plan and --runtime-confirm.")
    core_binary = str(plan["core"].get("binary", ""))
    core_kind = str(plan["core"].get("kind", "xray"))
    if not core_binary or not Path(core_binary).exists() or not os.access(core_binary, os.X_OK):
        raise ValueError("Tunnel core binary отсутствует или не исполняемый. Re-run --discord-tunnel-plan --tunnel-core-binary /path/to/core.")
    session_path = _session_path(paths, profile_id)
    if session_path.exists():
        session = _read_json(session_path)
        pid = int(session.get("pid", 0) or 0)
        if _pid_running(pid):
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


def discord_tunnel_probe_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, root: Path | None = None) -> str:
    paths = ensure_tunnel_store(root)
    session_path = _session_path(paths, profile_id)
    lines = ["Discord tunnel probe", f"stage: {TUNNEL_STAGE}", f"profile: {profile_id}"]
    if not session_path.exists():
        lines.extend(["state: not-started", "verdict: T0_NOT_RUNNING", "next: --discord-tunnel-plan; --runtime-confirm; --discord-tunnel-start"])
        return "\n".join(lines)
    session = _read_json(session_path)
    pid = int(session.get("pid", 0) or 0)
    running = _pid_running(pid)
    socks_host = str(session.get("socksHost", DEFAULT_SOCKS_HOST))
    socks_port = int(session.get("socksPort", DEFAULT_SOCKS_PORT))
    port_open = _connect_loopback(socks_host, socks_port)
    verdict = "T0_CORE_ONLY" if running and port_open else "T0_CORE_NOT_READY"
    report = {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "createdAt": _utc_now(),
        "profileId": profile_id,
        "pid": pid,
        "coreRunning": running,
        "socksHost": socks_host,
        "socksPort": socks_port,
        "socksPortOpen": port_open,
        "verdict": verdict,
    }
    reports_dir = paths.tunnel_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{profile_id}.tunnel-probe.json"
    _write_json(report_path, report, secret=False)
    _append_event(paths, profile_id, "tunnel-probed", "Tunnel core probe completed", report)
    lines.extend(
        [
            f"pid: {pid if pid else 'нет'}",
            f"core running: {'yes' if running else 'no'}",
            f"local socks: socks5://{socks_host}:{socks_port}",
            f"socks port open: {'yes' if port_open else 'no'}",
            f"verdict: {verdict}",
            f"report: {report_path}",
            "executes Discord now: no",
            "mutates firewall/services: no",
        ]
    )
    return "\n".join(lines)


def _discord_launch_argv(discord_binary: str, socks_host: str, socks_port: int, mode: str) -> tuple[str, ...]:
    proxy = f"socks5://{socks_host}:{socks_port}"
    # Electron/Chromium candidate flag.  Environment variables are set separately.
    return (discord_binary, f"--proxy-server={proxy}")


def discord_launch_through_socks_to_text(*, profile_id: str = DEFAULT_PROFILE_ID, discord_binary: str = "discord", launch_mode: str = "socks-updater-window", root: Path | None = None) -> str:
    if launch_mode not in SUPPORTED_LAUNCH_MODES:
        raise ValueError(f"Unsupported launch mode: {launch_mode}")
    paths = ensure_tunnel_store(root)
    session_path = _session_path(paths, profile_id)
    if not session_path.exists():
        raise ValueError("Tunnel session не найден. Сначала запустите --discord-tunnel-start.")
    session = _read_json(session_path)
    pid = int(session.get("pid", 0) or 0)
    if not _pid_running(pid):
        raise ValueError("Tunnel core не running; сначала проверьте --discord-tunnel-status/--discord-tunnel-start.")
    socks_host = str(session.get("socksHost", DEFAULT_SOCKS_HOST))
    socks_port = int(session.get("socksPort", DEFAULT_SOCKS_PORT))
    resolved_discord = shutil.which(discord_binary) or str(Path(discord_binary).expanduser())
    if not resolved_discord or not Path(resolved_discord).exists():
        raise ValueError("Discord binary не найден. Передайте --discord-binary /path/to/discord или установите binary в PATH.")
    proxy = f"socks5://{socks_host}:{socks_port}"
    env = dict(os.environ)
    env.update({"ALL_PROXY": proxy, "HTTPS_PROXY": proxy, "HTTP_PROXY": proxy, "all_proxy": proxy, "https_proxy": proxy, "http_proxy": proxy})
    argv = _discord_launch_argv(resolved_discord, socks_host, socks_port, launch_mode)
    process = subprocess.Popen(argv, cwd=str(paths.root), env=env, start_new_session=True)
    discord_session = {
        "schemaVersion": TUNNEL_SCHEMA_VERSION,
        "stage": TUNNEL_STAGE,
        "profileId": profile_id,
        "launchMode": launch_mode,
        "discordBinary": resolved_discord,
        "argv": list(argv),
        "pid": process.pid,
        "startedAt": _utc_now(),
        "proxy": proxy,
        "tunnelSession": str(session_path),
    }
    discord_session_path = _discord_session_path(paths, profile_id)
    _write_json(discord_session_path, discord_session, secret=False)
    _append_event(paths, profile_id, "discord-launched-through-socks", "Discord launched with SOCKS env/flag candidates", {"pid": process.pid, "launchMode": launch_mode, "socks": proxy})
    return "\n".join(
        [
            "Discord launch through SOCKS: started",
            f"profile: {profile_id}",
            f"launch mode: {launch_mode}",
            f"discord pid: {process.pid}",
            f"argv: {shlex.join(argv)}",
            f"proxy env: {proxy}",
            f"discord session: {discord_session_path}",
            "MANUAL ACTION:",
            "  Watch Discord. If it reaches the main window, keep the tunnel running and record that result.",
            "  If it stays on Checking for updates, run --discord-tunnel-probe and attach .zap2/tunnel/runtime + reports.",
            "executes Discord now: yes",
            "mutates firewall/services: no",
        ]
    )
