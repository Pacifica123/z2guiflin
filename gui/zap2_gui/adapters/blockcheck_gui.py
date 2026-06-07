"""GUI-facing blockcheck2 adapter for local strategy discovery.

The upstream ``blockcheck2.sh`` script is an interactive, privileged diagnostic
helper. This module turns a small, explicit subset into GUI/CLI objects without
running anything at import time. Execution still goes through graphical
``sudo -A`` askpass and is intentionally visible: the owner chooses the target
and starts the scan manually.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .build_dependencies import BuildDependencyReport, run_build_dependency_preflight
from .gui_privilege import _desktop_env_for_askpass, ensure_sudo_askpass_helper, is_sudo_available
from .local_build import LocalBuildPlan, create_local_build_plan, inspect_artifacts
from ..project_paths import discover_layout

SUPPORTED_BLOCKCHECK_TESTS = ("standard", "custom")
SUPPORTED_BLOCKCHECK_SCANLEVELS = ("quick", "standard", "force")
SUPPORTED_BLOCKCHECK_IPVS = ("4", "6", "46")
_SAFE_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/?=&%+~#@-]{0,250}$")


@dataclass(frozen=True)
class BlockcheckOptions:
    """Owner-selected blockcheck2 scan parameters."""

    domains: str = "youtube.com www.youtube.com"
    test: str = "standard"
    scanlevel: str = "quick"
    ipvs: str = "4"
    enable_http: bool = False
    enable_https_tls12: bool = True
    enable_https_tls13: bool = True
    enable_http3: bool = True
    skip_dnscheck: bool = True
    repeats: int = 1
    curl_max_time: int = 3
    timeout_seconds: int = 900

    def normalized_domains(self) -> tuple[str, ...]:
        values = tuple(item.strip() for item in self.domains.split() if item.strip())
        if not values:
            raise ValueError("blockcheck требует хотя бы один домен или URI")
        for value in values:
            if not _SAFE_TARGET_RE.fullmatch(value):
                raise ValueError(
                    "Недопустимый target для blockcheck: "
                    f"{value!r}. Разрешены домены/URI без пробелов и shell-символов."
                )
        return values

    def validate(self) -> None:
        self.normalized_domains()
        if self.test not in SUPPORTED_BLOCKCHECK_TESTS:
            raise ValueError(f"Неподдерживаемый blockcheck test: {self.test}")
        if self.scanlevel not in SUPPORTED_BLOCKCHECK_SCANLEVELS:
            raise ValueError(f"Неподдерживаемый blockcheck scanlevel: {self.scanlevel}")
        if self.ipvs not in SUPPORTED_BLOCKCHECK_IPVS:
            raise ValueError(f"Неподдерживаемый IPVS: {self.ipvs}")
        if not any((self.enable_http, self.enable_https_tls12, self.enable_https_tls13, self.enable_http3)):
            raise ValueError("Нужно включить хотя бы один протокол blockcheck")
        if not 1 <= self.repeats <= 5:
            raise ValueError("repeats должен быть в диапазоне 1..5")
        if not 1 <= self.curl_max_time <= 15:
            raise ValueError("curl timeout должен быть в диапазоне 1..15 секунд")
        if not 30 <= self.timeout_seconds <= 3600:
            raise ValueError("overall timeout должен быть в диапазоне 30..3600 секунд")

    def to_env(self) -> dict[str, str]:
        self.validate()
        return {
            "BATCH": "1",
            "TEST": self.test,
            "DOMAINS": " ".join(self.normalized_domains()),
            "IPVS": self.ipvs,
            "SCANLEVEL": self.scanlevel,
            "ENABLE_HTTP": "1" if self.enable_http else "0",
            "ENABLE_HTTPS_TLS12": "1" if self.enable_https_tls12 else "0",
            "ENABLE_HTTPS_TLS13": "1" if self.enable_https_tls13 else "0",
            "ENABLE_HTTP3": "1" if self.enable_http3 else "0",
            "SKIP_DNSCHECK": "1" if self.skip_dnscheck else "0",
            "REPEATS": str(self.repeats),
            "PARALLEL": "0",
            "CURL_MAX_TIME": str(self.curl_max_time),
            "CURL_MAX_TIME_QUIC": str(self.curl_max_time),
        }


@dataclass(frozen=True)
class BlockcheckArtifactStatus:
    """Read-only status of one blockcheck prerequisite."""

    label: str
    path_or_command: str
    ok: bool
    hint: str


@dataclass(frozen=True)
class BlockcheckPreflight:
    """Read-only prerequisite snapshot for blockcheck lab."""

    core_root: Path
    items: tuple[BlockcheckArtifactStatus, ...]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.items)

    def to_text(self) -> str:
        lines = [
            "Blockcheck preflight",
            f"core root: {self.core_root}",
            f"status: {'OK' if self.ok else 'needs attention'}",
            "",
        ]
        for item in self.items:
            mark = "OK" if item.ok else "MISSING"
            lines.append(f"- {mark}: {item.label}: {item.path_or_command}")
            if not item.ok:
                lines.append(f"  hint: {item.hint}")
        lines.extend(
            [
                "",
                "read-only: yes",
                "executes now: no",
                "mutates services/firewall now: no",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class BlockcheckCommand:
    """Command that the GUI can execute through sudo askpass."""

    options: BlockcheckOptions
    argv: tuple[str, ...]
    cwd: Path
    env_overrides: dict[str, str] = field(default_factory=dict)
    log_path: Path | None = None
    backend: str = "sudo-askpass"

    @property
    def uses_sudo_askpass(self) -> bool:
        return self.backend == "sudo-askpass"

    def redacted_command_preview(self) -> str:
        return " ".join(self.argv)

    def to_text(self) -> str:
        env_lines = [f"  {key}={value}" for key, value in sorted(self.options.to_env().items())]
        lines = [
            "Blockcheck GUI plan",
            f"domains: {', '.join(self.options.normalized_domains())}",
            f"test: {self.options.test}",
            f"scanlevel: {self.options.scanlevel}",
            f"ip versions: {self.options.ipvs}",
            f"cwd: {self.cwd}",
            f"log path: {self.log_path or 'не задан'}",
            "uses sudo askpass: yes",
            "uses pkexec/polkit: no",
            "asks password in terminal: no",
            "stores password: no",
            "contains remote bootstrap: no",
            "contains upstream installer script: no",
            "mutates services persistently: no",
            "mutates firewall temporarily: yes, inside upstream blockcheck cleanup path",
            "executes now: no",
            "",
            "environment passed to blockcheck2.sh:",
            *env_lines,
            "",
            "command:",
            self.redacted_command_preview(),
        ]
        return "\n".join(lines)


@dataclass(frozen=True)
class BlockcheckResult:
    """Completed blockcheck run and parsed summary hints."""

    command: BlockcheckCommand
    returncode: int
    stdout: str
    stderr: str
    summary_lines: tuple[str, ...]
    skipped_reason: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.skipped_reason

    def to_text(self) -> str:
        lines = [
            f"Blockcheck run: {'OK' if self.ok else 'FAILED'}",
            f"return code: {self.returncode}",
            "uses sudo askpass: no (skipped before sudo)" if self.skipped_reason else "uses sudo askpass: yes",
            "asks password in terminal: no",
            "stores password: no",
            f"log path: {self.command.log_path or 'не задан'}",
        ]
        if self.skipped_reason:
            lines.append(f"message: {self.skipped_reason}")
        if self.summary_lines:
            lines.extend(["", "Parsed SUMMARY / working strategy hints:"])
            lines.extend(f"- {line}" for line in self.summary_lines)
        if self.stdout.strip():
            lines.extend(["", "stdout:", self.stdout.rstrip()])
        if self.stderr.strip():
            lines.extend(["", "stderr:", self.stderr.rstrip()])
        if not self.stdout.strip() and not self.stderr.strip() and not self.skipped_reason:
            lines.append("message: команда завершилась без вывода")
        return "\n".join(lines)




@dataclass(frozen=True)
class BlockcheckBuildCommandResult:
    """Result of one local unprivileged build command for blockcheck prerequisites."""

    cwd: Path
    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class BlockcheckPrereqBuildPlan:
    """Explicit local build plan for binaries required by upstream blockcheck2."""

    local_build_plan: LocalBuildPlan
    dependency_report: BuildDependencyReport
    required_artifacts: tuple[Path, ...]

    def to_text(self) -> str:
        command_lines = [f"  - {command.shell_preview()}" for command in self.local_build_plan.commands]
        required_lines = [f"  - {path}" for path in self.required_artifacts]
        expected_lines = [f"  - {artifact.absolute_path}" for artifact in self.local_build_plan.expected_artifacts]
        return "\n".join(
            [
                "Blockcheck prerequisites build plan",
                "purpose: собрать nfqws2 и mdig перед privileged blockcheck run",
                f"target: {self.local_build_plan.target}",
                f"core root: {self.local_build_plan.core_root}",
                "commands:",
                *(command_lines or ["  - нет"]),
                "required artifacts for blockcheck:",
                *(required_lines or ["  - нет"]),
                "expected artifacts from selected build target:",
                *(expected_lines or ["  - нет"]),
                "dependency preflight:",
                f"  status: {self.dependency_report.summary_line()}",
                *(f"  - {check.status}: {check.check_id} — {check.details}" for check in self.dependency_report.checks),
                "executes now: no",
                "runs make now: no",
                "requires sudo: no",
                "mutates services/firewall: no",
                "mutates worktree when executed by owner: yes",
                "contains remote bootstrap: no",
                "contains upstream installer script: no",
            ]
        )


@dataclass(frozen=True)
class BlockcheckPrereqBuildResult:
    """Completed local build attempt for blockcheck prerequisites."""

    state: str
    plan: BlockcheckPrereqBuildPlan
    executed_commands: tuple[BlockcheckBuildCommandResult, ...]
    artifact_status: tuple[tuple[Path, bool, bool, int | None], ...]
    message: str

    @property
    def ok(self) -> bool:
        return self.state == "built"

    def to_text(self) -> str:
        lines = [
            f"Blockcheck prerequisites build: {self.state}",
            f"message: {self.message}",
            f"target: {self.plan.local_build_plan.target}",
            f"core root: {self.plan.local_build_plan.core_root}",
            f"dependency preflight: {self.plan.dependency_report.summary_line()}",
            "executed commands:",
        ]
        if self.plan.dependency_report.missing_required:
            lines.append("missing required dependencies:")
            for check in self.plan.dependency_report.missing_required:
                lines.append(f"  - {check.check_id}: {check.details}")
            lines.append("owner action hints:")
            for family, commands in self.plan.dependency_report.install_hints.items():
                lines.append(f"  {family}:")
                for command in commands:
                    lines.append(f"    - {command}")
        if not self.executed_commands:
            lines.append("  - нет")
        for result in self.executed_commands:
            lines.append(f"  - rc={result.returncode}: cd {result.cwd} && {' '.join(result.argv)}")
            if result.stderr.strip():
                lines.append(f"    stderr: {result.stderr.strip()}")
        lines.append("artifacts:")
        for path, exists, executable, size_bytes in self.artifact_status:
            size = "?" if size_bytes is None else str(size_bytes)
            lines.append(f"  - {path}: exists={'yes' if exists else 'no'}; executable={'yes' if executable else 'no'}; size={size}")
        lines.extend(
            [
                "requires sudo: no",
                "mutates services/firewall: no",
                "contains remote bootstrap: no",
                "contains upstream installer script: no",
                "next: повторите Blockcheck preflight, затем Blockcheck run",
            ]
        )
        return "\n".join(lines)


BlockcheckBuildRunner = Callable[[Path, tuple[str, ...]], BlockcheckBuildCommandResult]

def _is_executable(path: Path) -> bool:
    return path.is_file() and bool(path.stat().st_mode & 0o111)


def blockcheck_preflight(root: Path | None = None) -> BlockcheckPreflight:
    """Inspect local prerequisites without running blockcheck."""

    layout = discover_layout(root)
    core_root = layout.core_dir / "zapret2"
    items = (
        BlockcheckArtifactStatus(
            label="blockcheck2.sh",
            path_or_command=str(core_root / "blockcheck2.sh"),
            ok=(core_root / "blockcheck2.sh").is_file(),
            hint="vendored upstream blockcheck2.sh должен быть в core/zapret2",
        ),
        BlockcheckArtifactStatus(
            label="nfqws2 binary",
            path_or_command=str(core_root / "nfq2" / "nfqws2"),
            ok=_is_executable(core_root / "nfq2" / "nfqws2"),
            hint="соберите core target all или nfqws2 перед privileged blockcheck",
        ),
        BlockcheckArtifactStatus(
            label="mdig binary",
            path_or_command=str(core_root / "mdig" / "mdig"),
            ok=_is_executable(core_root / "mdig" / "mdig"),
            hint="для blockcheck upstream требует mdig; соберите core target all или mdig",
        ),
        BlockcheckArtifactStatus(
            label="curl",
            path_or_command="curl",
            ok=shutil.which("curl") is not None,
            hint="установите curl; blockcheck использует его для HTTP/TLS/QUIC проб",
        ),
        BlockcheckArtifactStatus(
            label="sudo -A",
            path_or_command="sudo",
            ok=is_sudo_available(),
            hint="GUI blockcheck запускает privileged scan только через sudo -A/SUDO_ASKPASS",
        ),
        BlockcheckArtifactStatus(
            label="nft or iptables",
            path_or_command="nft/iptables",
            ok=(shutil.which("nft") is not None or shutil.which("iptables") is not None),
            hint="blockcheck временно ставит firewall redirection через nftables или iptables",
        ),
    )
    return BlockcheckPreflight(core_root=core_root, items=items)


def blockcheck_preflight_to_text(root: Path | None = None) -> str:
    return blockcheck_preflight(root).to_text()




def _blockcheck_required_artifacts(core_root: Path) -> tuple[Path, ...]:
    return (core_root / "nfq2" / "nfqws2", core_root / "mdig" / "mdig")


def _artifact_rows(paths: tuple[Path, ...]) -> tuple[tuple[Path, bool, bool, int | None], ...]:
    rows: list[tuple[Path, bool, bool, int | None]] = []
    for path in paths:
        exists = path.exists()
        executable = path.is_file() and os.access(path, os.X_OK)
        rows.append((path, exists, executable, path.stat().st_size if exists else None))
    return tuple(rows)


def _is_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    return True if geteuid is None else geteuid() == 0


def _default_build_runner(cwd: Path, argv: tuple[str, ...]) -> BlockcheckBuildCommandResult:
    completed = subprocess.run(
        list(argv),
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return BlockcheckBuildCommandResult(
        cwd=cwd,
        argv=argv,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def create_blockcheck_prereq_build_plan(root: Path | None = None) -> BlockcheckPrereqBuildPlan:
    """Create a read-only local build plan for blockcheck-required binaries."""

    layout = discover_layout(root)
    local_plan = create_local_build_plan(layout.root, target="all")
    dependency_report = run_build_dependency_preflight("nfqws2")
    return BlockcheckPrereqBuildPlan(
        local_build_plan=local_plan,
        dependency_report=dependency_report,
        required_artifacts=_blockcheck_required_artifacts(local_plan.core_root),
    )


def blockcheck_build_plan_to_text(root: Path | None = None) -> str:
    return create_blockcheck_prereq_build_plan(root).to_text()


def execute_blockcheck_prereq_build(
    root: Path | None = None,
    *,
    runner: BlockcheckBuildRunner | None = None,
    allow_as_root: bool = False,
    dependency_report: BuildDependencyReport | None = None,
) -> BlockcheckPrereqBuildResult:
    """Run local make for blockcheck prerequisites after an explicit owner action.

    This path intentionally does not use sudo, does not install packages and does
    not touch firewall/service state. It only creates build artifacts inside the
    vendored core tree.
    """

    plan = create_blockcheck_prereq_build_plan(root)
    effective_report = dependency_report or plan.dependency_report
    if dependency_report is not None:
        plan = BlockcheckPrereqBuildPlan(
            local_build_plan=plan.local_build_plan,
            dependency_report=dependency_report,
            required_artifacts=plan.required_artifacts,
        )
    if runner is None:
        if not allow_as_root and _is_root():
            raise ValueError("Blockcheck prerequisites build не нужно запускать через sudo/root: это создаст root-owned артефакты в workspace.")
        runner = _default_build_runner

    results: list[BlockcheckBuildCommandResult] = []
    state = "built"
    message = "blockcheck prerequisites build completed"
    if not effective_report.ok:
        state = "blocked"
        message = "build dependency preflight failed: установите недостающие build dependencies и повторите сборку"
    if state == "built":
        for command in plan.local_build_plan.commands:
            result = runner(command.cwd, command.argv)
            results.append(result)
            if not result.ok:
                state = "failed"
                message = f"build command failed: {command.label}"
                break
    artifact_status = _artifact_rows(plan.required_artifacts)
    if state == "built" and not all(exists and executable for _path, exists, executable, _size in artifact_status):
        state = "failed"
        message = "build completed, but nfqws2/mdig executables are still missing"
    return BlockcheckPrereqBuildResult(
        state=state,
        plan=plan,
        executed_commands=tuple(results),
        artifact_status=artifact_status,
        message=message,
    )

def _planned_askpass_script_path(root: Path) -> Path:
    return root / ".zap2" / "runtime" / "askpass" / "zap2-sudo-askpass"


def build_blockcheck_command(root: Path | None = None, options: BlockcheckOptions | None = None) -> BlockcheckCommand:
    """Build the sudo-askpass blockcheck command without executing it."""

    opts = options or BlockcheckOptions()
    opts.validate()
    layout = discover_layout(root)
    core_root = layout.core_dir / "zapret2"
    script = core_root / "blockcheck2.sh"
    if not script.is_file():
        raise ValueError(f"blockcheck2.sh не найден: {script}")

    state_root = layout.root / ".zap2" / "blockcheck"
    rw_root = state_root / "rw"
    logs_root = state_root / "logs"
    log_path = logs_root / "last-blockcheck.txt"
    askpass = _planned_askpass_script_path(layout.root)

    env_assignments = {
        "ZAP2_GUI_PRIVILEGE_BRIDGE": "sudo-askpass",
        "ZAPRET_BASE": str(core_root),
        "ZAPRET_RW": str(rw_root),
        "ZAPRET_CONFIG": str(rw_root / "config"),
        **opts.to_env(),
    }
    env_argv = tuple(f"{key}={value}" for key, value in sorted(env_assignments.items()))
    argv = (
        "sudo",
        "-A",
        "env",
        *env_argv,
        "/bin/sh",
        str(script),
    )
    return BlockcheckCommand(
        options=opts,
        argv=argv,
        cwd=layout.root,
        env_overrides={"SUDO_ASKPASS": str(askpass)},
        log_path=log_path,
    )


def blockcheck_plan_to_text(root: Path | None = None, options: BlockcheckOptions | None = None) -> str:
    preflight = blockcheck_preflight(root)
    command = build_blockcheck_command(root=root, options=options)
    return "\n\n".join([preflight.to_text(), command.to_text()])


def parse_blockcheck_summary(stdout: str) -> tuple[str, ...]:
    """Extract concise strategy lines from blockcheck output."""

    lines = [line.strip() for line in stdout.splitlines()]
    result: list[str] = []
    in_summary = False
    for line in lines:
        if line == "* SUMMARY":
            in_summary = True
            continue
        if in_summary:
            if not line:
                continue
            if line.startswith("Please note"):
                break
            result.append(line)
        elif "working strategy found" in line:
            result.append(line.strip("! "))
    deduped: list[str] = []
    seen: set[str] = set()
    for line in result:
        if line not in seen:
            seen.add(line)
            deduped.append(line)
    return tuple(deduped[:40])


def _write_last_log(command: BlockcheckCommand, stdout: str, stderr: str) -> None:
    if not command.log_path:
        return
    command.log_path.parent.mkdir(parents=True, exist_ok=True)
    command.log_path.write_text(
        "".join(
            [
                command.to_text(),
                "\n\n===== STDOUT =====\n",
                stdout,
                "\n===== STDERR =====\n",
                stderr,
            ]
        ),
        encoding="utf-8",
    )


def execute_blockcheck_with_gui_sudo(
    root: Path | None = None,
    options: BlockcheckOptions | None = None,
) -> BlockcheckResult:
    """Run upstream blockcheck2.sh through graphical sudo askpass."""

    command = build_blockcheck_command(root=root, options=options)
    preflight = blockcheck_preflight(root)
    if not preflight.ok:
        missing = ", ".join(item.label for item in preflight.items if not item.ok)
        message = (
            "blockcheck preflight failed: "
            f"{missing}. Сначала соберите prerequisites кнопкой/CLI Blockcheck build "
            "или вручную выполните local build target all; sudo сейчас не запускался."
        )
        stderr = "\n\n".join([preflight.to_text(), message])
        _write_last_log(command, "", stderr)
        return BlockcheckResult(
            command=command,
            returncode=6,
            stdout="",
            stderr=stderr,
            summary_lines=(),
            skipped_reason=message,
        )
    if not is_sudo_available():
        return BlockcheckResult(
            command=command,
            returncode=127,
            stdout="",
            stderr="",
            summary_lines=(),
            skipped_reason="sudo не найден; GUI blockcheck требует sudo -A/SUDO_ASKPASS",
        )

    # These directories/helpers are created only for actual execution, not for
    # read-only preflight/plan rendering.
    (command.cwd / ".zap2" / "blockcheck" / "rw").mkdir(parents=True, exist_ok=True)
    if command.log_path:
        command.log_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_sudo_askpass_helper(command.cwd)

    env = _desktop_env_for_askpass(command)  # type: ignore[arg-type]
    env.setdefault("ZAP2_SUDO_ASKPASS_PROMPT", "Введите пароль sudo для Zap2 blockcheck")
    completed = subprocess.run(
        list(command.argv),
        cwd=command.cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=command.options.timeout_seconds,
        env=env,
    )
    stdout = completed.stdout
    stderr = completed.stderr
    if completed.returncode != 0 and "no askpass program" in stderr.lower():
        stderr += (
            "\n\nПодсказка: sudo не смог запустить SUDO_ASKPASS helper. "
            "Проверьте desktop-сессию DISPLAY/WAYLAND_DISPLAY."
        )
    _write_last_log(command, stdout, stderr)
    return BlockcheckResult(
        command=command,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        summary_lines=parse_blockcheck_summary(stdout),
    )


def last_blockcheck_log_to_text(root: Path | None = None) -> str:
    layout = discover_layout(root)
    log_path = layout.root / ".zap2" / "blockcheck" / "logs" / "last-blockcheck.txt"
    if not log_path.is_file():
        return "Blockcheck log отсутствует\nread-only: yes\nexecutes now: no"
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if len(text) > 80_000:
        return "... truncated ...\n" + text[-80_000:]
    return text
