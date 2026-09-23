"""Guarded runtime session runner для процесса nfqws2.

Stage 11 исполняет только lifecycle локального процесса, привязанного к уже
подготовленному и подтверждённому runtime start-plan. Модуль не применяет
firewall/routing rules, не управляет systemd/service manager, не делает
bootstrap и не вызывает upstream installer scripts.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import shlex
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from .runtime_plan_generator import GeneratedRuntimePlan, create_runtime_plan
from .runtime_queue import resolve_runtime_queue, find_nfqueue_processes, ensure_nfqueue_available
from .core_provenance import verify_core_bundle
from .strategy_file_inputs import split_strategy_file_arg, strategy_file_dependency_error_text
from .runtime_state import (
    append_runtime_event,
    ensure_runtime_store,
    generated_runtime_plan_to_payload,
    plan_payload_hash,
    runtime_store_paths,
    atomic_write_json,
)
from ..project_paths import discover_layout

SESSION_STAGE = "v0.3-beta_stage_11"
SESSION_SCHEMA_VERSION = 2
SESSION_MARKER = "zap2-runtime-session-v1"
PROCESS_START_GRACE_SECONDS = 0.25
PROCESS_STOP_TIMEOUT_SECONDS = 5.0
PUBLIC_SESSION_INPUTS_BASE = "zap2-runtime-inputs"
DEFAULT_DESYNC_MARK = "0x40000000"


@dataclass(frozen=True)
class RuntimeDropIdentity:
    """UID/GID, к которым nfqws2 должен сбросить root после открытия NFQUEUE.

    При запуске через sudo upstream nfqws2 по умолчанию сбрасывает привилегии
    в UID/GID 2147483647. Такой synthetic uid часто не может читать hostlist
    внутри пользовательского workspace. Поэтому runner явно передаёт --uid от
    владельца sudo-сессии или владельца workspace.
    """

    uid: int
    gid: int
    source: str

    @property
    def option(self) -> str:
        return f"--uid={self.uid}:{self.gid}"


SessionState = Literal["not-started", "running", "stopped", "stale", "failed", "unknown", "migration-required"]


@dataclass(frozen=True)
class RuntimeSessionConfig:
    """Сконструированная конфигурация запуска nfqws2 как runtime session."""

    profile_id: str
    plan_id: str
    plan_hash: str
    root_path: Path
    binary_path: Path
    cwd: Path
    argv: tuple[str, ...]
    args_path: Path
    session_inputs_dir: Path
    public_session_inputs_dir: Path | None
    hostlist_input_paths: tuple[Path, ...]
    strategy_file_input_paths: tuple[Path, ...]
    lua_input_paths: tuple[Path, ...]
    blob_input_paths: tuple[Path, ...]
    pidfile_path: Path
    stdout_log_path: Path
    stderr_log_path: Path
    debug_log_path: Path
    session_path: Path
    runtime_args: tuple[str, ...]
    drop_identity: RuntimeDropIdentity | None = None
    nfqueue_num: int = 0
    nfqueue_source: str = ""

    def to_text(self) -> str:
        return "\n".join(
            [
                f"Runtime session config для profile: {self.profile_id}",
                f"plan id: {self.plan_id}",
                f"plan hash: {self.plan_hash}",
                f"root: {self.root_path}",
                f"binary: {self.binary_path}",
                f"cwd: {self.cwd}",
                f"argv: {' '.join(self.argv)}",
                "runtime args:",
                *(f"  - {item}" for item in self.runtime_args),
                f"args file: {self.args_path}",
                f"session inputs dir: {self.session_inputs_dir}",
                f"public session inputs dir: {self.public_session_inputs_dir if self.public_session_inputs_dir else 'not used'}",
                "runtime hostlist inputs:",
                *(f"  - {item}" for item in self.hostlist_input_paths),
                "runtime strategy list/ipset inputs:",
                *(f"  - {item}" for item in self.strategy_file_input_paths),
                "runtime lua inputs:",
                *(f"  - {item}" for item in self.lua_input_paths),
                "runtime blob inputs:",
                *(f"  - {item}" for item in self.blob_input_paths),
                f"pidfile: {self.pidfile_path}",
                f"stdout log: {self.stdout_log_path}",
                f"stderr log: {self.stderr_log_path}",
                f"debug log: {self.debug_log_path}",
                f"debug enabled: {'yes' if _runtime_debug_enabled() else 'no'}",
                f"session file: {self.session_path}",
                f"drop identity: {self.drop_identity.uid}:{self.drop_identity.gid} ({self.drop_identity.source})" if self.drop_identity else "drop identity: upstream default",
                f"nfqueue: {self.nfqueue_num} ({self.nfqueue_source})",
                "requires confirmed start plan: yes",
                "mutates firewall/services: no",
                "service mode: no",
            ]
        )


@dataclass(frozen=True)
class RuntimeSessionResult:
    """CLI-friendly результат session action."""

    action: str
    state: SessionState
    profile_id: str
    message: str
    session_path: Path
    pid: int | None = None
    plan_id: str | None = None
    plan_hash: str | None = None
    log_path: Path | None = None

    def to_text(self) -> str:
        lines = [
            f"Runtime session {self.action}: {self.state}",
            f"profile: {self.profile_id}",
            f"message: {self.message}",
        ]
        if self.pid is not None:
            lines.append(f"pid: {self.pid}")
        if self.plan_id:
            lines.append(f"plan id: {self.plan_id}")
        if self.plan_hash:
            lines.append(f"plan hash: {self.plan_hash}")
        lines.append(f"session file: {self.session_path}")
        if self.log_path is not None:
            lines.append(f"runtime log: {self.log_path}")
        lines.extend(
            [
                "owned marker required: yes",
                "stops only recorded pid: yes",
                "mutates firewall/services: no",
                "service mode: no",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class RuntimeSessionLaunchReceipt:
    """Receipt returned by a bounded external launcher.

    P02 keeps lifecycle/state in the unprivileged application while the small
    root-owned executor is responsible only for the privileged spawn.  The
    executor returns the exact staged executable path and process identity so
    later status/stop logic can keep its existing PID-reuse protections.
    """

    pid: int
    runtime_executable_path: Path
    stdout_log_path: Path
    stderr_log_path: Path
    debug_log_path: Path | None
    helper_sha256: str
    helper_version: str
    helper_ruid: int | None
    helper_euid: int | None
    action_id: str
    plan_hash: str
    request_hash: str = ""
    process_identity: dict[str, Any] | None = None


@dataclass(frozen=True)
class RuntimeSessionStatus:
    """Read-only статус session state."""

    state: SessionState
    profile_id: str
    session_path: Path
    pid: int | None = None
    plan_id: str | None = None
    plan_hash: str | None = None
    binary_path: str | None = None
    message: str = ""

    def to_text(self) -> str:
        lines = [
            f"Runtime session status: {self.state}",
            f"profile: {self.profile_id}",
            f"session file: {self.session_path}",
        ]
        if self.pid is not None:
            lines.append(f"pid: {self.pid}")
        if self.plan_id:
            lines.append(f"plan id: {self.plan_id}")
        if self.plan_hash:
            lines.append(f"plan hash: {self.plan_hash}")
        if self.binary_path:
            lines.append(f"binary: {self.binary_path}")
        if self.message:
            lines.append(f"message: {self.message}")
        lines.extend(
            [
                "owned marker required: yes",
                "mutates firewall/services: no",
                "service mode: no",
            ]
        )
        return "\n".join(lines)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_json(path, data)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _session_path(root: Path, profile_id: str) -> Path:
    return runtime_store_paths(root).sessions_dir / f"{profile_id}.session.json"


def _event(event_type: str, level: str, plan_id: str, plan_hash: str, message: str, metadata: dict[str, Any] | None = None, executes_now: bool = True) -> dict[str, Any]:
    return {
        "schemaVersion": SESSION_SCHEMA_VERSION,
        "stage": SESSION_STAGE,
        "eventId": f"{event_type}-{plan_id}-{plan_hash[:12]}",
        "eventType": event_type,
        "level": level,
        "planId": plan_id,
        "planHash": plan_hash,
        "message": message,
        "createdAt": _utc_now(),
        "metadata": metadata or {},
        "executesNow": executes_now,
        "mutatesFirewallOrServicesNow": False,
        "managesServiceNow": False,
    }


def _current_start_plan_and_hash(root: Path, profile_id: str) -> tuple[GeneratedRuntimePlan, str]:
    plan = create_runtime_plan(root, action="start", profile_id=profile_id)
    payload = generated_runtime_plan_to_payload(plan, root)
    return plan, plan_payload_hash(payload)


def _load_valid_confirmation(root: Path, profile_id: str) -> tuple[GeneratedRuntimePlan, str, dict[str, Any]]:
    """Проверяет, что start plan подготовлен и подтверждён для текущего hash."""

    paths = ensure_runtime_store(root)
    plan, current_hash = _current_start_plan_and_hash(paths.root, profile_id)
    plan_path = paths.plans_dir / f"{plan.plan_id}.json"
    confirmation_path = paths.confirmations_dir / f"{plan.plan_id}.confirmation.json"
    if not plan_path.exists():
        raise ValueError(
            f"Prepared start-plan не найден: {plan.plan_id}. Сначала выполните --runtime-prepare start --profile {profile_id}."
        )
    if not confirmation_path.exists():
        raise ValueError(
            f"Confirmation не найден для {plan.plan_id}. Сначала выполните --runtime-confirm {plan.plan_id}."
        )
    prepared = _read_json(plan_path)
    confirmation = _read_json(confirmation_path)
    if prepared.get("planHash") != current_hash:
        raise ValueError("Prepared start-plan устарел: текущий planHash не совпадает с сохранённым")
    if prepared.get("confirmed") is not True:
        raise ValueError("Prepared start-plan ещё не подтверждён owner confirmation")
    if confirmation.get("planHash") != current_hash or confirmation.get("confirmedByOwner") is not True:
        raise ValueError("Confirmation не соответствует текущему start-plan hash")
    return plan, current_hash, confirmation


def _binary_is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _parse_positive_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value, 10)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _running_as_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    return False if geteuid is None else geteuid() == 0


def _drop_identity_mode() -> str:
    """Return GUI/owner-requested drop identity mode.

    В Stage 7 GUI/pkexec временно форсировал ``--uid=0:0`` через
    ``ZAP2_RUNTIME_DROP_IDENTITY=polkit-root``. После того как hostlist и Lua
    inputs были вынесены в public runtime directory, этот режим стал вредным:
    upstream ``nfqws2`` доходил до Lua, но затем падал на
    ``nfq_create_queue(): Operation not permitted``. Для GUI/pkexec теперь
    нужен upstream default drop identity, а не принудительный ``--uid=0:0``.
    """

    return os.environ.get("ZAP2_RUNTIME_DROP_IDENTITY", "").strip().lower()


def _upstream_default_identity_requested() -> bool:
    value = _drop_identity_mode()
    return value in {"upstream-default", "upstream", "default", "synthetic", "auto"}


def _preserve_root_identity_requested() -> bool:
    """Return whether legacy GUI bridge asked nfqws2 to keep root uid/gid.

    This mode is kept only for compatibility/diagnostics. The normal GUI/pkexec
    path no longer uses it because public runtime inputs make explicit root
    preservation unnecessary and it can break NFQUEUE creation on some systems.
    """

    value = _drop_identity_mode()
    return value in {"root", "preserve-root", "keep-root", "polkit-root"}


def _detect_drop_identity(root: Path) -> RuntimeDropIdentity | None:
    """Возвращает явную --uid identity для root запуска.

    Нерутовый запуск оставляет upstream default untouched. Обычный sudo/root
    запуск получает uid/gid владельца sudo-сессии или workspace, чтобы nfqws2
    после privilege drop мог читать hostlist. GUI/pkexec start после Stage 11
    тоже оставляет upstream default untouched: hostlist/Lua уже доступны из
    public runtime directory, а принудительный ``--uid=0:0`` может ломать
    ``nfq_create_queue``.
    """

    if not _running_as_root():
        return None

    if _upstream_default_identity_requested():
        return None

    if _preserve_root_identity_requested():
        return RuntimeDropIdentity(uid=0, gid=0, source="legacy-polkit-root-preserve")

    sudo_uid = _parse_positive_int(os.environ.get("SUDO_UID"))
    sudo_gid = _parse_positive_int(os.environ.get("SUDO_GID"))
    if sudo_uid is not None and sudo_gid is not None:
        return RuntimeDropIdentity(uid=sudo_uid, gid=sudo_gid, source="sudo-owner")

    try:
        stat_result = root.stat()
    except OSError:
        return RuntimeDropIdentity(uid=0, gid=0, source="root-fallback")
    if stat_result.st_uid != 0 or stat_result.st_gid != 0:
        return RuntimeDropIdentity(uid=stat_result.st_uid, gid=stat_result.st_gid, source="workspace-owner")
    return RuntimeDropIdentity(uid=0, gid=0, source="root-fallback")


def _runtime_debug_enabled() -> bool:
    value = os.environ.get("ZAP2_RUNTIME_DEBUG", "").strip().lower()
    return value in {"1", "true", "yes", "on", "debug"}


def _runtime_input_path_for_nfqws(path: Path) -> str:
    """Return a hostlist path suitable for nfqws2 after dropcaps.

    Stage 8 передавал относительный путь внутри `.zap2`. Это оказалось
    недостаточно для GUI/pkexec: после `dropcaps()` nfqws2 может потерять право
    обходить приватные родительские директории `/home/<owner>/...`. Поэтому для
    hostlist используется абсолютный путь к public runtime copy под `/tmp`.
    """

    return str(path.resolve())


def _safe_chmod(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except PermissionError:
        pass


def _ensure_public_dir(path: Path) -> Path:
    """Create a non-symlink public directory readable after nfqws2 dropcaps."""

    if path.exists() and path.is_symlink():
        raise ValueError(f"public runtime input path не должен быть symlink: {path}")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError(f"public runtime input path не является директорией: {path}")
    _safe_chmod(path, 0o755)
    return path


def _public_session_inputs_base() -> Path:
    """Return the writable public runtime-input base directory.

    If ZAP2_PUBLIC_RUNTIME_INPUTS_DIR is supplied by tests or an owner, keep the
    historical layout `<base>/zap2-runtime-inputs`.  Otherwise use a uid-scoped
    directory under the system temp dir so one root-owned stale directory cannot
    break unprivileged devctl/pytest runs for another user.
    """

    configured = os.environ.get("ZAP2_PUBLIC_RUNTIME_INPUTS_DIR")
    if configured:
        return Path(configured) / PUBLIC_SESSION_INPUTS_BASE
    return Path(tempfile.gettempdir()) / f"{PUBLIC_SESSION_INPUTS_BASE}-{os.getuid()}"


def _public_session_inputs_dir(paths_root: Path, profile_id: str, plan_id: str, plan_hash: str) -> Path:
    """Return deterministic public input dir under /tmp for one plan hash.

    Hostlist не является секретом в текущем single-owner workflow, зато путь
    должен быть доступен процессу без CAP_DAC_OVERRIDE после `dropcaps()`.
    """

    digest = hashlib.sha256(f"{paths_root.resolve()}|{profile_id}|{plan_id}|{plan_hash}".encode("utf-8")).hexdigest()[:16]
    base = _public_session_inputs_base()
    _ensure_public_dir(base)
    return _ensure_public_dir(base / f"{profile_id}-{digest}")


def _make_runtime_input_accessible(path: Path) -> None:
    """Make a runtime input readable/searchable after nfqws2 drops caps."""

    for directory in (path.parent.parent, path.parent):
        if directory.exists():
            _safe_chmod(directory, 0o755)
    _safe_chmod(path, 0o644)


def _prepare_runtime_hostlist_inputs(paths_root: Path, plan: GeneratedRuntimePlan, profile_id: str, plan_hash: str, inputs_dir: Path | None = None) -> tuple[Path, ...]:
    """Copy profile hostlists to public runtime session inputs.

    Source hostlists remain owner-maintained project files. Runtime uses a
    per-plan public copy so privileged GUI start does not depend on source-file
    ownership, restrictive umask, or `/home` traversal after `dropcaps()`.
    """

    if not plan.hostlists:
        return ()
    inputs_dir = inputs_dir or _public_session_inputs_dir(paths_root, profile_id, plan.plan_id, plan_hash)
    prepared: list[Path] = []
    for index, hostlist in enumerate(plan.hostlists):
        source = (paths_root / hostlist.path).resolve()
        if not source.is_file():
            raise ValueError(f"hostlist source отсутствует: {source}")
        suffix = source.suffix or ".hosts"
        target_name = f"{profile_id}.hostlist-{index}{suffix}"
        target = inputs_dir / target_name
        tmp = target.with_suffix(target.suffix + ".tmp")
        shutil.copyfile(source, tmp)
        _safe_chmod(tmp, 0o644)
        os.replace(tmp, target)
        _make_runtime_input_accessible(target)
        prepared.append(target)
    return tuple(prepared)


def _resolve_project_file_reference(paths_root: Path, path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = paths_root / path
    return path.resolve()


def _prepare_runtime_lua_inputs(paths_root: Path, runtime_args: tuple[str, ...], inputs_dir: Path) -> tuple[tuple[str, ...], tuple[Path, ...]]:
    """Copy Lua init files to public runtime inputs and rewrite args.

    nfqws2 intentionally drops privileges before running Lua. When it is
    started through GUI/pkexec from a private workspace, paths such as
    `core/zapret2/lua/zapret-lib.lua` can become inaccessible after dropcaps.
    We therefore keep project sources untouched and run nfqws2 against public
    per-plan copies with 0644 file and 0755 directory modes.
    """

    rewritten: list[str] = []
    copied: list[Path] = []
    lua_dir = inputs_dir / "lua"
    seen: dict[Path, Path] = {}

    for arg in runtime_args:
        if not arg.startswith("--lua-init=@"):
            rewritten.append(arg)
            continue

        source_text = arg.split("=@", 1)[1]
        source = _resolve_project_file_reference(paths_root, source_text)
        if not source.is_file():
            raise ValueError(f"lua init source отсутствует: {source}")
        if source not in seen:
            _ensure_public_dir(lua_dir)
            target = lua_dir / source.name
            tmp = target.with_suffix(target.suffix + ".tmp")
            shutil.copyfile(source, tmp)
            _safe_chmod(tmp, 0o644)
            os.replace(tmp, target)
            _make_runtime_input_accessible(target)
            seen[source] = target
            copied.append(target)
        rewritten.append(f"--lua-init=@{seen[source].resolve()}")

    return tuple(rewritten), tuple(copied)





def _prepare_runtime_strategy_file_inputs(
    paths_root: Path,
    runtime_args: tuple[str, ...],
    inputs_dir: Path,
) -> tuple[tuple[str, ...], tuple[Path, ...]]:
    """Copy per-strategy hostlist/ipset files to public runtime inputs.

    Full TXT presets may embed file-backed filters directly in strategy args.
    They are distinct from workspace profile hostlists and therefore must be
    rewritten before nfqws2 drops privileges.
    """

    error_text = strategy_file_dependency_error_text(paths_root, runtime_args)
    if error_text:
        raise ValueError(error_text)

    rewritten: list[str] = []
    copied: list[Path] = []
    list_dir = inputs_dir / "strategy-files"
    seen: dict[Path, Path] = {}
    occupied: dict[str, Path] = {}

    for arg in runtime_args:
        parsed = split_strategy_file_arg(arg)
        if parsed is None:
            rewritten.append(arg)
            continue
        option, value = parsed
        source = _resolve_project_file_reference(paths_root, value.lstrip("@"))
        if source not in seen:
            _ensure_public_dir(list_dir)
            target_name = source.name
            if target_name in occupied and occupied[target_name] != source:
                digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:8]
                target_name = f"{source.stem}-{digest}{source.suffix}"
            target = list_dir / target_name
            tmp = target.with_suffix(target.suffix + ".tmp")
            shutil.copyfile(source, tmp)
            _safe_chmod(tmp, 0o644)
            os.replace(tmp, target)
            _make_runtime_input_accessible(target)
            seen[source] = target
            occupied[target_name] = source
            copied.append(target)
        rewritten.append(f"{option}={seen[source].resolve()}")

    return tuple(rewritten), tuple(copied)


def _prepare_runtime_blob_inputs(paths_root: Path, runtime_args: tuple[str, ...], inputs_dir: Path) -> tuple[tuple[str, ...], tuple[Path, ...]]:
    """Copy --blob=@file inputs to public runtime inputs and rewrite args.

    Windows-derived winws2 presets often load custom ClientHello/QUIC samples via
    `--blob=name:@file`.  nfqws2 reads those files after argument expansion and
    may already have dropped privileges, so project-local paths under a private
    workspace can fail for the same reason as Lua/hostlist files.  Hex blobs are
    left untouched.
    """

    rewritten: list[str] = []
    copied: list[Path] = []
    blob_dir = inputs_dir / "blob"
    seen: dict[Path, Path] = {}
    occupied: dict[str, Path] = {}

    for arg in runtime_args:
        if not arg.startswith("--blob=") or "@" not in arg:
            rewritten.append(arg)
            continue

        prefix, source_text = arg.split("@", 1)
        if not source_text:
            rewritten.append(arg)
            continue

        source = _resolve_project_file_reference(paths_root, source_text)
        if not source.is_file():
            raise ValueError(f"blob source отсутствует: {source}")
        if source not in seen:
            _ensure_public_dir(blob_dir)
            target_name = source.name
            if target_name in occupied and occupied[target_name] != source:
                digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:8]
                target_name = f"{source.stem}-{digest}{source.suffix}"
            target = blob_dir / target_name
            tmp = target.with_suffix(target.suffix + ".tmp")
            shutil.copyfile(source, tmp)
            _safe_chmod(tmp, 0o644)
            os.replace(tmp, target)
            _make_runtime_input_accessible(target)
            seen[source] = target
            occupied[target_name] = source
            copied.append(target)
        rewritten.append(f"{prefix}@{seen[source].resolve()}")

    return tuple(rewritten), tuple(copied)

def _cleanup_public_session_inputs(paths: tuple[Path, ...]) -> None:
    """Best-effort cleanup for public runtime hostlist copies."""

    seen_dirs: set[Path] = set()
    for item in paths:
        try:
            path = Path(item)
            if path.exists() and path.is_file():
                path.unlink()
            seen_dirs.add(path.parent)
        except OSError:
            continue
    for directory in seen_dirs:
        try:
            directory.rmdir()
        except OSError:
            pass


def _runtime_args_for_plan(
    paths_root: Path,
    plan: GeneratedRuntimePlan,
    drop_identity: RuntimeDropIdentity | None,
    pidfile_path: Path,
    debug_log_path: Path,
    hostlist_input_paths: tuple[Path, ...],
    strategy_runtime_args: tuple[str, ...],
    nfqueue_num: int,
) -> tuple[str, ...]:
    args: list[str] = [
        f"--qnum={nfqueue_num}",
        f"--pidfile={pidfile_path}",
        f"--fwmark={DEFAULT_DESYNC_MARK}",
    ]
    if _runtime_debug_enabled():
        args.append(f"--debug=@{debug_log_path}")
    args.extend(strategy_runtime_args)
    if drop_identity is not None:
        args.append(drop_identity.option)
    for hostlist_path in hostlist_input_paths:
        args.append(f"--hostlist={_runtime_input_path_for_nfqws(hostlist_path)}")
    return tuple(args)


def _tail_text(path: Path, max_chars: int = 1200) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:].strip()


def build_runtime_session_config(
    root: Path | None = None,
    profile_id: str = "default",
    *,
    prepare_public_inputs: bool = True,
) -> RuntimeSessionConfig:
    """Создаёт session config из default profile и confirmed start plan."""

    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    plan, plan_hash, _confirmation = _load_valid_confirmation(paths.root, profile_id)
    binary_path = (paths.root / plan.binary_relative_path).resolve()
    if not _binary_is_executable(binary_path):
        raise ValueError(
            "nfqws2 binary отсутствует или не исполняемый: "
            f"{binary_path}. Сначала соберите build target {plan.profile.build_target}."
        )
    provenance = verify_core_bundle(paths.root, binary_path)
    if provenance.hard_error:
        raise ValueError(f"core provenance gate: {provenance.message}")

    session_path = paths.sessions_dir / f"{profile_id}.session.json"
    args_path = paths.sessions_dir / f"{profile_id}.nfqws2.args"
    pidfile_path = paths.sessions_dir / f"{profile_id}.nfqws2.pid"
    stdout_log_path = paths.logs_dir / f"{profile_id}.nfqws2.stdout.log"
    stderr_log_path = paths.logs_dir / f"{profile_id}.nfqws2.stderr.log"
    debug_log_path = paths.logs_dir / f"{profile_id}.nfqws2.debug.log"
    drop_identity = _detect_drop_identity(paths.root)
    public_session_inputs_dir = _public_session_inputs_dir(paths.root, profile_id, plan.plan_id, plan_hash) if prepare_public_inputs else None
    strategy_dependency_error = strategy_file_dependency_error_text(paths.root, tuple(plan.strategy.runtime_args))
    if strategy_dependency_error:
        raise ValueError(strategy_dependency_error)
    if prepare_public_inputs:
        assert public_session_inputs_dir is not None
        hostlist_input_paths = _prepare_runtime_hostlist_inputs(paths.root, plan, profile_id, plan_hash, public_session_inputs_dir)
        strategy_runtime_args, strategy_file_input_paths = _prepare_runtime_strategy_file_inputs(
            paths.root, tuple(plan.strategy.runtime_args), public_session_inputs_dir
        )
        strategy_runtime_args, lua_input_paths = _prepare_runtime_lua_inputs(paths.root, strategy_runtime_args, public_session_inputs_dir)
        strategy_runtime_args, blob_input_paths = _prepare_runtime_blob_inputs(paths.root, strategy_runtime_args, public_session_inputs_dir)
        if not hostlist_input_paths and not strategy_file_input_paths and not lua_input_paths and not blob_input_paths:
            public_session_inputs_dir = None
    else:
        # Bounded P02 launcher stages the exact plan-bound bytes inside a
        # root-owned /run bundle.  Do not create mutable /tmp copies first.
        hostlist_input_paths = tuple((paths.root / item.path).resolve() for item in plan.hostlists)
        strategy_runtime_args = tuple(plan.strategy.runtime_args)
        strategy_file_input_paths = ()
        lua_input_paths = ()
        blob_input_paths = ()
    queue = resolve_runtime_queue(paths.root, profile_id)
    runtime_args = _runtime_args_for_plan(paths.root, plan, drop_identity, pidfile_path, debug_log_path, hostlist_input_paths, strategy_runtime_args, queue.qnum)

    return RuntimeSessionConfig(
        profile_id=profile_id,
        plan_id=plan.plan_id,
        plan_hash=plan_hash,
        root_path=paths.root,
        binary_path=binary_path,
        cwd=paths.root,
        argv=(str(binary_path), f"@{args_path}"),
        args_path=args_path,
        session_inputs_dir=paths.session_inputs_dir,
        public_session_inputs_dir=public_session_inputs_dir,
        hostlist_input_paths=hostlist_input_paths,
        strategy_file_input_paths=strategy_file_input_paths,
        lua_input_paths=lua_input_paths,
        blob_input_paths=blob_input_paths,
        pidfile_path=pidfile_path,
        stdout_log_path=stdout_log_path,
        stderr_log_path=stderr_log_path,
        debug_log_path=debug_log_path,
        session_path=session_path,
        runtime_args=runtime_args,
        drop_identity=drop_identity,
        nfqueue_num=queue.qnum,
        nfqueue_source=queue.source,
    )


def _quote_nfqws_args_file_arg(arg: str) -> str:
    """Return one shell-safe token for nfqws2 @args files.

    Upstream nfqws2 reads @file content through wordexp(3), not by simply
    splitting one line per argument.  Values such as ``--out-range=<s1`` or
    paths with spaces are therefore shell-sensitive unless quoted.
    """

    if "\x00" in arg or "\n" in arg or "\r" in arg:
        raise ValueError(f"nfqws2 argument cannot contain NUL/newline: {arg!r}")
    return shlex.quote(arg)


def _nfqws_args_file_text(args: tuple[str, ...]) -> str:
    return "\n".join(_quote_nfqws_args_file_arg(arg) for arg in args) + "\n"


def _write_args_file(config: RuntimeSessionConfig) -> None:
    config.args_path.write_text(_nfqws_args_file_text(config.runtime_args), encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _proc_cmdline(pid: int) -> tuple[str, ...] | None:
    proc_cmdline = Path("/proc") / str(pid) / "cmdline"
    try:
        raw = proc_cmdline.read_bytes()
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None
    if not raw:
        return ()
    return tuple(part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part)


def _boot_id() -> str | None:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except (FileNotFoundError, PermissionError, OSError):
        return None
    return value or None


def _proc_starttime(pid: int) -> str | None:
    """Return Linux proc starttime (clock ticks since boot) for PID.

    Field 22 must be parsed after the closing ``)`` because comm can contain
    spaces and parentheses. Missing/denied proc data is intentionally unknown.
    """

    try:
        text = (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None
    close = text.rfind(")")
    if close < 0:
        return None
    fields_after_comm = text[close + 2 :].split()
    # field 3 (state) is index 0 here; field 22 (starttime) is index 19.
    if len(fields_after_comm) <= 19:
        return None
    return fields_after_comm[19]


def _proc_executable(pid: int) -> str | None:
    try:
        return os.path.realpath(os.readlink(Path("/proc") / str(pid) / "exe"))
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None


def _cmdline_digest(cmdline: tuple[str, ...] | None) -> str | None:
    if not cmdline:
        return None
    raw = b"\0".join(part.encode("utf-8", errors="surrogatepass") for part in cmdline)
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _capture_process_identity(pid: int, binary_path: Path) -> dict[str, Any] | None:
    cmdline = _proc_cmdline(pid)
    boot_id = _boot_id()
    starttime = _proc_starttime(pid)
    proc_exe = _proc_executable(pid)
    cmdline_sha = _cmdline_digest(cmdline)
    if not boot_id or not starttime or not proc_exe or not cmdline_sha:
        return None
    return {
        "bootId": boot_id,
        "procStartTime": starttime,
        "procExecutable": proc_exe,
        "cmdlineSha256": cmdline_sha,
        # Diagnostic/provenance only. A binary may legitimately be replaced
        # after start; stop identity therefore does not compare this hash.
        "binarySha256AtStart": _file_sha256(binary_path),
    }


def _path_belongs_to_root(path_value: object, root: Path) -> bool:
    """Return whether an absolute path from saved state belongs to current workspace."""

    if not path_value:
        return True
    try:
        path = Path(str(path_value)).resolve()
        root_resolved = root.resolve()
        path.relative_to(root_resolved)
        return True
    except Exception:
        return False


def _upgrade_legacy_session_identity(record: dict[str, Any], root: Path) -> dict[str, Any] | None:
    """Adopt a schema-1 live session only when every legacy proof still matches.

    runtime-security tightened stop/start safety with exact /proc identity.  A live
    session created by the previous workspace-sync build has no processIdentity,
    which otherwise leaves the queue occupied but impossible to stop.  We only
    upgrade records that prove workspace scope, pidfile ownership, executable and
    the full saved argv against the currently running task.
    """

    if isinstance(record.get("processIdentity"), dict):
        return record
    try:
        pid = int(record.get("pid", 0))
    except (TypeError, ValueError):
        return None
    if pid <= 1 or not _pid_alive(pid):
        return None
    for key in ("binaryPath", "sessionPath", "pidfilePath"):
        if not _path_belongs_to_root(record.get(key), root):
            return None
    pidfile_value = str(record.get("pidfilePath", "") or "")
    if not pidfile_value:
        return None
    try:
        if int(Path(pidfile_value).read_text(encoding="utf-8").strip()) != pid:
            return None
    except (OSError, ValueError):
        return None

    binary_value = str(record.get("binaryPath", "") or "")
    saved_argv = tuple(str(item) for item in record.get("argv", []))
    current_argv = _proc_cmdline(pid)
    current_exe = _proc_executable(pid)
    if not binary_value or not saved_argv or not current_argv or not current_exe:
        return None
    if os.path.realpath(saved_argv[0]) != os.path.realpath(binary_value):
        return None
    if os.path.realpath(current_argv[0]) != os.path.realpath(binary_value):
        return None
    if current_argv[1:] != saved_argv[1:]:
        return None
    if current_exe != os.path.realpath(binary_value):
        return None
    identity = _capture_process_identity(pid, Path(binary_value))
    if not identity:
        return None
    updated = dict(record)
    updated["schemaVersion"] = SESSION_SCHEMA_VERSION
    updated["processIdentity"] = identity
    updated["legacyIdentityUpgradedAt"] = _utc_now()
    updated["legacyIdentityUpgrade"] = "schema-1 exact pidfile/exe/argv match"
    return updated


def _record_matches_process(record: dict[str, Any]) -> bool:
    """Verify that PID is the exact Linux task created for this session.

    Old schema-1 records intentionally fail closed: a numeric PID plus argv
    text is not enough to safely send signals after reboot/PID reuse.
    """

    try:
        pid = int(record.get("pid", 0))
    except (TypeError, ValueError):
        return False
    identity = record.get("processIdentity")
    if pid <= 1 or not isinstance(identity, dict):
        return False
    current_boot = _boot_id()
    current_start = _proc_starttime(pid)
    current_exe = _proc_executable(pid)
    current_cmdline = _cmdline_digest(_proc_cmdline(pid))
    if not all((current_boot, current_start, current_exe, current_cmdline)):
        return False
    return (
        str(identity.get("bootId", "")) == current_boot
        and str(identity.get("procStartTime", "")) == current_start
        and os.path.realpath(str(identity.get("procExecutable", ""))) == current_exe
        and str(identity.get("cmdlineSha256", "")) == current_cmdline
    )


def _signal_verified_process(record: dict[str, Any], sig: int) -> None:
    """Signal the recorded task, using pidfd when Python/kernel provide it.

    Identity is checked before and after pidfd_open. Without pidfd we perform a
    second check immediately before os.kill. Any uncertainty fails closed.
    """

    pid = int(record.get("pid", 0))
    if not _record_matches_process(record):
        raise ValueError("PID identity no longer matches recorded runtime session")

    pidfd_open = getattr(os, "pidfd_open", None)
    pidfd_send_signal = getattr(signal, "pidfd_send_signal", None)
    if callable(pidfd_open) and callable(pidfd_send_signal):
        try:
            fd = pidfd_open(pid, 0)
        except OSError as exc:
            raise ValueError(f"cannot open pidfd for verified session pid {pid}: {exc}") from exc
        try:
            if not _record_matches_process(record):
                raise ValueError("PID identity changed while opening pidfd; signal refused")
            pidfd_send_signal(fd, sig, None, 0)
            return
        finally:
            os.close(fd)

    if not _record_matches_process(record):
        raise ValueError("PID identity changed before signal; signal refused")
    os.kill(pid, sig)


def _load_session_record(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    record = _read_json(path)
    if record.get("marker") != SESSION_MARKER:
        raise ValueError(f"Session file не принадлежит Stage 11 runner: {path}")
    return record


def runtime_session_status(root: Path | None = None, profile_id: str = "default") -> RuntimeSessionStatus:
    """Read-only status текущей session."""

    layout = discover_layout(root)
    session_path = _session_path(layout.root, profile_id)
    record = _load_session_record(session_path)
    if record is None:
        return RuntimeSessionStatus("not-started", profile_id, session_path, message="session state отсутствует")

    if not _path_belongs_to_root(record.get("binaryPath"), layout.root) or not _path_belongs_to_root(record.get("sessionPath"), layout.root):
        return RuntimeSessionStatus(
            "stale",
            profile_id,
            session_path,
            pid=int(record.get("pid", 0)) if int(record.get("pid", 0)) > 0 else None,
            plan_id=str(record.get("planId", "")) or None,
            plan_hash=str(record.get("planHash", "")) or None,
            binary_path=str(record.get("binaryPath", "")) or None,
            message="session record относится к другому workspace; stop из текущего workspace запрещён",
        )

    try:
        schema_version = int(record.get("schemaVersion", 1))
    except (TypeError, ValueError):
        schema_version = 0
    pid = int(record.get("pid", 0))
    recorded_state = str(record.get("state", "unknown"))
    alive = _pid_alive(pid)
    if schema_version > SESSION_SCHEMA_VERSION:
        return RuntimeSessionStatus(
            "unknown", profile_id, session_path, pid=pid if pid > 0 else None,
            plan_id=str(record.get("planId", "")) or None, plan_hash=str(record.get("planHash", "")) or None,
            binary_path=str(record.get("binaryPath", "")) or None,
            message=f"session schema {schema_version} новее поддерживаемой {SESSION_SCHEMA_VERSION}; mutation/stop запрещены",
        )
    if alive and (schema_version < SESSION_SCHEMA_VERSION or not isinstance(record.get("processIdentity"), dict)):
        return RuntimeSessionStatus(
            "migration-required", profile_id, session_path, pid=pid if pid > 0 else None,
            plan_id=str(record.get("planId", "")) or None, plan_hash=str(record.get("planHash", "")) or None,
            binary_path=str(record.get("binaryPath", "")) or None,
            message="legacy live session requires explicit receipted MigrationTxn before status can claim ownership",
        )
    matches = _record_matches_process(record) if alive else False
    if recorded_state == "stopped":
        state: SessionState = "stopped"
        message = "session ранее остановлена runner-ом"
    elif alive and matches:
        state = "running"
        message = "recorded process alive and exact process identity matches"
    elif alive and not matches:
        state = "unknown"
        message = "PID жив, но точная process identity не совпадает/неизвестна; stop запрещён"
    else:
        state = "stale"
        message = "session record есть, но процесс не найден"
    return RuntimeSessionStatus(
        state=state,
        profile_id=profile_id,
        session_path=session_path,
        pid=pid if pid > 0 else None,
        plan_id=str(record.get("planId", "")) or None,
        plan_hash=str(record.get("planHash", "")) or None,
        binary_path=str(record.get("binaryPath", "")) or None,
        message=message,
    )


def start_runtime_session(
    root: Path | None = None,
    profile_id: str = "default",
    *,
    launcher: Callable[[RuntimeSessionConfig], RuntimeSessionLaunchReceipt] | None = None,
    run_id: str | None = None,
) -> RuntimeSessionResult:
    """Запускает nfqws2 как локальную session, привязанную к confirmed plan."""

    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    current_status = runtime_session_status(paths.root, profile_id)
    if current_status.state == "running":
        return RuntimeSessionResult(
            action="start",
            state="running",
            profile_id=profile_id,
            message="session уже запущена; повторный старт не выполнен",
            session_path=current_status.session_path,
            pid=current_status.pid,
            plan_id=current_status.plan_id,
            plan_hash=current_status.plan_hash,
            log_path=paths.logs_dir / f"{profile_id}.runtime.jsonl",
        )

    config = build_runtime_session_config(paths.root, profile_id, prepare_public_inputs=launcher is None)
    # Re-check immediately before Popen. A positive /proc match means this
    # queue is already owned elsewhere; fail closed instead of relying on
    # nfq_create_queue() to fail after firewall apply.
    ensure_nfqueue_available(config.nfqueue_num)
    launch_receipt: RuntimeSessionLaunchReceipt | None = None
    if launcher is None:
        _write_args_file(config)
        config.stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
        config.stderr_log_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_handle = config.stdout_log_path.open("ab")
        stderr_handle = config.stderr_log_path.open("ab")
        try:
            process = subprocess.Popen(
                list(config.argv),
                cwd=str(config.cwd),
                stdout=stdout_handle,
                stderr=stderr_handle,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
        finally:
            stdout_handle.close()
            stderr_handle.close()

        time.sleep(PROCESS_START_GRACE_SECONDS)
        exit_code = process.poll()
        if exit_code is not None:
            record = _base_session_record(config, process.pid, state="failed", run_id=run_id)
            record["exitCode"] = exit_code
            record["failedAt"] = _utc_now()
            _write_json(config.session_path, record)
            log_path = append_runtime_event(
                paths,
                _event(
                    "session-failed",
                    "error",
                    config.plan_id,
                    config.plan_hash,
                    f"nfqws2 process exited immediately with code {exit_code}; firewall/services were not changed.",
                    {"pid": process.pid, "exitCode": exit_code, "sessionPath": str(config.session_path.relative_to(paths.root))},
                ),
                profile_id=profile_id,
            )
            stderr_tail = _tail_text(config.stderr_log_path)
            detail = f"nfqws2 завершился сразу после запуска, exit code: {exit_code}. См. {config.stderr_log_path}"
            if stderr_tail:
                detail += f"\nstderr tail: {stderr_tail}"
            raise ValueError(detail)
        pid = process.pid
    else:
        launch_receipt = launcher(config)
        if launch_receipt.plan_hash != config.plan_hash:
            raise ValueError("privileged launcher receipt planHash mismatch")
        if launch_receipt.pid <= 1:
            raise ValueError("privileged launcher returned invalid pid")
        pid = launch_receipt.pid

    record = _base_session_record(config, pid, state="running", launch_receipt=launch_receipt, run_id=run_id)
    _write_json(config.session_path, record)
    log_path = append_runtime_event(
        paths,
        _event(
            "session-started",
            "info",
            config.plan_id,
            config.plan_hash,
            f"Started nfqws2 session for profile {profile_id}; firewall/services were not changed.",
            {"pid": pid, "sessionPath": str(config.session_path.relative_to(paths.root)), "privilegedLauncher": launch_receipt is not None},
        ),
        profile_id=profile_id,
    )
    return RuntimeSessionResult(
        action="start",
        state="running",
        profile_id=profile_id,
        message="nfqws2 session запущена как локальный процесс",
        session_path=config.session_path,
        pid=pid,
        plan_id=config.plan_id,
        plan_hash=config.plan_hash,
        log_path=log_path,
    )


def _base_session_record(
    config: RuntimeSessionConfig,
    pid: int,
    state: str,
    *,
    launch_receipt: RuntimeSessionLaunchReceipt | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    process_group_id: int | None
    try:
        process_group_id = os.getpgid(pid)
    except OSError:
        process_group_id = None
    provenance = verify_core_bundle(config.root_path, config.binary_path)
    runtime_executable = launch_receipt.runtime_executable_path if launch_receipt is not None else config.binary_path
    process_identity = (
        launch_receipt.process_identity
        if launch_receipt is not None and launch_receipt.process_identity is not None
        else _capture_process_identity(pid, runtime_executable)
    )
    return {
        "schemaVersion": SESSION_SCHEMA_VERSION,
        "stage": SESSION_STAGE,
        "marker": SESSION_MARKER,
        "state": state,
        "profileId": config.profile_id,
        "rootPath": str(config.root_path),
        "sessionPath": str(config.session_path),
        "planId": config.plan_id,
        "planHash": config.plan_hash,
        "runId": run_id,
        "pid": pid,
        "processGroupId": process_group_id,
        "startedAt": _utc_now(),
        "processIdentity": process_identity,
        "binaryPath": str(config.binary_path),
        "runtimeExecutablePath": str(runtime_executable),
        "cwd": str(config.cwd),
        "argv": list(config.argv),
        "runtimeArgs": list(config.runtime_args),
        "nfqueueNum": config.nfqueue_num,
        "nfqueueSource": config.nfqueue_source,
        "nfqueueExistingProcessesAtStart": list(find_nfqueue_processes(config.nfqueue_num)),
        "coreProvenance": {
            "state": provenance.state,
            "message": provenance.message,
            "receiptPath": str(provenance.receipt_path),
        },
        "sessionInputsDir": str(config.session_inputs_dir),
        "publicSessionInputsDir": str(config.public_session_inputs_dir) if config.public_session_inputs_dir else None,
        "hostlistInputPaths": [str(path) for path in config.hostlist_input_paths],
        "strategyFileInputPaths": [str(path) for path in config.strategy_file_input_paths],
        "luaInputPaths": [str(path) for path in config.lua_input_paths],
        "blobInputPaths": [str(path) for path in config.blob_input_paths],
        "dropIdentity": None if config.drop_identity is None else {"uid": config.drop_identity.uid, "gid": config.drop_identity.gid, "source": config.drop_identity.source},
        "argsPath": str(config.args_path),
        "pidfilePath": str(config.pidfile_path),
        "stdoutLogPath": str(launch_receipt.stdout_log_path if launch_receipt is not None else config.stdout_log_path),
        "stderrLogPath": str(launch_receipt.stderr_log_path if launch_receipt is not None else config.stderr_log_path),
        "debugLogPath": str(launch_receipt.debug_log_path if launch_receipt is not None and launch_receipt.debug_log_path else config.debug_log_path),
        "privilegedExecutor": None if launch_receipt is None else {
            "helperSha256": launch_receipt.helper_sha256,
            "helperVersion": launch_receipt.helper_version,
            "ruid": launch_receipt.helper_ruid,
            "euid": launch_receipt.helper_euid,
            "actionId": launch_receipt.action_id,
            "planHash": launch_receipt.plan_hash,
            "requestHash": launch_receipt.request_hash,
        },
        "stopPolicy": {
            "stopsOnlyRecordedPid": True,
            "requiresOwnedMarker": True,
            "requiresExactProcessIdentity": True,
            "usesPidfdWhenAvailable": True,
            "termTimeoutSeconds": PROCESS_STOP_TIMEOUT_SECONDS,
        },
        "mutatesFirewallOrServicesNow": False,
        "managesServiceNow": False,
        "containsBootstrap": False,
        "containsUpstreamInstallerScript": False,
    }


def _try_reap_child(pid: int) -> bool:
    try:
        waited_pid, _status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return False
    except OSError:
        return False
    return waited_pid == pid


def _wait_until_dead(pid: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _try_reap_child(pid):
            return True
        if not _pid_alive(pid):
            return True
        time.sleep(0.1)
    if _try_reap_child(pid):
        return True
    return not _pid_alive(pid)


def stop_runtime_session(root: Path | None = None, profile_id: str = "default", *, run_id: str | None = None) -> RuntimeSessionResult:
    """Останавливает только PID, записанный нашим Stage 11 session record."""

    layout = discover_layout(root)
    paths = ensure_runtime_store(layout.root)
    session_path = paths.sessions_dir / f"{profile_id}.session.json"
    record = _load_session_record(session_path)
    if record is None:
        return RuntimeSessionResult(
            action="stop",
            state="not-started",
            profile_id=profile_id,
            message="session state отсутствует; останавливать нечего",
            session_path=session_path,
            log_path=paths.logs_dir / f"{profile_id}.runtime.jsonl",
        )

    if not _path_belongs_to_root(record.get("binaryPath"), paths.root) or not _path_belongs_to_root(record.get("sessionPath"), paths.root):
        return RuntimeSessionResult(
            action="stop",
            state="stale",
            profile_id=profile_id,
            message="session record относится к другому workspace; stop из текущего workspace запрещён",
            session_path=session_path,
            pid=int(record.get("pid", 0)) if int(record.get("pid", 0)) > 0 else None,
            plan_id=str(record.get("planId", "")) or None,
            plan_hash=str(record.get("planHash", "")) or None,
            log_path=paths.logs_dir / f"{profile_id}.runtime.jsonl",
        )

    pid = int(record.get("pid", 0))
    plan_id = str(record.get("planId", ""))
    plan_hash = str(record.get("planHash", ""))
    if str(record.get("state", "")) == "stopped":
        return RuntimeSessionResult(
            action="stop",
            state="stopped",
            profile_id=profile_id,
            message="session уже была остановлена runner-ом; повторный signal не отправлялся",
            session_path=session_path,
            pid=pid if pid > 0 else None,
            plan_id=plan_id,
            plan_hash=plan_hash,
            log_path=paths.logs_dir / f"{profile_id}.runtime.jsonl",
        )
    try:
        schema_version = int(record.get("schemaVersion", 1))
    except (TypeError, ValueError):
        schema_version = 0
    if schema_version > SESSION_SCHEMA_VERSION:
        raise ValueError(f"session schema {schema_version} новее поддерживаемой {SESSION_SCHEMA_VERSION}; stop запрещён")
    if _pid_alive(pid) and (schema_version < SESSION_SCHEMA_VERSION or not isinstance(record.get("processIdentity"), dict)):
        raise ValueError("legacy live session требует explicit MigrationTxn перед stop")

    if not _pid_alive(pid):
        updated = dict(record)
        updated["state"] = "stale"
        if run_id is not None:
            updated["runId"] = run_id
        updated["staleAt"] = _utc_now()
        _write_json(session_path, updated)
        log_path = append_runtime_event(
            paths,
            _event("session-stale", "warning", plan_id, plan_hash, "Session PID is not alive; no signal was sent.", {"pid": pid}),
            profile_id=profile_id,
        )
        return RuntimeSessionResult("stop", "stale", profile_id, "процесс уже не существует; signal не отправлялся", session_path, pid, plan_id, plan_hash, log_path)

    if not _record_matches_process(record):
        raise ValueError("PID из session state не подтверждён exact process identity; stop отклонён, чтобы не остановить чужой процесс")

    _signal_verified_process(record, signal.SIGTERM)
    terminated = _wait_until_dead(pid, PROCESS_STOP_TIMEOUT_SECONDS)
    if not terminated:
        _signal_verified_process(record, signal.SIGKILL)
        terminated = _wait_until_dead(pid, PROCESS_STOP_TIMEOUT_SECONDS)

    updated = dict(record)
    updated["state"] = "stopped" if terminated else "unknown"
    if run_id is not None:
        updated["runId"] = run_id
    updated["stoppedAt"] = _utc_now()
    updated["stopSignal"] = "SIGTERM" if terminated else "SIGKILL-attempted"
    _write_json(session_path, updated)
    if terminated and record.get("publicSessionInputsDir"):
        _cleanup_public_session_inputs(
            tuple(Path(item) for item in record.get("hostlistInputPaths", []))
            + tuple(Path(item) for item in record.get("strategyFileInputPaths", []))
            + tuple(Path(item) for item in record.get("luaInputPaths", []))
            + tuple(Path(item) for item in record.get("blobInputPaths", []))
        )
    log_path = append_runtime_event(
        paths,
        _event(
            "session-stopped" if terminated else "session-stop-unknown",
            "info" if terminated else "error",
            plan_id,
            plan_hash,
            "Stopped recorded nfqws2 session; firewall/services were not changed." if terminated else "Could not confirm process stop.",
            {"pid": pid, "sessionPath": str(session_path.relative_to(paths.root))},
        ),
        profile_id=profile_id,
    )
    return RuntimeSessionResult(
        action="stop",
        state="stopped" if terminated else "unknown",
        profile_id=profile_id,
        message="записанный session процесс остановлен" if terminated else "не удалось подтвердить остановку процесса",
        session_path=session_path,
        pid=pid,
        plan_id=plan_id,
        plan_hash=plan_hash,
        log_path=log_path,
    )
