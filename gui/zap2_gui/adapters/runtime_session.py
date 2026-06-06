"""Guarded runtime session runner для процесса nfqws2.

Stage 11 исполняет только lifecycle локального процесса, привязанного к уже
подготовленному и подтверждённому runtime start-plan. Модуль не применяет
firewall/routing rules, не управляет systemd/service manager, не делает
bootstrap и не вызывает upstream installer scripts.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .runtime_plan_generator import GeneratedRuntimePlan, create_runtime_plan
from .runtime_state import (
    append_runtime_event,
    ensure_runtime_store,
    generated_runtime_plan_to_payload,
    plan_payload_hash,
    runtime_store_paths,
)
from ..project_paths import discover_layout

SESSION_STAGE = "v0.3-beta_stage_3"
SESSION_SCHEMA_VERSION = 1
SESSION_MARKER = "zap2-runtime-session-v1"
DEFAULT_NFQUEUE_NUM = 200
PROCESS_START_GRACE_SECONDS = 0.25
PROCESS_STOP_TIMEOUT_SECONDS = 5.0


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


SessionState = Literal["not-started", "running", "stopped", "stale", "failed", "unknown"]


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
    pidfile_path: Path
    stdout_log_path: Path
    stderr_log_path: Path
    debug_log_path: Path
    session_path: Path
    runtime_args: tuple[str, ...]
    drop_identity: RuntimeDropIdentity | None = None

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
                f"pidfile: {self.pidfile_path}",
                f"stdout log: {self.stdout_log_path}",
                f"stderr log: {self.stderr_log_path}",
                f"debug log: {self.debug_log_path}",
                f"debug enabled: {'yes' if _runtime_debug_enabled() else 'no'}",
                f"session file: {self.session_path}",
                f"drop identity: {self.drop_identity.uid}:{self.drop_identity.gid} ({self.drop_identity.source})" if self.drop_identity else "drop identity: upstream default",
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
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    payload = generated_runtime_plan_to_payload(plan)
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


def _detect_drop_identity(root: Path) -> RuntimeDropIdentity | None:
    """Возвращает явную --uid identity для sudo/root запуска.

    Нерутовый запуск оставляет upstream default untouched. Root/sudo запуск получает
    явный uid/gid, чтобы nfqws2 после privilege drop мог читать hostlist и другие
    файлы пользовательского workspace.
    """

    if not _running_as_root():
        return None

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


def _runtime_args_for_plan(paths_root: Path, plan: GeneratedRuntimePlan, drop_identity: RuntimeDropIdentity | None, pidfile_path: Path, debug_log_path: Path) -> tuple[str, ...]:
    args: list[str] = [
        f"--qnum={DEFAULT_NFQUEUE_NUM}",
        f"--pidfile={pidfile_path}",
    ]
    if _runtime_debug_enabled():
        args.append(f"--debug=@{debug_log_path}")
    args.extend(plan.strategy.runtime_args)
    if drop_identity is not None:
        args.append(drop_identity.option)
    if plan.hostlists:
        args.append(f"--hostlist={(paths_root / plan.hostlists[0].path).resolve()}")
    return tuple(args)


def _tail_text(path: Path, max_chars: int = 1200) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:].strip()


def build_runtime_session_config(root: Path | None = None, profile_id: str = "default") -> RuntimeSessionConfig:
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

    session_path = paths.sessions_dir / f"{profile_id}.session.json"
    args_path = paths.sessions_dir / f"{profile_id}.nfqws2.args"
    pidfile_path = paths.sessions_dir / f"{profile_id}.nfqws2.pid"
    stdout_log_path = paths.logs_dir / f"{profile_id}.nfqws2.stdout.log"
    stderr_log_path = paths.logs_dir / f"{profile_id}.nfqws2.stderr.log"
    debug_log_path = paths.logs_dir / f"{profile_id}.nfqws2.debug.log"
    drop_identity = _detect_drop_identity(paths.root)
    runtime_args = _runtime_args_for_plan(paths.root, plan, drop_identity, pidfile_path, debug_log_path)

    return RuntimeSessionConfig(
        profile_id=profile_id,
        plan_id=plan.plan_id,
        plan_hash=plan_hash,
        root_path=paths.root,
        binary_path=binary_path,
        cwd=paths.root,
        argv=(str(binary_path), f"@{args_path}"),
        args_path=args_path,
        pidfile_path=pidfile_path,
        stdout_log_path=stdout_log_path,
        stderr_log_path=stderr_log_path,
        debug_log_path=debug_log_path,
        session_path=session_path,
        runtime_args=runtime_args,
        drop_identity=drop_identity,
    )


def _write_args_file(config: RuntimeSessionConfig) -> None:
    config.args_path.write_text("\n".join(config.runtime_args) + "\n", encoding="utf-8")


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
    if not proc_cmdline.exists():
        return None
    raw = proc_cmdline.read_bytes()
    if not raw:
        return ()
    return tuple(part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part)


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


def _record_matches_process(record: dict[str, Any]) -> bool:
    pid = int(record.get("pid", 0))
    binary_path = str(record.get("binaryPath", ""))
    cmdline = _proc_cmdline(pid)
    if cmdline is None:
        # На системах без /proc опираемся на PID только после проверки session marker.
        return True
    if not cmdline:
        return False
    expected = os.path.realpath(binary_path)
    for part in cmdline:
        candidate = part[1:] if part.startswith("@") else part
        if not candidate.startswith("/"):
            continue
        if os.path.realpath(candidate) == expected:
            return True
    return False


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

    pid = int(record.get("pid", 0))
    recorded_state = str(record.get("state", "unknown"))
    alive = _pid_alive(pid)
    matches = _record_matches_process(record) if alive else False
    if recorded_state == "stopped":
        state: SessionState = "stopped"
        message = "session ранее остановлена runner-ом"
    elif alive and matches:
        state = "running"
        message = "recorded process alive and matches session binary"
    elif alive and not matches:
        state = "unknown"
        message = "PID жив, но process command не совпадает с session record; stop запрещён"
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


def start_runtime_session(root: Path | None = None, profile_id: str = "default") -> RuntimeSessionResult:
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

    config = build_runtime_session_config(paths.root, profile_id)
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
        record = _base_session_record(config, process.pid, state="failed")
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

    record = _base_session_record(config, process.pid, state="running")
    _write_json(config.session_path, record)
    log_path = append_runtime_event(
        paths,
        _event(
            "session-started",
            "info",
            config.plan_id,
            config.plan_hash,
            f"Started nfqws2 session for profile {profile_id}; firewall/services were not changed.",
            {"pid": process.pid, "sessionPath": str(config.session_path.relative_to(paths.root))},
        ),
        profile_id=profile_id,
    )
    return RuntimeSessionResult(
        action="start",
        state="running",
        profile_id=profile_id,
        message="nfqws2 session запущена как локальный процесс",
        session_path=config.session_path,
        pid=process.pid,
        plan_id=config.plan_id,
        plan_hash=config.plan_hash,
        log_path=log_path,
    )


def _base_session_record(config: RuntimeSessionConfig, pid: int, state: str) -> dict[str, Any]:
    process_group_id: int | None
    try:
        process_group_id = os.getpgid(pid)
    except OSError:
        process_group_id = None
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
        "pid": pid,
        "processGroupId": process_group_id,
        "startedAt": _utc_now(),
        "binaryPath": str(config.binary_path),
        "cwd": str(config.cwd),
        "argv": list(config.argv),
        "runtimeArgs": list(config.runtime_args),
        "dropIdentity": None if config.drop_identity is None else {"uid": config.drop_identity.uid, "gid": config.drop_identity.gid, "source": config.drop_identity.source},
        "argsPath": str(config.args_path),
        "pidfilePath": str(config.pidfile_path),
        "stdoutLogPath": str(config.stdout_log_path),
        "stderrLogPath": str(config.stderr_log_path),
        "debugLogPath": str(config.debug_log_path),
        "stopPolicy": {
            "stopsOnlyRecordedPid": True,
            "requiresOwnedMarker": True,
            "checksProcCmdlineWhenAvailable": True,
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


def stop_runtime_session(root: Path | None = None, profile_id: str = "default") -> RuntimeSessionResult:
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
    if not _pid_alive(pid):
        updated = dict(record)
        updated["state"] = "stale"
        updated["staleAt"] = _utc_now()
        _write_json(session_path, updated)
        log_path = append_runtime_event(
            paths,
            _event("session-stale", "warning", plan_id, plan_hash, "Session PID is not alive; no signal was sent.", {"pid": pid}),
            profile_id=profile_id,
        )
        return RuntimeSessionResult("stop", "stale", profile_id, "процесс уже не существует; signal не отправлялся", session_path, pid, plan_id, plan_hash, log_path)

    if not _record_matches_process(record):
        raise ValueError("PID из session state не совпадает с recorded binary; stop отклонён, чтобы не остановить чужой процесс")

    os.kill(pid, signal.SIGTERM)
    terminated = _wait_until_dead(pid, PROCESS_STOP_TIMEOUT_SECONDS)
    if not terminated:
        os.kill(pid, signal.SIGKILL)
        terminated = _wait_until_dead(pid, PROCESS_STOP_TIMEOUT_SECONDS)

    updated = dict(record)
    updated["state"] = "stopped" if terminated else "unknown"
    updated["stoppedAt"] = _utc_now()
    updated["stopSignal"] = "SIGTERM" if terminated else "SIGKILL-attempted"
    _write_json(session_path, updated)
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
