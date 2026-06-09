"""GUI-facing blockcheck2 adapter for local strategy discovery.

The upstream ``blockcheck2.sh`` script is an interactive, privileged diagnostic
helper. This module turns a small, explicit subset into GUI/CLI objects without
running anything at import time. Execution still goes through graphical
``sudo -A`` askpass and is intentionally visible: the owner chooses the target
and starts the scan manually.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .build_dependencies import BuildDependencyReport, run_build_dependency_preflight
from .gui_privilege import _desktop_env_for_askpass, ensure_sudo_askpass_helper, is_sudo_available
from .local_build import LocalBuildPlan, create_local_build_plan, inspect_artifacts
from ..models.service_targets import DEFAULT_BLOCKCHECK_TARGET_STRING, normalize_service_targets
from ..project_paths import discover_layout

SUPPORTED_BLOCKCHECK_TESTS = ("standard", "custom")
SUPPORTED_BLOCKCHECK_SCANLEVELS = ("quick", "standard", "force")
SUPPORTED_BLOCKCHECK_IPVS = ("4", "6", "46")


@dataclass(frozen=True)
class BlockcheckWorkerIdentity:
    """UID/GID that upstream nfqws2 should use after dropping root."""

    uid: int
    gid: int
    source: str

    @property
    def pair(self) -> str:
        return f"{self.uid}:{self.gid}"


def _parse_nonnegative_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value, 10)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def current_blockcheck_worker_identity() -> BlockcheckWorkerIdentity:
    """Return the owner identity to pass as WS_UID/WS_GID to blockcheck2.

    ``blockcheck2.sh`` starts ``nfqws2`` as root and then asks it to drop
    privileges. Upstream defaults to ``WS_UID=1`` and ``WS_GID=3003``; that
    synthetic account often cannot traverse a user workspace under ``/home`` and
    therefore cannot read ``core/zapret2/lua/*.lua``. The GUI already knows the
    owner process identity before invoking ``sudo -A``, so we pass that identity
    explicitly and keep Lua file access aligned with the workspace owner.
    """

    sudo_uid = _parse_nonnegative_int(os.environ.get("SUDO_UID"))
    sudo_gid = _parse_nonnegative_int(os.environ.get("SUDO_GID"))
    if sudo_uid is not None and sudo_gid is not None:
        return BlockcheckWorkerIdentity(uid=sudo_uid, gid=sudo_gid, source="SUDO_UID/SUDO_GID")

    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    uid = int(getuid()) if getuid is not None else 0
    gid = int(getgid()) if getgid is not None else 0
    return BlockcheckWorkerIdentity(uid=uid, gid=gid, source="current process uid/gid")


@dataclass(frozen=True)
class BlockcheckOptions:
    """Owner-selected blockcheck2 scan parameters."""

    domains: str = DEFAULT_BLOCKCHECK_TARGET_STRING
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
    timeout_seconds: int = 0

    def normalized_domains(self) -> tuple[str, ...]:
        try:
            return normalize_service_targets(self.domains)
        except ValueError as exc:
            message = str(exc)
            if "requires at least one target" in message:
                raise ValueError("blockcheck требует хотя бы один домен или URI") from exc
            raise

    def for_single_domain(self, target: str) -> "BlockcheckOptions":
        """Return a copy constrained to one sequential blockcheck candidate."""

        return BlockcheckOptions(
            domains=target,
            test=self.test,
            scanlevel=self.scanlevel,
            ipvs=self.ipvs,
            enable_http=self.enable_http,
            enable_https_tls12=self.enable_https_tls12,
            enable_https_tls13=self.enable_https_tls13,
            enable_http3=self.enable_http3,
            skip_dnscheck=self.skip_dnscheck,
            repeats=self.repeats,
            curl_max_time=self.curl_max_time,
            timeout_seconds=self.timeout_seconds,
        )

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
        if self.timeout_seconds != 0 and not 30 <= self.timeout_seconds <= 3600:
            raise ValueError("overall timeout должен быть 0 (без общего лимита) или в диапазоне 30..3600 секунд")

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
class AvailableBlockcheckStrategy:
    """One concrete AVAILABLE nfqws2 strategy observed in blockcheck output."""

    probe: str
    ip_version: str
    target: str
    script: str
    command: str
    runtime_args: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedStrategyFile:
    """One strategy file generated from a blockcheck AVAILABLE result."""

    strategy_id: str
    path: Path
    source_probe: str
    source_target: str
    runtime_args: tuple[str, ...]


@dataclass(frozen=True)
class BlockcheckGeneratedStrategiesResult:
    """Result of converting blockcheck AVAILABLE results into catalog strategies."""

    source_log: Path
    target_label: str
    generated: tuple[GeneratedStrategyFile, ...]
    catalog_path: Path

    @property
    def ok(self) -> bool:
        return bool(self.generated)

    def to_text(self) -> str:
        lines = [
            "Blockcheck generated strategies",
            f"source log: {self.source_log}",
            f"target label: {self.target_label}",
            f"generated files: {len(self.generated)}",
            f"catalog: {self.catalog_path}",
        ]
        if not self.generated:
            lines.append("message: available strategies were not found in the latest successful blockcheck log")
        else:
            lines.append("generated strategy files:")
            for item in self.generated:
                lines.append(f"  - {item.strategy_id}: {item.path}")
                lines.append(f"    probe: {item.source_probe}; target: {item.source_target}; runtime args: {len(item.runtime_args)}")
            lines.extend(
                [
                    "next: open the Strategies tab, select one generated strategy for Default, then run Default workflow",
                    "executes now: no",
                    "mutates services/firewall now: no",
                    "mutates worktree/catalog now: yes",
                ]
            )
        return "\n".join(lines)


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
    script_env: dict[str, str] = field(default_factory=dict)
    log_path: Path | None = None
    backend: str = "sudo-askpass"
    worker_identity: BlockcheckWorkerIdentity | None = None

    @property
    def uses_sudo_askpass(self) -> bool:
        return self.backend == "sudo-askpass"

    def redacted_command_preview(self) -> str:
        return " ".join(self.argv)

    def to_text(self) -> str:
        display_env = self.script_env or self.options.to_env()
        env_lines = [f"  {key}={value}" for key, value in sorted(display_env.items())]
        worker = self.worker_identity
        worker_line = (
            f"blockcheck worker uid/gid: {worker.pair} ({worker.source})"
            if worker is not None
            else "blockcheck worker uid/gid: upstream default"
        )
        lines = [
            "Blockcheck GUI plan",
            f"domains: {', '.join(self.options.normalized_domains())}",
            f"test: {self.options.test}",
            f"scanlevel: {self.options.scanlevel}",
            f"ip versions: {self.options.ipvs}",
            f"cwd: {self.cwd}",
            f"log path: {self.log_path or 'не задан'}",
            worker_line,
            "uses sudo askpass: yes",
            "uses pkexec/polkit: no",
            "asks password in terminal: no",
            "stores password: no",
            "contains remote bootstrap: no",
            "contains upstream installer script: no",
            "mutates services persistently: no",
            "mutates firewall temporarily: yes, inside upstream blockcheck cleanup path",
            f"overall timeout: {'none; owner stops manually' if self.options.timeout_seconds == 0 else str(self.options.timeout_seconds) + ' seconds'}",
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
class BlockcheckRunStats:
    """Compact statistics extracted from partial or complete blockcheck output."""

    strategy_attempts: int
    available: int
    unavailable: int
    unknown: int
    port_connects: int
    port_failures: int
    top_unavailable_reasons: tuple[tuple[str, int], ...] = ()
    top_probes: tuple[tuple[str, int], ...] = ()
    top_scripts: tuple[tuple[str, int], ...] = ()
    infrastructure_notes: tuple[tuple[str, int], ...] = ()
    available_strategies: tuple[str, ...] = ()

    @property
    def port_precheck_dead(self) -> bool:
        """True when the observed target had no connectable TCP/443 candidates."""

        return self.port_failures > 0 and self.port_connects == 0

    @property
    def verdict(self) -> str:
        if self.port_precheck_dead:
            return "port-precheck-dead-target: strategy scan skipped/should be skipped"
        if self.available > 0:
            return "available-strategies-observed"
        if self.strategy_attempts > 0 and self.unavailable >= self.strategy_attempts - self.unknown:
            return "no-available-strategy-observed-yet"
        if self.has_observations:
            return "inconclusive"
        return "no-observations"

    @property
    def has_observations(self) -> bool:
        return any(
            (
                self.strategy_attempts,
                self.available,
                self.unavailable,
                self.unknown,
                self.port_connects,
                self.port_failures,
                self.infrastructure_notes,
            )
        )

    def to_text(self) -> str:
        lines = [
            "Blockcheck run statistics",
            f"strategy checks seen: {self.strategy_attempts}",
            f"available strategies: {self.available}",
            f"unavailable strategies: {self.unavailable}",
            f"in-progress/unknown checks: {self.unknown}",
            f"port precheck: connects={self.port_connects}; failed={self.port_failures}",
            f"verdict: {self.verdict}",
        ]
        if self.top_unavailable_reasons:
            lines.append("top unavailable reasons:")
            lines.extend(f"  - {reason}: {count}" for reason, count in self.top_unavailable_reasons)
        elif self.strategy_attempts:
            lines.append("top unavailable reasons: none observed yet")
        if self.top_probes:
            lines.append("top probes:")
            lines.extend(f"  - {probe}: {count}" for probe, count in self.top_probes)
        if self.top_scripts:
            lines.append("scripts seen:")
            lines.extend(f"  - {script}: {count}" for script, count in self.top_scripts)
        if self.infrastructure_notes:
            lines.append("infrastructure notes:")
            lines.extend(f"  - {note}: {count}" for note, count in self.infrastructure_notes)
        if self.available_strategies:
            lines.append("available strategy samples:")
            lines.extend(f"  - {strategy}" for strategy in self.available_strategies[:5])
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
        stats = parse_blockcheck_run_stats(self.stdout, self.stderr)
        if stats.has_observations:
            lines.extend(["", stats.to_text()])
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



class BlockcheckPreparationError(ValueError):
    """Raised when a GUI run must stop before starting sudo/QProcess."""

    def __init__(self, result: BlockcheckResult) -> None:
        super().__init__(result.to_text())
        self.result = result


@dataclass(frozen=True)
class PreparedBlockcheckExecution:
    """Fully prepared QProcess-compatible blockcheck execution context."""

    command: BlockcheckCommand
    env: dict[str, str]

    def start_text(self) -> str:
        return "\n".join(
            [
                "Blockcheck run: started",
                "mode: live QProcess streaming; GUI remains responsive",
                "overall timeout: none; use Stop to terminate intentionally",
                f"log path: {self.command.log_path or 'не задан'}",
                "",
                self.command.to_text(),
                "",
                "===== LIVE OUTPUT =====",
            ]
        )



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
            label="lua support files",
            path_or_command=str(core_root / "lua" / "zapret-lib.lua"),
            ok=(core_root / "lua" / "zapret-lib.lua").is_file() and (core_root / "lua" / "zapret-antidpi.lua").is_file(),
            hint="nfqws2 загружает lua после privilege drop; GUI передаёт WS_UID/WS_GID владельца workspace",
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
    worker_identity = current_blockcheck_worker_identity()

    env_assignments = {
        "ZAP2_GUI_PRIVILEGE_BRIDGE": "sudo-askpass",
        "ZAPRET_BASE": str(core_root),
        "ZAPRET_RW": str(rw_root),
        "ZAPRET_CONFIG": str(rw_root / "config"),
        "WS_UID": str(worker_identity.uid),
        "WS_GID": str(worker_identity.gid),
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
        script_env=env_assignments,
        log_path=log_path,
        worker_identity=worker_identity,
    )


def blockcheck_plan_to_text(root: Path | None = None, options: BlockcheckOptions | None = None) -> str:
    preflight = blockcheck_preflight(root)
    command = build_blockcheck_command(root=root, options=options)
    return "\n\n".join([preflight.to_text(), command.to_text()])



_STRATEGY_ATTEMPT_RE = re.compile(
    r"^-\s+(?P<probe>\S+)\s+(?P<ipver>ipv[46])\s+(?P<target>\S+)\s+:\s+(?P<strategy>nfqws2\b.*)$"
)
_SCRIPT_RE = re.compile(r"^\*\s+script\s+:\s+(?P<script>.+)$")
_CURL_ERROR_RE = re.compile(r"^curl:\s+\((?P<code>\d+)\)\s+(?P<message>.+)$")
_UNAVAILABLE_RE = re.compile(r"^UNAVAILABLE(?:\s+code=(?P<code>\d+))?")
_PORT_HEADER_RE = re.compile(r"^\*\s+port block tests\s+(?P<ipver>ipv[46])\s+(?P<target>\S+):(?P<port>\d+)$")
_PORT_RESULT_RE = re.compile(
    r"^(?P<address>[0-9A-Fa-f:.]+)\s+(?P<status>connects|does not connect\. netcat code \d+)"
)
_TEST_SECTION_RE = re.compile(r"^\*\s+curl_test_")


@dataclass
class BlockcheckPortPrecheckMonitor:
    """Live stdout monitor used by GUI to skip provably dead targets.

    It does not impose a wall-clock timeout. It only reacts to upstream evidence:
    once the port precheck for the active target has observed at least one failed
    address and zero connectable addresses, the following test/strategy section is
    a strong signal that continuing the strategy scan for this target is wasted.
    """

    target: str
    buffer: str = ""
    in_port_precheck: bool = False
    port_connects: int = 0
    port_failures: int = 0
    decided_reason: str = ""

    @property
    def dead_target(self) -> bool:
        return self.port_failures > 0 and self.port_connects == 0

    def feed_stdout(self, data: str) -> str:
        """Feed one stdout chunk and return a skip reason when one is proven."""

        if self.decided_reason:
            return self.decided_reason
        self.buffer += data
        if "\n" not in self.buffer:
            return ""
        *complete, self.buffer = self.buffer.split("\n")
        for raw_line in complete:
            reason = self.feed_line(raw_line)
            if reason:
                return reason
        return ""

    def feed_line(self, raw_line: str) -> str:
        line = raw_line.strip()
        if not line:
            return ""

        header = _PORT_HEADER_RE.match(line)
        if header:
            self.in_port_precheck = header.group("target") == self.target
            if self.in_port_precheck:
                self.port_connects = 0
                self.port_failures = 0
            return ""

        port_result = _PORT_RESULT_RE.match(line)
        if self.in_port_precheck and port_result:
            if port_result.group("status") == "connects":
                self.port_connects += 1
            else:
                self.port_failures += 1
            return ""

        if self.in_port_precheck and (
            _TEST_SECTION_RE.match(line)
            or _STRATEGY_ATTEMPT_RE.match(line)
            or line.startswith("preparing nfqws2 redirection")
        ):
            self.in_port_precheck = False
            if self.dead_target:
                self.decided_reason = (
                    f"port-precheck-dead-target for {self.target}: "
                    f"connects=0; failed={self.port_failures}; skipping strategy scan for this candidate"
                )
                return self.decided_reason
        return ""


def _normalize_curl_error(line: str) -> str | None:
    match = _CURL_ERROR_RE.match(line.strip())
    if not match:
        return None
    code = match.group("code")
    message = match.group("message").strip()
    lowered = message.lower()
    if code == "28" or "timed out" in lowered or "connection timed out" in lowered:
        return f"curl code {code}: connection timed out"
    if "could not resolve" in lowered:
        return f"curl code {code}: could not resolve host"
    if "ssl" in lowered or "certificate" in lowered:
        return f"curl code {code}: TLS/certificate failure"
    if "quic" in lowered or "http/3" in lowered:
        return f"curl code {code}: HTTP/3/QUIC failure"
    return f"curl code {code}: {message[:80]}"


def parse_blockcheck_run_stats(stdout: str, stderr: str = "") -> BlockcheckRunStats:
    """Parse partial blockcheck logs into compact progress statistics.

    The parser is intentionally conservative: it counts only strategy attempts
    printed as ``- curl_test... : nfqws2 ...``. Generic ``!!!!! AVAILABLE !!!!!``
    lines from IP/manual interpretation checks are ignored unless a strategy
    attempt is currently active.
    """

    attempts = available = unavailable = unknown = 0
    port_connects = port_failures = 0
    unavailable_reasons: Counter[str] = Counter()
    probes: Counter[str] = Counter()
    scripts: Counter[str] = Counter()
    infrastructure: Counter[str] = Counter()
    available_strategies: list[str] = []
    current_strategy: str | None = None
    current_probe: str | None = None
    current_error: str | None = None
    current_script = "<no script>"

    def close_current(status: str, reason: str | None = None) -> None:
        nonlocal current_strategy, current_probe, current_error, available, unavailable, unknown
        if current_strategy is None:
            return
        if status == "available":
            available += 1
            if current_strategy not in available_strategies:
                available_strategies.append(current_strategy)
        elif status == "unavailable":
            unavailable += 1
            unavailable_reasons[reason or current_error or "UNAVAILABLE"] += 1
        else:
            unknown += 1
        current_strategy = None
        current_probe = None
        current_error = None

    combined_lines = stdout.splitlines()
    for raw_line in combined_lines:
        line = raw_line.strip()
        if not line:
            continue

        script_match = _SCRIPT_RE.match(line)
        if script_match:
            current_script = script_match.group("script").strip()
            continue

        port_match = _PORT_RESULT_RE.match(line)
        if port_match:
            if port_match.group("status") == "connects":
                port_connects += 1
            else:
                port_failures += 1
            continue

        strategy_match = _STRATEGY_ATTEMPT_RE.match(line)
        if strategy_match:
            close_current("unknown")
            attempts += 1
            current_probe = f"{strategy_match.group('probe')} {strategy_match.group('ipver')} {strategy_match.group('target')}"
            current_strategy = strategy_match.group("strategy").strip()
            current_error = None
            probes[current_probe] += 1
            scripts[current_script] += 1
            continue

        normalized_error = _normalize_curl_error(line)
        if normalized_error and current_strategy is not None:
            current_error = normalized_error
            continue

        unavailable_match = _UNAVAILABLE_RE.match(line)
        if unavailable_match and current_strategy is not None:
            code = unavailable_match.group("code")
            fallback = f"UNAVAILABLE code={code}" if code else "UNAVAILABLE"
            close_current("unavailable", current_error or fallback)
            continue

        if "!!!!! AVAILABLE !!!!!" in line and current_strategy is not None:
            close_current("available")
            continue
        if "working strategy found" in line and current_strategy is not None:
            close_current("available")
            continue

    close_current("unknown")

    for raw_line in stderr.splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if not line:
            continue
        if "lua file" in lowered and "not accessible" in lowered:
            infrastructure["Lua support file not accessible"] += 1
        elif "qsettings::value: empty key" in lowered:
            infrastructure["Qt/QSettings empty key warning"] += 1
        elif "no askpass" in lowered:
            infrastructure["sudo askpass problem"] += 1

    return BlockcheckRunStats(
        strategy_attempts=attempts,
        available=available,
        unavailable=unavailable,
        unknown=unknown,
        port_connects=port_connects,
        port_failures=port_failures,
        top_unavailable_reasons=tuple(unavailable_reasons.most_common(5)),
        top_probes=tuple(probes.most_common(5)),
        top_scripts=tuple((script, count) for script, count in scripts.most_common(8) if script != "<no script>"),
        infrastructure_notes=tuple(infrastructure.most_common(5)),
        available_strategies=tuple(available_strategies[:10]),
    )

def _split_nfqws2_command(command: str) -> tuple[str, ...]:
    try:
        parts = tuple(shlex.split(command))
    except ValueError:
        parts = tuple(command.split())
    if parts and parts[0] == "nfqws2":
        return parts[1:]
    return parts


def _protocol_runtime_prefix(probe: str) -> tuple[str, ...]:
    lowered = probe.lower()
    if "http3" in lowered or "quic" in lowered:
        return ("--filter-udp=443", "--filter-l7=quic")
    if "https" in lowered or "tls" in lowered:
        return ("--filter-tcp=443", "--filter-l7=tls")
    if "http" in lowered:
        return ("--filter-tcp=80", "--filter-l7=http")
    return ("--filter-tcp=443",)


def _runtime_args_from_available_command(probe: str, command: str) -> tuple[str, ...]:
    raw_args = list(_split_nfqws2_command(command))
    args: list[str] = [
        "--lua-init=@core/zapret2/lua/zapret-lib.lua",
        "--lua-init=@core/zapret2/lua/zapret-antidpi.lua",
    ]
    existing_options = {item.split("=", 1)[0] for item in raw_args if item.startswith("--")}
    for item in _protocol_runtime_prefix(probe):
        option = item.split("=", 1)[0]
        if option not in existing_options:
            args.append(item)
    args.extend(raw_args)
    return tuple(args)


def parse_blockcheck_available_strategies(stdout: str) -> tuple[AvailableBlockcheckStrategy, ...]:
    """Extract concrete AVAILABLE strategy commands from blockcheck output."""

    current_command: str | None = None
    current_probe = ""
    current_ip_version = ""
    current_target = ""
    current_script = "<no script>"
    available: list[AvailableBlockcheckStrategy] = []
    seen_commands: set[str] = set()

    def mark_available() -> None:
        nonlocal current_command
        if current_command is None or current_command in seen_commands:
            current_command = None
            return
        seen_commands.add(current_command)
        available.append(
            AvailableBlockcheckStrategy(
                probe=current_probe,
                ip_version=current_ip_version,
                target=current_target,
                script=current_script,
                command=current_command,
                runtime_args=_runtime_args_from_available_command(current_probe, current_command),
            )
        )
        current_command = None

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        script_match = _SCRIPT_RE.match(line)
        if script_match:
            current_script = script_match.group("script").strip()
            continue
        strategy_match = _STRATEGY_ATTEMPT_RE.match(line)
        if strategy_match:
            current_probe = strategy_match.group("probe")
            current_ip_version = strategy_match.group("ipver")
            current_target = strategy_match.group("target")
            current_command = strategy_match.group("strategy").strip()
            continue
        if current_command is not None and ("!!!!! AVAILABLE !!!!!" in line or "working strategy found" in line):
            mark_available()
            continue
        if _UNAVAILABLE_RE.match(line):
            current_command = None
            continue
    return tuple(available)


def _last_blockcheck_log_path(root: Path | None = None) -> Path:
    layout = discover_layout(root)
    return layout.root / ".zap2" / "blockcheck" / "logs" / "last-blockcheck.txt"


def _successful_blockcheck_log_path(root: Path | None = None) -> Path:
    layout = discover_layout(root)
    return layout.root / ".zap2" / "blockcheck" / "logs" / "latest-successful-blockcheck.txt"


def _blockcheck_log_has_available_strategies(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    return bool(parse_blockcheck_available_strategies(text))


def _select_blockcheck_export_log(root: Path | None = None) -> Path:
    layout = discover_layout(root)
    successful = _successful_blockcheck_log_path(layout.root)
    last = _last_blockcheck_log_path(layout.root)
    if _blockcheck_log_has_available_strategies(successful):
        return successful
    if _blockcheck_log_has_available_strategies(last):
        return last
    return successful if successful.exists() else last


def _domains_from_blockcheck_log(text: str, fallback: str = "blockcheck") -> tuple[str, ...]:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("domains:"):
            raw_value = line.split(":", 1)[1]
            values = [item.strip() for item in raw_value.replace(",", " ").split() if item.strip()]
            if values:
                return tuple(values)
    return (fallback,)


def _slug(value: str, *, max_len: int = 48) -> str:
    cleaned = value.lower().replace("://", "-").replace("/", "-")
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", cleaned).strip("-._")
    cleaned = re.sub(r"[-_.]{2,}", "-", cleaned)
    return (cleaned or "blockcheck")[:max_len].strip("-._") or "blockcheck"


def _catalog_relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _update_strategy_catalog(catalog_path: Path, new_files: tuple[Path, ...], root: Path) -> None:
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    existing = [str(item) for item in data.get("strategyFiles", [])]
    for path in new_files:
        rel = _catalog_relative(path, root)
        if rel not in existing:
            existing.append(rel)
    data["strategyFiles"] = existing
    catalog_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _strategy_payload(
    *,
    strategy_id: str,
    title: str,
    summary: str,
    target_domains: tuple[str, ...],
    available: AvailableBlockcheckStrategy,
    source_log: Path,
    root: Path,
    index: int,
    generated_at: str,
) -> dict[str, object]:
    try:
        source_path = _catalog_relative(source_log, root)
    except ValueError:
        source_path = str(source_log)
    return {
        "schemaVersion": 1,
        "id": strategy_id,
        "title": title,
        "summary": summary,
        "philosophy": "blockcheck-generated-owner-choice",
        "intendedFor": [
            f"target: {', '.join(target_domains)}",
            "manual owner comparison of blockcheck-discovered AVAILABLE strategies",
            "Default workflow start after explicit selection in the Strategies tab",
        ],
        "workflow": ["blockcheck", "generate", "owner-selects", "plan", "owner-confirms", "execute-later"],
        "capabilities": {
            "readsProfiles": True,
            "readsHostlists": True,
            "usesLocalBuildPlan": True,
            "executesAutomatically": False,
            "requiresSudoAtStage7": False,
            "mutatesServicesOrFirewallAtStage7": False,
        },
        "runtimeArgs": list(available.runtime_args),
        "sourcePreset": {
            "engine": "nfqws2",
            "id": "blockcheck-generated",
            "name": "Blockcheck generated AVAILABLE strategy",
            "portingLevel": "generated-local-runtime-args",
            "sourcePath": source_path,
            "generatedAt": generated_at,
            "probe": available.probe,
            "ipVersion": available.ip_version,
            "target": available.target,
            "script": available.script,
            "availableIndex": index,
            "originalCommand": available.command,
            "windowsOptionsExecuted": False,
        },
        "notes": [
            "Generated from a concrete AVAILABLE line in the last Blockcheck lab log.",
            "The original nfqws2 command is preserved after base Lua init and protocol filter args.",
            "This file is catalog data only; choosing it does not start network changes until Default workflow is explicitly planned, confirmed and started.",
        ],
    }


def export_blockcheck_available_strategies(root: Path | None = None, max_strategies: int = 0) -> BlockcheckGeneratedStrategiesResult:
    """Convert AVAILABLE strategies from the last blockcheck log into catalog files."""

    layout = discover_layout(root)
    source_log = _select_blockcheck_export_log(layout.root)
    catalog_path = layout.root / "strategies" / "catalog.json"
    generated_dir = layout.root / "strategies" / "generated"
    if not source_log.is_file():
        raise ValueError(f"Успешный blockcheck log для экспорта не найден: {source_log}")
    text = source_log.read_text(encoding="utf-8", errors="replace")
    available = list(parse_blockcheck_available_strategies(text))
    if max_strategies > 0:
        available = available[:max_strategies]
    domains = _domains_from_blockcheck_log(text)
    target_label = _slug(domains[0])
    if not available:
        return BlockcheckGeneratedStrategiesResult(
            source_log=source_log,
            target_label=target_label,
            generated=(),
            catalog_path=catalog_path,
        )
    generated_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    stamp = datetime.fromtimestamp(source_log.stat().st_mtime, timezone.utc).strftime("%Y%m%d-%H%M%S")
    files: list[GeneratedStrategyFile] = []
    for index, item in enumerate(available, 1):
        strategy_id = f"blockcheck-{target_label}-{stamp}-{index:02d}"
        filename = f"{strategy_id}.json"
        path = generated_dir / filename
        title = f"Blockcheck {domains[0]} #{index:02d}"
        summary = f"Generated AVAILABLE strategy for {', '.join(domains)} from {item.probe} ({item.script})."
        payload = _strategy_payload(
            strategy_id=strategy_id,
            title=title,
            summary=summary,
            target_domains=domains,
            available=item,
            source_log=source_log,
            root=layout.root,
            index=index,
            generated_at=generated_at,
        )
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        files.append(
            GeneratedStrategyFile(
                strategy_id=strategy_id,
                path=path,
                source_probe=item.probe,
                source_target=item.target,
                runtime_args=item.runtime_args,
            )
        )
    _update_strategy_catalog(catalog_path, tuple(item.path for item in files), layout.root)
    return BlockcheckGeneratedStrategiesResult(
        source_log=source_log,
        target_label=target_label,
        generated=tuple(files),
        catalog_path=catalog_path,
    )


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


def write_blockcheck_last_log(command: BlockcheckCommand, stdout: str, stderr: str, footer: str = "") -> None:
    if not command.log_path:
        return
    command.log_path.parent.mkdir(parents=True, exist_ok=True)
    stats = parse_blockcheck_run_stats(stdout, stderr)
    parts = [
        command.to_text(),
        "\n\n===== STDOUT =====\n",
        stdout,
        "\n===== BLOCKCHECK RUN STATISTICS =====\n",
        stats.to_text(),
        "\n===== STDERR =====\n",
        stderr,
    ]
    if footer.strip():
        parts.extend(["\n===== GUI FINISH =====\n", footer.rstrip(), "\n"])
    text = "".join(parts)
    command.log_path.write_text(text, encoding="utf-8")

    # Keep a durable export source that is not overwritten by a later dead-target
    # or owner-stopped failed run. This turns Blockcheck lab into a safe pipeline:
    # the Export button reads the latest log that actually contains AVAILABLE
    # strategy attempts, not merely the last attempted candidate.
    if stats.available > 0:
        successful_path = command.log_path.with_name("latest-successful-blockcheck.txt")
        successful_path.write_text(text, encoding="utf-8")


def _preflight_failed_result(command: BlockcheckCommand, preflight: BlockcheckPreflight) -> BlockcheckResult:
    missing = ", ".join(item.label for item in preflight.items if not item.ok)
    message = (
        "blockcheck preflight failed: "
        f"{missing}. Сначала соберите prerequisites кнопкой/CLI Blockcheck build "
        "или вручную выполните local build target all; sudo сейчас не запускался."
    )
    stderr = "\n\n".join([preflight.to_text(), message])
    write_blockcheck_last_log(command, "", stderr)
    return BlockcheckResult(
        command=command,
        returncode=6,
        stdout="",
        stderr=stderr,
        summary_lines=(),
        skipped_reason=message,
    )


def _sudo_missing_result(command: BlockcheckCommand) -> BlockcheckResult:
    message = "sudo не найден; GUI blockcheck требует sudo -A/SUDO_ASKPASS"
    result = BlockcheckResult(
        command=command,
        returncode=127,
        stdout="",
        stderr="",
        summary_lines=(),
        skipped_reason=message,
    )
    write_blockcheck_last_log(command, "", result.to_text())
    return result


def prepare_blockcheck_execution(
    root: Path | None = None,
    options: BlockcheckOptions | None = None,
) -> PreparedBlockcheckExecution:
    """Prepare a privileged blockcheck run without blocking the GUI thread.

    The returned object is suitable for ``QProcess``: argv, cwd and desktop
    askpass environment are ready, but the process has not been started yet.
    Preflight failures are converted to ``BlockcheckPreparationError`` so GUI
    code can display the same user-facing text as the synchronous CLI path.
    """

    command = build_blockcheck_command(root=root, options=options)
    preflight = blockcheck_preflight(root)
    if not preflight.ok:
        raise BlockcheckPreparationError(_preflight_failed_result(command, preflight))
    if not is_sudo_available():
        raise BlockcheckPreparationError(_sudo_missing_result(command))

    (command.cwd / ".zap2" / "blockcheck" / "rw").mkdir(parents=True, exist_ok=True)
    if command.log_path:
        command.log_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_sudo_askpass_helper(command.cwd)

    env = _desktop_env_for_askpass(command)  # type: ignore[arg-type]
    env.setdefault("ZAP2_SUDO_ASKPASS_PROMPT", "Введите пароль sudo для Zap2 blockcheck")
    return PreparedBlockcheckExecution(command=command, env=env)


def execute_blockcheck_with_gui_sudo(
    root: Path | None = None,
    options: BlockcheckOptions | None = None,
) -> BlockcheckResult:
    """Run upstream blockcheck2.sh through graphical sudo askpass.

    This CLI-compatible path streams only after completion because it returns a
    dataclass result, but it deliberately has no arbitrary overall timeout by
    default. The PyQt page uses ``prepare_blockcheck_execution`` plus QProcess
    for live output and manual Stop.
    """

    try:
        prepared = prepare_blockcheck_execution(root=root, options=options)
    except BlockcheckPreparationError as exc:
        return exc.result

    timeout: int | None = None if prepared.command.options.timeout_seconds == 0 else prepared.command.options.timeout_seconds
    completed = subprocess.run(
        list(prepared.command.argv),
        cwd=prepared.command.cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
        env=prepared.env,
    )
    stdout = completed.stdout
    stderr = completed.stderr
    if completed.returncode != 0 and "no askpass program" in stderr.lower():
        stderr += (
            "\n\nПодсказка: sudo не смог запустить SUDO_ASKPASS helper. "
            "Проверьте desktop-сессию DISPLAY/WAYLAND_DISPLAY."
        )
    write_blockcheck_last_log(prepared.command, stdout, stderr)
    return BlockcheckResult(
        command=prepared.command,
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
