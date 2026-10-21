"""Managed system C Tor and Arti SOCKS backends.

Both backends remain separate executables. z2guiflin owns only generated
configuration, project-local state/log paths and the PID recorded in the shared
tunnel session. No package installation, download, sudo, firewall or systemd
mutation is performed here.

Мосты и pluggable transports (``tor_bridges``) попадают в конфиг из плана: план хранит
digest строк мостов и пути к транспортам, старт сверяет digest и строит тот же конфиг.
Слушать можно фиксированный порт, случайный порт или unix-сокет (только C Tor).
Порт на 127.0.0.1 доступен любой программе и любому пользователю этой машины:
localhost — не приватность. Unix-сокет в каталоге 0700 доступен только вам.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .runtime_state import ensure_runtime_store, plan_payload_hash
from .tor_bridges import BridgeLine, bridges_digest, detect_transport_programs, load_bridges, plugin_groups
from ..project_paths import discover_layout

TOR_STAGE = "v0.4-alpha_stage8g"
TOR_SCHEMA_VERSION = 1
TOR_MARKER = "zap2-tor-backend-v1"
SUPPORTED_TOR_BACKENDS = ("c-tor", "arti")
DEFAULT_TOR_BACKEND = "c-tor"
DEFAULT_TOR_SOCKS_HOST = "127.0.0.1"
DEFAULT_TOR_SOCKS_PORT = 19050
LISTEN_MODES = ("port", "random", "unix")
_UNIX_PATH_MAX = 100  # sun_path — 108 байт, с запасом
_BOOTSTRAP = re.compile(r"Bootstrapped (\d{1,3})%(?: \(([^)]*)\))?:? ?(.*)")


@dataclass(frozen=True)
class TorBackendPaths:
    root: Path
    tor_root: Path
    generated_dir: Path
    data_dir: Path
    runtime_dir: Path
    logs_dir: Path
    plans_dir: Path
    confirmations_dir: Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any], *, secret: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if secret:
        try:
            path.chmod(0o600)
        except OSError:
            pass


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def tor_backend_paths(root: Path | None = None) -> TorBackendPaths:
    layout = discover_layout(root)
    runtime = ensure_runtime_store(layout.root)
    tor_root = layout.root / ".zap2" / "tor"
    return TorBackendPaths(
        root=layout.root,
        tor_root=tor_root,
        generated_dir=tor_root / "generated",
        data_dir=tor_root / "data",
        runtime_dir=tor_root / "runtime",
        logs_dir=tor_root / "logs",
        plans_dir=runtime.plans_dir,
        confirmations_dir=runtime.confirmations_dir,
    )


def ensure_tor_backend_store(root: Path | None = None) -> TorBackendPaths:
    paths = tor_backend_paths(root)
    for item in (paths.tor_root, paths.generated_dir, paths.data_dir, paths.runtime_dir, paths.logs_dir):
        item.mkdir(parents=True, exist_ok=True)
    return paths


def _shared_tunnel_session(paths: TorBackendPaths, profile_id: str) -> Path:
    target = paths.root / ".zap2" / "tunnel" / "runtime" / f"{profile_id}.session.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _tor_session(paths: TorBackendPaths, profile_id: str) -> Path:
    return paths.runtime_dir / f"{profile_id}.session.json"


def _plan_id(profile_id: str, backend: str) -> str:
    return f"runtime-{profile_id}-tor-{backend}-start-plan"


def _resolve_binary(backend: str, explicit: str | None) -> tuple[str, str]:
    if explicit:
        return str(Path(explicit).expanduser()), "explicit"
    env_name = "ZAP2_ARTI_BINARY" if backend == "arti" else "ZAP2_TOR_BINARY"
    if os.environ.get(env_name):
        return str(Path(os.environ[env_name]).expanduser()), env_name
    name = "arti" if backend == "arti" else "tor"
    found = shutil.which(name)
    return (found, f"PATH:{name}") if found else ("", "not-found")


def _quote_torrc_path(path: Path) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _torrc_value(path: str) -> str:
    return path if not any(ch.isspace() or ch == '"' for ch in path) else _quote_torrc_path(Path(path))


def generate_c_tor_config(paths: TorBackendPaths, *, socks_host: str, socks_port: int,
                          bridges: tuple[BridgeLine, ...] = (),
                          plugins: tuple[tuple[tuple[str, ...], str], ...] = (),
                          socks_unix: str = "") -> str:
    data = paths.data_dir / "c-tor"
    data.mkdir(parents=True, exist_ok=True)
    listen = f"unix:{_torrc_value(socks_unix)}" if socks_unix else f"{socks_host}:{socks_port}"
    lines = [
        "ClientOnly 1",
        f"SocksPort {listen}",
        f"DataDirectory {_quote_torrc_path(data)}",
        "SafeLogging 1",
        "Log notice stdout",
        "AvoidDiskWrites 1",
    ]
    if bridges:
        lines.append("UseBridges 1")
        for transports, program in plugins:
            lines.append(f"ClientTransportPlugin {','.join(transports)} exec {_torrc_value(program)}")
        lines.extend(f"Bridge {item.line}" for item in bridges)
    lines.append("")
    return "\n".join(lines)


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def generate_arti_config(paths: TorBackendPaths, *, socks_host: str, socks_port: int,
                         bridges: tuple[BridgeLine, ...] = (),
                         plugins: tuple[tuple[tuple[str, ...], str], ...] = ()) -> str:
    cache = paths.data_dir / "arti-cache"
    state = paths.data_dir / "arti-state"
    cache.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Generated by z2guiflin." + (" Bridges enabled." if bridges else " Direct Tor network."),
        "[proxy]",
        f"socks_listen = {_toml_string(f'{socks_host}:{socks_port}')}",
        "dns_listen = 0",
        "",
        "[storage]",
        f"cache_dir = {_toml_string(str(cache))}",
        f"state_dir = {_toml_string(str(state))}",
        "",
    ]
    if bridges:
        lines += ["[bridges]", "enabled = true", "bridges = ["]
        lines += [f"  {_toml_string(item.line)}," for item in bridges]
        lines += ["]", ""]
        for transports, program in plugins:
            lines += [
                "[[bridges.transports]]",
                "protocols = [" + ", ".join(_toml_string(item) for item in transports) + "]",
                f"path = {_toml_string(program)}",
                "arguments = []",
                "run_on_startup = false",
                "",
            ]
    return "\n".join(lines)


def default_unix_socket_path(paths: TorBackendPaths, profile_id: str = "default") -> Path:
    """Сокет в каталоге 0700: XDG_RUNTIME_DIR, если путь помещается в sun_path, иначе рабочий каталог."""

    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime:
        candidate = Path(runtime) / "zap2gui-tor" / f"{profile_id}.socks"
        if len(str(candidate)) <= _UNIX_PATH_MAX:
            return candidate
    return paths.runtime_dir / "sock" / f"{profile_id}.socks"


def _prepare_unix_socket(path: Path) -> None:
    if len(str(path)) > _UNIX_PATH_MAX:
        raise ValueError(f"Путь unix-сокета длиннее {_UNIX_PATH_MAX} символов: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)  # tor отказывается от сокета в каталоге, доступном другим
    if path.exists() or path.is_symlink():
        path.unlink()


def _free_loopback_port() -> int:
    from .discord_tunnel import pick_random_socks_port

    return pick_random_socks_port(DEFAULT_TOR_SOCKS_HOST)


def _bridge_plan(paths: TorBackendPaths, backend: str, use_bridges: bool) -> tuple[tuple[BridgeLine, ...], tuple[tuple[tuple[str, ...], str], ...], dict[str, Any]]:
    if not use_bridges:
        return (), (), {"enabled": False, "count": 0}
    bridges = load_bridges(paths.tor_root)
    if not bridges:
        raise ValueError("Мосты включены, но список пуст: вставьте строки мостов и сохраните")
    transports = tuple(dict.fromkeys(item.transport for item in bridges if item.transport))
    programs = detect_transport_programs()
    missing = programs.missing_for(transports)
    if missing:
        raise ValueError("Не найдены программы для транспортов: " + ", ".join(missing) + ". Установите их или уберите такие мосты")
    plugins = plugin_groups(transports, programs)
    return bridges, plugins, {
        "enabled": True,
        "count": len(bridges),
        "sha256": bridges_digest(bridges),
        "transports": list(transports),
        "plugins": [[list(items), program] for items, program in plugins],
    }


def _config_path(paths: TorBackendPaths, profile_id: str, backend: str) -> Path:
    suffix = "toml" if backend == "arti" else "torrc"
    return paths.generated_dir / f"{profile_id}.{backend}.{suffix}"


def _argv(binary: str, backend: str, config_path: Path) -> tuple[str, ...]:
    if backend == "arti":
        return (binary, "proxy", "-c", str(config_path))
    return (binary, "-f", str(config_path))


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat_path = Path("/proc") / str(pid) / "stat"
    try:
        state = stat_path.read_text(encoding="utf-8", errors="ignore").rsplit(")", 1)[-1].strip().split()[0]
    except (OSError, IndexError):
        return True
    return state not in {"Z", "X", "x"}


def _render_config(paths: TorBackendPaths, backend: str, *, host: str, port: int, bridges: tuple[BridgeLine, ...],
                   plugins: tuple[tuple[tuple[str, ...], str], ...], socks_unix: str) -> str:
    if backend == "arti":
        return generate_arti_config(paths, socks_host=host, socks_port=port, bridges=bridges, plugins=plugins)
    return generate_c_tor_config(paths, socks_host=host, socks_port=port, bridges=bridges, plugins=plugins, socks_unix=socks_unix)


def tor_backend_plan_to_text(*, profile_id: str = "default", backend: str = DEFAULT_TOR_BACKEND,
                             binary: str | None = None, socks_port: int = DEFAULT_TOR_SOCKS_PORT,
                             root: Path | None = None, listen: str = "port", use_bridges: bool = False) -> str:
    if backend not in SUPPORTED_TOR_BACKENDS:
        raise ValueError(f"Неизвестный Tor backend: {backend}")
    if listen not in LISTEN_MODES:
        raise ValueError(f"Неизвестный режим прослушивания: {listen}")
    if listen == "unix" and backend == "arti":
        raise ValueError("Unix-сокет поддерживается только для C Tor; для Arti выберите порт")
    paths = ensure_tor_backend_store(root)
    if listen == "random":
        socks_port = _free_loopback_port()
    if not 1 <= int(socks_port) <= 65535:
        raise ValueError("Tor SOCKS port должен быть 1..65535")
    socks_unix = str(default_unix_socket_path(paths, profile_id)) if listen == "unix" else ""
    bridges, plugins, bridge_info = _bridge_plan(paths, backend, use_bridges)
    resolved, source = _resolve_binary(backend, binary)
    exists = bool(resolved and Path(resolved).is_file() and os.access(resolved, os.X_OK))
    config_path = _config_path(paths, profile_id, backend)
    config_text = _render_config(paths, backend, host=DEFAULT_TOR_SOCKS_HOST, port=int(socks_port), bridges=bridges,
                                 plugins=plugins, socks_unix=socks_unix)
    payload = {
        "schemaVersion": TOR_SCHEMA_VERSION,
        "stage": TOR_STAGE,
        "marker": TOR_MARKER,
        "planId": _plan_id(profile_id, backend),
        "action": "tor-backend-start",
        "profileId": profile_id,
        "backend": backend,
        "binary": resolved,
        "binarySource": source,
        "localSocks": {"host": DEFAULT_TOR_SOCKS_HOST, "port": 0 if socks_unix else int(socks_port), "udp": False,
                       "unix": socks_unix, "listenMode": listen},
        "bridges": bridge_info,
        "generatedConfigPath": str(config_path.relative_to(paths.root)),
        "generatedConfigSha256": __import__("hashlib").sha256(config_text.encode()).hexdigest(),
        "safety": {
            "requiresOwnerConfirmation": True,
            "requiresSudo": False,
            "mutatesFirewallOrSystemServices": False,
            "downloadsOrInstalls": False,
            "bindsLoopbackOnly": True,
            "bridgesConfigured": bool(bridges),
            "moatBridgeRequests": False,
        },
        "execution": {"executesNow": False},
    }
    plan_hash = plan_payload_hash(payload)
    record = {**payload, "planHash": plan_hash, "preparedAt": _utc_now(), "confirmationRequired": True,
              "confirmed": False, "expiresWhenPlanChanges": True, "allowsAutomaticReuse": False}
    plan_path = paths.plans_dir / f"{payload['planId']}.json"
    _write_json(plan_path, record)
    return "\n".join([
        "Tor backend start plan",
        f"stage: {TOR_STAGE}",
        f"profile: {profile_id}",
        f"backend: {backend}",
        f"plan id: {payload['planId']}",
        f"plan hash: {plan_hash}",
        f"binary: {resolved or 'not found'} ({source})",
        f"binary exists/executable: {'yes' if exists else 'no'}",
        f"local socks: {('unix:' + socks_unix) if socks_unix else f'socks5://{DEFAULT_TOR_SOCKS_HOST}:{socks_port}'} ({listen})",
        f"generated config: {config_path}",
        f"plan file: {plan_path}",
        "C Tor package management: system/pacman only" if backend == "c-tor" else "Arti backend: separate managed executable",
        f"bridges: {len(bridges)}" + (f" ({', '.join(bridge_info['transports']) or 'обычные'})" if bridges else ""),
        "bridge requests to Moat: no",
        "requires owner confirmation: yes",
        "requires sudo: no",
        "starts now: no",
    ])


def _load_confirmed_plan(paths: TorBackendPaths, profile_id: str, backend: str, plan_id: str) -> dict[str, Any]:
    expected = _plan_id(profile_id, backend)
    if plan_id != expected:
        raise ValueError(f"Нужен confirmed plan id: {expected}")
    plan_path = paths.plans_dir / f"{plan_id}.json"
    confirm_path = paths.confirmations_dir / f"{plan_id}.confirmation.json"
    if not plan_path.exists() or not confirm_path.exists():
        raise ValueError("Tor backend plan не подтверждён через --runtime-confirm")
    plan = _read_json(plan_path)
    confirmation = _read_json(confirm_path)
    payload = {k: v for k, v in plan.items() if k not in {"planHash", "preparedAt", "confirmationRequired", "confirmed", "expiresWhenPlanChanges", "allowsAutomaticReuse", "confirmationId", "confirmedAt"}}
    if plan_payload_hash(payload) != str(plan.get("planHash")):
        raise ValueError("Tor backend plan hash изменён")
    if str(confirmation.get("planHash")) != str(plan.get("planHash")):
        raise ValueError("Tor backend confirmation относится к другому plan hash")
    return plan


def tor_backend_start_to_text(*, profile_id: str = "default", backend: str = DEFAULT_TOR_BACKEND,
                              confirm_plan_id: str = "", root: Path | None = None) -> str:
    paths = ensure_tor_backend_store(root)
    plan = _load_confirmed_plan(paths, profile_id, backend, confirm_plan_id)
    binary = str(plan.get("binary", ""))
    if not binary or not Path(binary).is_file() or not os.access(binary, os.X_OK):
        raise ValueError("Tor backend binary отсутствует или не исполняемый")
    socks = dict(plan["localSocks"])
    host, port = str(socks["host"]), int(socks["port"])
    socks_unix = str(socks.get("unix") or "")
    bridge_info = dict(plan.get("bridges") or {})
    bridges: tuple[BridgeLine, ...] = ()
    plugins: tuple[tuple[tuple[str, ...], str], ...] = ()
    if bridge_info.get("enabled"):
        bridges = load_bridges(paths.tor_root)
        if bridges_digest(bridges) != bridge_info.get("sha256"):
            raise ValueError("Список мостов изменился после плана: подготовьте план Tor заново")
        plugins = tuple((tuple(items), str(program)) for items, program in bridge_info.get("plugins", ()))
    if socks_unix:
        _prepare_unix_socket(Path(socks_unix))
    config_path = paths.root / str(plan["generatedConfigPath"])
    config_text = _render_config(paths, backend, host=host, port=port, bridges=bridges, plugins=plugins, socks_unix=socks_unix)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_text, encoding="utf-8")
    try:
        config_path.chmod(0o600)
    except OSError:
        pass
    argv = _argv(binary, backend, config_path)
    stdout_path = paths.logs_dir / f"{profile_id}.{backend}.stdout.log"
    stderr_path = paths.logs_dir / f"{profile_id}.{backend}.stderr.log"
    with stdout_path.open("ab") as out, stderr_path.open("ab") as err:
        process = subprocess.Popen(argv, cwd=str(paths.root), stdout=out, stderr=err, start_new_session=True)
    time.sleep(0.5)
    running = process.poll() is None
    session = {
        "schemaVersion": TOR_SCHEMA_VERSION, "stage": TOR_STAGE, "marker": TOR_MARKER,
        "profileId": profile_id, "planId": confirm_plan_id, "planHash": plan["planHash"],
        "providerKind": "tor", "torBackend": backend,
        "coreBinary": binary, "coreKind": backend, "argv": list(argv), "pid": process.pid,
        "startedAt": _utc_now(), "socksHost": host, "socksPort": port, "socksUnix": socks_unix,
        "bridgeCount": len(bridges),
        "configPath": str(config_path), "stdoutLog": str(stdout_path), "stderrLog": str(stderr_path),
        "runningAfterGrace": running, "state": "running" if running else "failed",
    }
    _write_json(_tor_session(paths, profile_id), session, secret=True)
    if not socks_unix:  # приложения через SOCKS умеют только TCP-порт
        _write_json(_shared_tunnel_session(paths, profile_id), session, secret=True)
    return "\n".join([
        f"Tor backend start: {'started' if running else 'failed'}",
        f"profile: {profile_id}", f"backend: {backend}", f"pid: {process.pid}",
        f"local socks: {('unix:' + socks_unix) if socks_unix else f'socks5://{host}:{port}'}", f"config: {config_path}",
        f"stdout: {stdout_path}", f"stderr: {stderr_path}",
        f"shared SOCKS route session updated: {'no (unix socket)' if socks_unix else 'yes'}",
        "requires sudo: no", "mutates firewall/services: no",
    ])


def tor_backend_status_to_text(*, profile_id: str = "default", root: Path | None = None) -> str:
    paths = ensure_tor_backend_store(root)
    session_path = _tor_session(paths, profile_id)
    if not session_path.exists():
        return "\n".join(["Tor backend status", f"profile: {profile_id}", "state: not-started", "read-only: yes"])
    session = _read_json(session_path)
    pid = int(session.get("pid", 0) or 0)
    running = str(session.get("state")) == "running" and _pid_running(pid)
    return "\n".join([
        "Tor backend status", f"stage: {TOR_STAGE}", f"profile: {profile_id}",
        f"backend: {session.get('torBackend', 'unknown')}", f"state: {'running' if running else session.get('state', 'stale')}",
        f"pid: {pid or 'нет'}",
        "local socks: " + (f"unix:{session['socksUnix']}" if session.get("socksUnix") else f"socks5://{session.get('socksHost')}:{session.get('socksPort')}"),
        f"config: {session.get('configPath')}", f"stdout: {session.get('stdoutLog')}", f"stderr: {session.get('stderrLog')}",
        "read-only: yes",
    ])


@dataclass(frozen=True)
class TorSettings:
    """Выбор владельца на странице Tor; хранится в .zap2/tor/settings.json."""

    backend: str = DEFAULT_TOR_BACKEND
    binary: str = ""
    listen: str = "random"
    port: int = DEFAULT_TOR_SOCKS_PORT
    use_bridges: bool = False
    vless_via_tor: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"schemaVersion": TOR_SCHEMA_VERSION, "backend": self.backend, "binary": self.binary, "listen": self.listen,
                "port": self.port, "useBridges": self.use_bridges, "vlessViaTor": self.vless_via_tor}


def _settings_path(paths: TorBackendPaths) -> Path:
    return paths.tor_root / "settings.json"


def load_tor_settings(root: Path | None = None) -> TorSettings:
    paths = tor_backend_paths(root)
    try:
        data = _read_json(_settings_path(paths))
    except (OSError, ValueError):
        return TorSettings()
    backend = str(data.get("backend") or DEFAULT_TOR_BACKEND)
    listen = str(data.get("listen") or "random")
    return TorSettings(
        backend=backend if backend in SUPPORTED_TOR_BACKENDS else DEFAULT_TOR_BACKEND,
        binary=str(data.get("binary") or ""),
        listen=listen if listen in LISTEN_MODES else "random",
        port=int(data.get("port") or DEFAULT_TOR_SOCKS_PORT),
        use_bridges=bool(data.get("useBridges")),
        vless_via_tor=bool(data.get("vlessViaTor")),
    )


def save_tor_settings(settings: TorSettings, root: Path | None = None) -> Path:
    paths = ensure_tor_backend_store(root)
    path = _settings_path(paths)
    _write_json(path, settings.to_dict())
    return path


def tor_upstream_for_vless(root: Path | None = None, profile_id: str = "default") -> tuple[str, int] | None:
    """SOCKS Tor для режима «Tor перед VLESS»: только если режим включён и Tor слушает TCP-порт."""

    if not load_tor_settings(root).vless_via_tor:
        return None
    paths = tor_backend_paths(root)
    session_path = _tor_session(paths, profile_id)
    if not session_path.exists():
        raise ValueError("Режим «Tor перед VLESS» включён, но Tor не запущен: запустите его на странице Tor")
    session = _read_json(session_path)
    if session.get("socksUnix"):
        raise ValueError("Режим «Tor перед VLESS» требует, чтобы Tor слушал TCP-порт, а не unix-сокет")
    if str(session.get("state")) != "running" or not _pid_running(int(session.get("pid", 0) or 0)):
        raise ValueError("Режим «Tor перед VLESS» включён, но Tor не запущен: запустите его на странице Tor")
    return str(session.get("socksHost") or DEFAULT_TOR_SOCKS_HOST), int(session.get("socksPort") or 0)


@dataclass(frozen=True)
class TorBootstrap:
    state: str  # not-started | starting | ready | failed | stopped
    percent: int | None
    summary: str
    socks: str = ""


def _log_tail(path: Path, limit: int = 64 * 1024) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def parse_bootstrap(text: str) -> tuple[int | None, str]:
    """Последний процент загрузки C Tor или признак готовности Arti."""

    percent: int | None = None
    summary = ""
    for line in text.splitlines():
        match = _BOOTSTRAP.search(line)
        if match:
            percent = min(100, int(match.group(1)))
            summary = (match.group(3) or match.group(2) or "").strip()
        elif "Sufficiently bootstrapped" in line or "system SOCKS now functional" in line:
            percent, summary = 100, "Arti готов: SOCKS работает"
        elif "Bootstrapping" in line and percent is None:
            percent, summary = 0, "Arti подключается к сети Tor"
    return percent, summary


def tor_bootstrap_status(*, profile_id: str = "default", root: Path | None = None) -> TorBootstrap:
    paths = ensure_tor_backend_store(root)
    session_path = _tor_session(paths, profile_id)
    if not session_path.exists():
        return TorBootstrap("not-started", None, "Tor не запущен")
    session = _read_json(session_path)
    socks = ("unix:" + str(session["socksUnix"])) if session.get("socksUnix") else f"socks5h://{session.get('socksHost')}:{session.get('socksPort')}"
    if session.get("state") == "stopped":
        return TorBootstrap("stopped", None, "Tor остановлен", socks)
    running = str(session.get("state")) == "running" and _pid_running(int(session.get("pid", 0) or 0))
    text = _log_tail(Path(str(session.get("stdoutLog", "")))) + "\n" + _log_tail(Path(str(session.get("stderrLog", ""))))
    percent, summary = parse_bootstrap(text)
    if not running:
        problem = next((line.strip() for line in reversed(text.splitlines()) if "[err]" in line or "[warn]" in line or "ERROR" in line), "")
        return TorBootstrap("failed", percent, problem or "процесс Tor завершился — подробности в журнале", socks)
    if percent == 100:
        return TorBootstrap("ready", 100, summary or "готов", socks)
    return TorBootstrap("starting", percent, summary or "запускается", socks)


def tor_backend_stop_to_text(*, profile_id: str = "default", root: Path | None = None) -> str:
    paths = ensure_tor_backend_store(root)
    session_path = _tor_session(paths, profile_id)
    if not session_path.exists():
        return "\n".join(["Tor backend stop: not-started", f"profile: {profile_id}"])
    session = _read_json(session_path)
    pid = int(session.get("pid", 0) or 0)
    if _pid_running(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.time() + 3.0
        while time.time() < deadline and _pid_running(pid):
            time.sleep(0.05)
        if _pid_running(pid):
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    session["state"] = "stopped"
    session["stoppedAt"] = _utc_now()
    _write_json(session_path, session, secret=True)
    shared = _shared_tunnel_session(paths, profile_id)
    if shared.exists():
        current = _read_json(shared)
        if int(current.get("pid", 0) or 0) == pid and current.get("providerKind") == "tor":
            current["state"] = "stopped"
            current["stoppedAt"] = session["stoppedAt"]
            _write_json(shared, current, secret=True)
    return "\n".join(["Tor backend stop: stopped", f"profile: {profile_id}", f"backend: {session.get('torBackend')}", f"pid: {pid}"])
