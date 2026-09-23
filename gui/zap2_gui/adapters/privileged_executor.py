"""P02 bounded privileged executor client.

The standard runtime path must never execute the writable GUI package as root.
This module keeps orchestration/state in the normal user process and delegates
only finite actions to a separately installed root-owned helper.  Requests are
canonical JSON bytes over stdin; no project path, PYTHONPATH or arbitrary argv
is appended to the privileged command line.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime_apply import RuntimeCommandResult
from .runtime_session import RuntimeSessionConfig, RuntimeSessionLaunchReceipt
from .runtime_state import ensure_runtime_store
from ..project_paths import discover_layout

PRIVILEGE_PROTOCOL_SCHEMA_VERSION = 1
PRIVILEGED_EXECUTOR_VERSION = "p02-v1"
DEFAULT_PRIVILEGED_EXECUTOR = Path("/usr/local/libexec/zap2-runtime-executor")
PROJECT_EXECUTOR_RELATIVE_PATH = Path("tools/privileged/zap2-runtime-executor")
_PLAN_TRANSIENT_FIELDS = {
    "planHash",
    "preparedAt",
    "confirmationRequired",
    "confirmed",
    "expiresWhenPlanChanges",
    "allowsAutomaticReuse",
    "confirmationId",
    "confirmedAt",
}
_NFT_TRANSACTION_RE = re.compile(r"^(?P<profile>.+)\.(?P<action>apply|revert)\.(?P<hash>[0-9a-f]{12})\.nft$")


def _stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _plan_hash(plan: dict[str, Any]) -> str:
    payload = {key: value for key, value in plan.items() if key not in _PLAN_TRANSIENT_FIELDS}
    return _sha256_bytes(_stable_json(payload).encode("utf-8"))


@dataclass(frozen=True)
class PrivilegedExecutorStatus:
    path: Path
    state: str
    message: str
    installed_sha256: str | None
    project_sha256: str | None
    owner_uid: int | None
    mode: int | None

    @property
    def ready(self) -> bool:
        return self.state == "ready"

    def to_text(self) -> str:
        return "\n".join(
            [
                f"P02 privileged executor: {self.state}",
                f"path: {self.path}",
                f"installed sha256: {self.installed_sha256 or 'нет'}",
                f"project sha256: {self.project_sha256 or 'нет'}",
                f"owner uid: {self.owner_uid if self.owner_uid is not None else 'unknown'}",
                f"mode: {oct(self.mode) if self.mode is not None else 'unknown'}",
                f"message: {self.message}",
                "root imports workspace Python: no",
                "request transport: canonical JSON bytes over stdin",
            ]
        )


def project_executor_path(root: Path | None = None) -> Path:
    return discover_layout(root).root / PROJECT_EXECUTOR_RELATIVE_PATH


def privileged_executor_status(root: Path | None = None, *, installed_path: Path = DEFAULT_PRIVILEGED_EXECUTOR) -> PrivilegedExecutorStatus:
    layout = discover_layout(root)
    source = project_executor_path(layout.root)
    project_sha = _file_sha256(source)
    try:
        info = installed_path.stat()
    except OSError as exc:
        return PrivilegedExecutorStatus(installed_path, "missing", f"trusted helper не установлен: {exc}", None, project_sha, None, None)
    mode = stat.S_IMODE(info.st_mode)
    installed_sha = _file_sha256(installed_path)
    if not stat.S_ISREG(info.st_mode):
        return PrivilegedExecutorStatus(installed_path, "untrusted", "helper path не является regular file", installed_sha, project_sha, info.st_uid, mode)
    if info.st_uid != 0:
        return PrivilegedExecutorStatus(installed_path, "untrusted", "helper должен принадлежать root", installed_sha, project_sha, info.st_uid, mode)
    if mode & 0o022:
        return PrivilegedExecutorStatus(installed_path, "untrusted", "helper не должен быть group/world writable", installed_sha, project_sha, info.st_uid, mode)
    if not os.access(installed_path, os.X_OK):
        return PrivilegedExecutorStatus(installed_path, "untrusted", "helper не executable", installed_sha, project_sha, info.st_uid, mode)
    if project_sha is None:
        return PrivilegedExecutorStatus(installed_path, "unknown", "project helper source отсутствует; provenance comparison невозможен", installed_sha, None, info.st_uid, mode)
    if installed_sha != project_sha:
        return PrivilegedExecutorStatus(installed_path, "mismatch", "installed helper hash отличается от source текущего HEAD", installed_sha, project_sha, info.st_uid, mode)
    return PrivilegedExecutorStatus(installed_path, "ready", "root-owned helper совпадает с source текущего HEAD", installed_sha, project_sha, info.st_uid, mode)


def privileged_executor_install_command(root: Path | None = None, *, installed_path: Path = DEFAULT_PRIVILEGED_EXECUTOR) -> str:
    source = project_executor_path(root)
    digest = _file_sha256(source) or "UNKNOWN"
    return "\n".join(
        [
            "P02 trusted helper install (явное действие владельца):",
            f"source: {source}",
            f"source sha256: {digest}",
            f"target: {installed_path}",
            f"sudo install -D -o root -g root -m 0755 -- {source} {installed_path}",
            "После install обязательно повторно проверьте --privileged-executor-status.",
            "devctl start и автоматические checks этот install не выполняют.",
        ]
    )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _confirmed_plan(root: Path, plan_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    paths = ensure_runtime_store(root)
    plan_path = paths.plans_dir / f"{plan_id}.json"
    confirmation_path = paths.confirmations_dir / f"{plan_id}.confirmation.json"
    if not plan_path.is_file() or not confirmation_path.is_file():
        raise ValueError(f"confirmed plan pair отсутствует: {plan_id}")
    plan = _load_json(plan_path)
    confirmation = _load_json(confirmation_path)
    calculated = _plan_hash(plan)
    if plan.get("planHash") != calculated:
        raise ValueError(f"saved plan hash mismatch: {plan_id}")
    if confirmation.get("planHash") != calculated or confirmation.get("confirmedByOwner") is not True:
        raise ValueError(f"confirmation hash mismatch: {plan_id}")
    return plan, confirmation


def _request(action_id: str, payload: dict[str, Any]) -> tuple[bytes, str]:
    body: dict[str, Any] = {
        "schemaVersion": PRIVILEGE_PROTOCOL_SCHEMA_VERSION,
        "protocol": "zap2-privilege-plan/v1",
        "actionId": action_id,
        "payload": payload,
    }
    request_hash = _sha256_bytes(_stable_json(body).encode("utf-8"))
    body["requestHash"] = request_hash
    return (_stable_json(body) + "\n").encode("utf-8"), request_hash


def _sudo_command(installed_path: Path, request_hash: str, askpass: Path | None) -> tuple[str, ...]:
    prefix = ("sudo", "-A", "--") if askpass is not None else ("sudo", "--")
    return (*prefix, str(installed_path), "--execute", "--request-hash", request_hash)


def _helper_env(askpass: Path | None) -> dict[str, str] | None:
    if askpass is None:
        return None
    env = os.environ.copy()
    env["SUDO_ASKPASS"] = str(askpass)
    env.setdefault("ZAP2_SUDO_ASKPASS_PROMPT", "Введите пароль sudo для bounded Zap2 executor")
    return env


def _call_helper(
    root: Path,
    action_id: str,
    payload: dict[str, Any],
    *,
    askpass: Path | None,
    installed_path: Path,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    status = privileged_executor_status(root, installed_path=installed_path)
    if not status.ready:
        raise ValueError(status.to_text() + "\n\n" + privileged_executor_install_command(root, installed_path=installed_path))
    if shutil.which("sudo") is None:
        raise ValueError("sudo не найден; bounded privileged executor недоступен")
    request_bytes, request_hash = _request(action_id, payload)
    completed = subprocess.run(
        list(_sudo_command(installed_path, request_hash, askpass)),
        input=request_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=root,
        env=_helper_env(askpass),
        check=False,
        timeout=timeout_seconds,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    try:
        receipt = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"privileged executor returned invalid JSON (rc={completed.returncode}): {stdout}\n{stderr}") from exc
    if completed.returncode != 0:
        message = receipt.get("message") if isinstance(receipt, dict) else None
        raise ValueError(f"privileged executor failed rc={completed.returncode}: {message or stderr or stdout}")
    if not isinstance(receipt, dict) or receipt.get("requestHash") != request_hash:
        raise ValueError("privileged executor receipt requestHash mismatch")
    return receipt


def _plan_for_transaction(root: Path, transaction_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    match = _NFT_TRANSACTION_RE.match(transaction_path.name)
    if match is None:
        raise ValueError(f"unexpected nft transaction filename: {transaction_path.name}")
    hash_prefix = match.group("hash")
    action = match.group("action")
    paths = ensure_runtime_store(root)
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for plan_path in paths.plans_dir.glob("*.json"):
        try:
            plan = _load_json(plan_path)
        except Exception:
            continue
        if str(plan.get("action")) != action:
            continue
        plan_hash = str(plan.get("planHash", ""))
        if plan_hash.startswith(hash_prefix):
            try:
                candidates.append(_confirmed_plan(root, str(plan.get("planId", ""))))
            except ValueError:
                continue
    if len(candidates) != 1:
        raise ValueError(f"cannot bind nft transaction {transaction_path.name} to exactly one confirmed plan")
    return candidates[0]


class BoundedNftRunner:
    """RuntimeApply CommandRunner backed by the finite root-owned helper."""

    def __init__(self, root: Path, *, askpass: Path | None = None, installed_path: Path = DEFAULT_PRIVILEGED_EXECUTOR):
        self.root = root.resolve()
        self.askpass = askpass
        self.installed_path = installed_path

    def __call__(self, argv: tuple[str, ...]) -> RuntimeCommandResult:
        if argv[:4] == ("nft", "list", "table", "inet") and len(argv) == 5:
            receipt = _call_helper(
                self.root,
                "nft.observe-table",
                {"table": argv[4]},
                askpass=self.askpass,
                installed_path=self.installed_path,
            )
        elif len(argv) == 4 and argv[:3] == ("nft", "--check", "-f"):
            transaction = Path(argv[3])
            plan, confirmation = _plan_for_transaction(self.root, transaction)
            receipt = _call_helper(
                self.root,
                "nft.check-confirmed-plan",
                {"plan": plan, "confirmation": confirmation, "batch": transaction.read_text(encoding="utf-8")},
                askpass=self.askpass,
                installed_path=self.installed_path,
            )
        elif len(argv) == 3 and argv[:2] == ("nft", "-f"):
            transaction = Path(argv[2])
            plan, confirmation = _plan_for_transaction(self.root, transaction)
            receipt = _call_helper(
                self.root,
                "nft.execute-confirmed-plan",
                {"plan": plan, "confirmation": confirmation, "batch": transaction.read_text(encoding="utf-8")},
                askpass=self.askpass,
                installed_path=self.installed_path,
            )
        else:
            raise ValueError(f"bounded nft runner rejected argv: {argv}")
        command = receipt.get("command", {})
        helper = receipt.get("helper") if isinstance(receipt.get("helper"), dict) else {}
        evidence = {
            "helperSha256": str(helper.get("sha256", "")),
            "helperVersion": str(helper.get("version", "")),
            "ruid": helper.get("ruid"),
            "euid": helper.get("euid"),
            "actionId": str(receipt.get("actionId", "")),
            "planHash": str(receipt.get("planHash", "")),
            "requestHash": str(receipt.get("requestHash", "")),
        }
        return RuntimeCommandResult(
            argv=argv,
            returncode=int(command.get("returncode", 1)),
            stdout=str(command.get("stdout", "")),
            stderr=str(command.get("stderr", "")),
            evidence=evidence,
        )


class BoundedSessionLauncher:
    """Start nfqws2 through the plan-bound root helper and return a lifecycle receipt."""

    def __init__(self, root: Path, *, askpass: Path | None = None, installed_path: Path = DEFAULT_PRIVILEGED_EXECUTOR):
        self.root = root.resolve()
        self.askpass = askpass
        self.installed_path = installed_path

    def __call__(self, config: RuntimeSessionConfig) -> RuntimeSessionLaunchReceipt:
        plan, confirmation = _confirmed_plan(self.root, config.plan_id)
        receipt = _call_helper(
            self.root,
            "nfqws.start-confirmed-plan",
            {"rootPath": str(self.root), "plan": plan, "confirmation": confirmation},
            askpass=self.askpass,
            installed_path=self.installed_path,
            timeout_seconds=90,
        )
        process = receipt.get("process")
        helper = receipt.get("helper")
        if not isinstance(process, dict) or not isinstance(helper, dict):
            raise ValueError("privileged session receipt missing process/helper provenance")
        identity = process.get("identity") if isinstance(process.get("identity"), dict) else None
        return RuntimeSessionLaunchReceipt(
            pid=int(process["pid"]),
            runtime_executable_path=Path(str(process["executablePath"])),
            stdout_log_path=Path(str(process["stdoutLogPath"])),
            stderr_log_path=Path(str(process["stderrLogPath"])),
            debug_log_path=Path(str(process["debugLogPath"])) if process.get("debugLogPath") else None,
            helper_sha256=str(helper.get("sha256", "")),
            helper_version=str(helper.get("version", "")),
            helper_ruid=int(helper["ruid"]) if helper.get("ruid") is not None else None,
            helper_euid=int(helper["euid"]) if helper.get("euid") is not None else None,
            action_id=str(receipt.get("actionId", "")),
            plan_hash=str(receipt.get("planHash", "")),
            request_hash=str(receipt.get("requestHash", "")),
            process_identity=identity,
        )


def bounded_privilege_preview(
    root: Path | None = None,
    *,
    askpass: bool = True,
    installed_path: Path = DEFAULT_PRIVILEGED_EXECUTOR,
) -> tuple[str, ...]:
    """Return the fixed privileged argv shape used by P02.

    The real request hash is generated separately for every finite action from
    canonical stdin bytes; the preview intentionally contains no writable
    project Python path, arbitrary environment assignment or shell.
    """

    _ = discover_layout(root)
    prefix = ("sudo", "-A", "--") if askpass else ("sudo", "--")
    return (*prefix, str(installed_path), "--execute", "--request-hash", "<sha256-of-canonical-request>")


def execute_bounded_default_workflow(
    root: Path | None = None,
    *,
    action: str,
    profile_id: str = "default",
    confirm_plan_id: str = "",
    askpass: Path | None = None,
    installed_path: Path = DEFAULT_PRIVILEGED_EXECUTOR,
):
    """Execute the composite default workflow without importing app code as root."""

    layout = discover_layout(root)
    if os.geteuid() == 0:
        raise ValueError(
            "P02 запрещает запуск writable GUI/application package как root. "
            "Запустите команду обычным пользователем; finite effects выполняет root-owned executor."
        )
    from .runtime_default import execute_default_workflow

    nft_runner = BoundedNftRunner(layout.root, askpass=askpass, installed_path=installed_path)
    session_launcher = BoundedSessionLauncher(layout.root, askpass=askpass, installed_path=installed_path) if action == "start" else None
    return execute_default_workflow(
        layout.root,
        action=action,
        profile_id=profile_id,
        confirm_plan_id=confirm_plan_id,
        apply_runner=nft_runner,
        allow_without_root=True,
        session_launcher=session_launcher,
    )


def execute_bounded_owner_rules(
    root: Path | None = None,
    *,
    action: str,
    profile_id: str = "default",
    confirm_plan_id: str = "",
    askpass: Path | None = None,
    installed_path: Path = DEFAULT_PRIVILEGED_EXECUTOR,
):
    """Execute only the confirmed nft owner-rules child plan via the finite helper."""

    layout = discover_layout(root)
    if os.geteuid() == 0:
        raise ValueError("P02 owner-rules standard path must be invoked as the workspace owner, not root")
    from .runtime_apply import execute_runtime_owner_rules

    return execute_runtime_owner_rules(
        layout.root,
        action=action,
        profile_id=profile_id,
        confirm_plan_id=confirm_plan_id,
        runner=BoundedNftRunner(layout.root, askpass=askpass, installed_path=installed_path),
        allow_without_root=True,
    )


def execute_bounded_session_start(
    root: Path | None = None,
    *,
    profile_id: str = "default",
    askpass: Path | None = None,
    installed_path: Path = DEFAULT_PRIVILEGED_EXECUTOR,
):
    """Start only the confirmed nfqws session through the finite helper."""

    layout = discover_layout(root)
    if os.geteuid() == 0:
        raise ValueError("P02 session standard path must be invoked as the workspace owner, not root")
    from .runtime_session import start_runtime_session

    return start_runtime_session(
        layout.root,
        profile_id=profile_id,
        launcher=BoundedSessionLauncher(layout.root, askpass=askpass, installed_path=installed_path),
    )


__all__ = [
    "BoundedNftRunner",
    "BoundedSessionLauncher",
    "bounded_privilege_preview",
    "execute_bounded_default_workflow",
    "execute_bounded_owner_rules",
    "execute_bounded_session_start",
    "DEFAULT_PRIVILEGED_EXECUTOR",
    "PRIVILEGED_EXECUTOR_VERSION",
    "PrivilegedExecutorStatus",
    "privileged_executor_install_command",
    "privileged_executor_status",
    "project_executor_path",
]
