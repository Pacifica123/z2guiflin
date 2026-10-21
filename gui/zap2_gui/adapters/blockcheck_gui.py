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
import signal
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
from ..models.preset_labels import blockcheck_title, desync_functions
from ..models.service_targets import (
    DEFAULT_BLOCKCHECK_TARGET_STRING,
    DEFAULT_SERVICE_TARGET_PRESET_ID,
    SERVICE_TARGET_CUSTOM,
    SERVICE_COVERAGE_ANY_TARGET_AVAILABLE,
    SERVICE_COVERAGE_MAXIMIZE_TARGETS,
    SERVICE_COVERAGE_ORDERED_TARGET_CHAIN,
    get_service_target_preset,
    infer_service_target_preset_id,
    normalize_service_targets,
    service_target_coverage_policy_to_text,
    service_target_export_slug,
    service_target_host_token,
    service_target_layer_for_target,
    service_target_ordered_targets,
    service_target_phase_chain,
    service_target_policy,
    service_target_recommended_scan_mode,
    service_target_title,
)
from ..project_paths import discover_layout

SUPPORTED_BLOCKCHECK_TESTS = ("standard", "custom")
SUPPORTED_BLOCKCHECK_SCANLEVELS = ("quick", "standard", "force")
SUPPORTED_BLOCKCHECK_IPVS = ("4", "6", "46")
BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE = "stop-after-first-available"
BLOCKCHECK_SCAN_ALL_TARGETS = "scan-all-targets"
BLOCKCHECK_SCAN_SKIP_DEAD_ONLY = "skip-dead-targets-only"
BLOCKCHECK_DEAD_TARGET_GUARD_AUTO_STOP = "auto-stop"
BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY = "observe-only"
SUPPORTED_BLOCKCHECK_DEAD_TARGET_GUARDS = (
    BLOCKCHECK_DEAD_TARGET_GUARD_AUTO_STOP,
    BLOCKCHECK_DEAD_TARGET_GUARD_OBSERVE_ONLY,
)
SUPPORTED_BLOCKCHECK_SCAN_MODES = (
    BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE,
    BLOCKCHECK_SCAN_ALL_TARGETS,
    BLOCKCHECK_SCAN_SKIP_DEAD_ONLY,
)


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


def request_blockcheck_graceful_stop(process: object) -> bool:
    """Попросить upstream Blockcheck завершиться через SIGINT и выполнить cleanup.

    GUI запускает ``sudo -A ... blockcheck2.sh`` как QProcess. Upstream script
    обрабатывает SIGINT своим cleanup-handler, но не гарантирует такую же
    обработку SIGTERM от ``QProcess.terminate()``. Поэтому обычная остановка
    сначала посылает SIGINT в pid wrapper-процесса; sudo передаёт сигнал
    выполняемой команде. ``False`` означает, что вызывающий код должен перейти
    к аварийному fallback.
    """

    process_id = getattr(process, "processId", None)
    if not callable(process_id):
        return False
    try:
        pid = int(process_id())
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, signal.SIGINT)
    except OSError:
        return False
    return True


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


# blockcheck2 1.0.6 CURL_PAD: junk "X-Pad-NNNN:" headers grow every curl
# request so a TSPU-style "16 KB" block (total bytes per flow) can be
# triggered without a large page on the target. Bounded: 0 = off.
BLOCKCHECK_CURL_PAD_MIN = 1024
BLOCKCHECK_CURL_PAD_MAX = 65536
BLOCKCHECK_CURL_PAD_SUGGESTED = 20000

_COVERAGE_ROW_RE = re.compile(r"^(\d+)/(\d+) : (.+)$")


@dataclass(frozen=True)
class BlockcheckCoverageRow:
    """One line of the blockcheck2 1.0.6 ``* COVERAGE`` section."""

    strategy: str
    worked: int
    total: int

    def to_dict(self) -> dict[str, object]:
        return {"strategy": self.strategy, "worked": self.worked, "total": self.total}


def parse_blockcheck_coverage(stdout: str) -> tuple[BlockcheckCoverageRow, ...]:
    """Parse ``* COVERAGE`` lines (``worked/total : strategy``) from blockcheck2 output.

    Format comes from ``result_coverage_print`` in core/zapret2/blockcheck2.sh.
    The section is printed only when more than one domain was tested.
    """

    rows: list[BlockcheckCoverageRow] = []
    in_section = False
    for raw in stdout.splitlines():
        line = raw.strip()
        if line == "* COVERAGE":
            in_section = True
            rows = []
            continue
        if not in_section:
            continue
        match = _COVERAGE_ROW_RE.match(line)
        if match is None:
            if rows or line.startswith("* "):
                in_section = False
            continue
        rows.append(BlockcheckCoverageRow(strategy=match.group(3).strip(), worked=int(match.group(1)), total=int(match.group(2))))
    return tuple(rows)


def blockcheck_coverage_rows_to_text(rows: tuple[BlockcheckCoverageRow, ...]) -> str:
    if not rows:
        return ""
    lines = ["COVERAGE (стратегия сработала для N из M доменов; надёжно только при SCANLEVEL=force):"]
    lines.extend(f"- {row.worked}/{row.total} : {row.strategy}" for row in rows)
    return "\n".join(lines)


@dataclass(frozen=True)
class BlockcheckOptions:
    """Owner-selected blockcheck2 scan parameters."""

    domains: str = DEFAULT_BLOCKCHECK_TARGET_STRING
    service_target_preset_id: str = DEFAULT_SERVICE_TARGET_PRESET_ID
    scan_mode: str = BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE
    test: str = "standard"
    scanlevel: str = "quick"
    ipvs: str = "4"
    enable_http: bool = False
    enable_https_tls12: bool = True
    enable_https_tls13: bool = True
    enable_http3: bool = True
    skip_dnscheck: bool = False
    repeats: int = 1
    curl_max_time: int = 3
    timeout_seconds: int = 0
    dead_target_guard: str = BLOCKCHECK_DEAD_TARGET_GUARD_AUTO_STOP
    custom_list_env: tuple[tuple[str, str], ...] = ()
    curl_pad: int = 0

    def normalized_domains(self) -> tuple[str, ...]:
        try:
            return normalize_service_targets(self.domains)
        except ValueError as exc:
            message = str(exc)
            if "requires at least one target" in message:
                raise ValueError("blockcheck требует хотя бы один домен или URI") from exc
            raise

    def ordered_domains_for_policy(self) -> tuple[str, ...]:
        """Return domains in the service policy order used by sequential GUI runs."""

        domains = self.normalized_domains()
        if self.service_target_preset_id == SERVICE_TARGET_CUSTOM:
            return domains
        try:
            preset_order = service_target_ordered_targets(self.service_target_preset_id)
        except ValueError:
            return domains
        if set(item.lower() for item in domains) != set(item.lower() for item in preset_order):
            return domains
        positions = {target.lower(): index for index, target in enumerate(preset_order)}
        return tuple(sorted(domains, key=lambda item: positions.get(item.lower(), len(positions))))

    def service_coverage_policy(self):
        return service_target_policy(self.service_target_preset_id)

    def for_single_domain(self, target: str) -> "BlockcheckOptions":
        """Return a copy constrained to one sequential blockcheck candidate."""

        return BlockcheckOptions(
            domains=target,
            service_target_preset_id=self.service_target_preset_id,
            scan_mode=self.scan_mode,
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
            dead_target_guard=self.dead_target_guard,
            custom_list_env=self.custom_list_env,
            curl_pad=self.curl_pad,
        )

    def validate(self) -> None:
        self.normalized_domains()
        get_service_target_preset(self.service_target_preset_id)
        if self.scan_mode not in SUPPORTED_BLOCKCHECK_SCAN_MODES:
            raise ValueError(f"Неподдерживаемый scan mode: {self.scan_mode}")
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
        if self.curl_pad != 0 and not BLOCKCHECK_CURL_PAD_MIN <= self.curl_pad <= BLOCKCHECK_CURL_PAD_MAX:
            raise ValueError(
                f"CURL_PAD должен быть 0 (выкл.) или в диапазоне {BLOCKCHECK_CURL_PAD_MIN}..{BLOCKCHECK_CURL_PAD_MAX} байт"
            )
        if self.dead_target_guard not in SUPPORTED_BLOCKCHECK_DEAD_TARGET_GUARDS:
            raise ValueError(f"Неподдерживаемый dead-target guard: {self.dead_target_guard}")
        allowed_custom_keys = {"LIST_HTTP", "LIST_HTTPS_TLS12", "LIST_HTTPS_TLS13", "LIST_QUIC", "ZAP2_TOURNAMENT_STRATEGY_ID"}
        for key, value in self.custom_list_env:
            if key not in allowed_custom_keys:
                raise ValueError(f"unsupported blockcheck custom env key: {key}")
            if not str(value).strip():
                raise ValueError(f"empty blockcheck custom env value for {key}")

    def to_env(self) -> dict[str, str]:
        self.validate()
        policy = self.service_coverage_policy()
        env = {
            "BATCH": "1",
            "TEST": self.test,
            "DOMAINS": " ".join(self.normalized_domains()),
            "ZAP2_SERVICE_TARGET_PRESET": self.service_target_preset_id,
            "ZAP2_SERVICE_COVERAGE_POLICY": policy.mode,
            "ZAP2_SERVICE_COVERAGE_ORDER_MODE": policy.order_mode,
            "ZAP2_BLOCKCHECK_SCAN_MODE": self.scan_mode,
            "ZAP2_DEAD_TARGET_GUARD": self.dead_target_guard,
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
        if self.curl_pad > 0:
            env["CURL_PAD"] = str(self.curl_pad)
        env.update({key: value for key, value in self.custom_list_env})
        return env




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
    service_target_preset_id: str
    coverage_status: str = "single-target"
    runtime_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlockcheckStrategyValidationLists:
    """Custom blockcheck list files containing exactly one strategy candidate."""

    strategy_id: str
    root_dir: Path
    strategy_line: str
    env_items: tuple[tuple[str, str], ...]

    def to_text(self) -> str:
        lines = [
            "Blockcheck one-strategy validation lists",
            f"strategy: {self.strategy_id}",
            f"root: {self.root_dir}",
            f"strategy line: {self.strategy_line}",
            "env:",
        ]
        lines.extend(f"  {key}={value}" for key, value in self.env_items)
        lines.extend([
            "purpose: upstream custom test sees one nfqws2 candidate, so tournament validation is one-strategy-at-a-time",
            "executes now: no",
            "mutates services/firewall now: no",
            "mutates worktree now: yes",
        ])
        return "\n".join(lines)


@dataclass(frozen=True)
class BlockcheckGeneratedStrategiesResult:
    """Result of converting blockcheck AVAILABLE results into catalog strategies."""

    source_log: Path
    target_label: str
    service_target_preset_id: str
    generated: tuple[GeneratedStrategyFile, ...]
    catalog_path: Path
    source_logs: tuple[Path, ...] = ()

    @property
    def ok(self) -> bool:
        return bool(self.generated)

    def to_text(self) -> str:
        lines = [
            "Blockcheck generated strategies",
            f"source log: {self.source_log}",
            f"source logs: {len(self.source_logs) if self.source_logs else 1}",
            f"target label: {self.target_label}",
            f"service target preset: {self.service_target_preset_id}",
            f"generated files: {len(self.generated)}",
            f"catalog: {self.catalog_path}",
        ]
        if not self.generated:
            lines.append("message: available strategies were not found in the latest successful blockcheck log")
        else:
            lines.append("generated strategy files:")
            for item in self.generated:
                lines.append(f"  - {item.strategy_id}: {item.path}")
                lines.append(f"    probe: {item.source_probe}; target: {item.source_target}; coverage: {item.coverage_status}; runtime args: {len(item.runtime_args)}")
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
    candidate_log_path: Path | None = None
    coverage_manifest_path: Path | None = None
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
        policy = self.options.service_coverage_policy()
        lines = [
            "Blockcheck GUI plan",
            f"domains: {', '.join(self.options.normalized_domains())}",
            f"ordered domains: {', '.join(self.options.ordered_domains_for_policy())}",
            f"service target preset: {self.options.service_target_preset_id} ({get_service_target_preset(self.options.service_target_preset_id).title})",
            f"service coverage policy: {policy.mode}; order: {policy.order_mode}",
            f"candidate scan mode: {self.options.scan_mode}",
            f"dead-target guard: {self.options.dead_target_guard}",
            f"test: {self.options.test}",
            f"scanlevel: {self.options.scanlevel}",
            f"ip versions: {self.options.ipvs}",
            f"cwd: {self.cwd}",
            f"log path: {self.log_path or 'не задан'}",
            f"candidate log path: {self.candidate_log_path or 'не задан'}",
            f"coverage manifest: {self.coverage_manifest_path or 'не задан'}",
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
        coverage_text = blockcheck_coverage_rows_to_text(parse_blockcheck_coverage(self.stdout))
        if coverage_text:
            lines.extend(["", coverage_text])
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
                f"candidate log path: {self.command.candidate_log_path or 'не задан'}",
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
            label="target DNS guard",
            path_or_command=str(layout.root / "tools" / "blockcheck_target_preflight.sh"),
            ok=(layout.root / "tools" / "blockcheck_target_preflight.sh").is_file(),
            hint="локальный read-only wrapper проверяет mdig для выбранного target до upstream firewall mutation",
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
    coverage_manifest_path = logs_root / "candidates" / "coverage-manifest.json"
    candidate_log_path = None
    normalized_domains = opts.normalized_domains()
    if len(normalized_domains) == 1:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        candidate_log_path = logs_root / "candidates" / f"{stamp}-{_slug(opts.service_target_preset_id, max_len=32)}-{_slug(normalized_domains[0], max_len=64)}.txt"
    askpass = _planned_askpass_script_path(layout.root)
    worker_identity = current_blockcheck_worker_identity()

    env_assignments = {
        "ZAP2_GUI_PRIVILEGE_BRIDGE": "sudo-askpass",
        "ZAPRET_BASE": str(core_root),
        "ZAPRET_RW": str(rw_root),
        "ZAPRET_CONFIG": str(rw_root / "config"),
        "WS_UID": str(worker_identity.uid),
        "WS_GID": str(worker_identity.gid),
        "ZAP2_BLOCKCHECK_SCRIPT": str(script),
        "ZAP2_TARGET_HOSTS": " ".join(service_target_host_token(item) for item in opts.normalized_domains()),
        **opts.to_env(),
    }
    env_argv = tuple(f"{key}={value}" for key, value in sorted(env_assignments.items()))
    argv = (
        "sudo",
        "-A",
        "env",
        *env_argv,
        "/bin/sh",
        str(layout.root / "tools" / "blockcheck_target_preflight.sh"),
    )
    return BlockcheckCommand(
        options=opts,
        argv=argv,
        cwd=layout.root,
        env_overrides={"SUDO_ASKPASS": str(askpass)},
        script_env=env_assignments,
        log_path=log_path,
        candidate_log_path=candidate_log_path,
        coverage_manifest_path=coverage_manifest_path,
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

def _coverage_status_from_stats(stats: BlockcheckRunStats) -> str:
    if stats.available > 0:
        return "available"
    if stats.port_precheck_dead:
        return "dead-target"
    if stats.strategy_attempts > 0 and stats.unknown == 0:
        return "unavailable"
    if stats.has_observations:
        return "unknown"
    return "not-tested"


def _json_rel_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _target_coverage_template(preset_id: str, observed_targets: tuple[str, ...]) -> dict[str, dict[str, object]]:
    try:
        preset = get_service_target_preset(preset_id)
    except ValueError:
        preset = get_service_target_preset(SERVICE_TARGET_CUSTOM)
    targets = preset.targets if not preset.is_custom else observed_targets
    coverage: dict[str, dict[str, object]] = {}
    for target in targets:
        coverage[str(target)] = {
            "target": str(target),
            "status": "not-tested",
            "availableStrategies": 0,
            "strategyChecks": 0,
            "lastLog": "",
            "updatedAt": "",
        }
    for target in observed_targets:
        coverage.setdefault(
            str(target),
            {
                "target": str(target),
                "status": "not-tested",
                "availableStrategies": 0,
                "strategyChecks": 0,
                "lastLog": "",
                "updatedAt": "",
            },
        )
    return coverage


def _summarize_coverage_targets(targets: dict[str, dict[str, object]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in targets.values():
        counts[str(item.get("status") or "unknown")] += 1
    return dict(sorted(counts.items()))


def _read_coverage_manifest(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _update_blockcheck_coverage_manifest(command: BlockcheckCommand, stats: BlockcheckRunStats, text: str) -> None:
    if command.coverage_manifest_path is None or command.candidate_log_path is None:
        return
    try:
        targets = command.options.normalized_domains()
    except ValueError:
        return
    if len(targets) != 1:
        return
    target = targets[0]
    manifest_path = command.coverage_manifest_path
    root = command.cwd
    preset_id = command.options.service_target_preset_id
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    existing = _read_coverage_manifest(manifest_path)
    policy = command.options.service_coverage_policy()
    if existing and existing.get("serviceTargetPresetId") == preset_id:
        data = dict(existing)
        raw_targets = data.get("targets") if isinstance(data.get("targets"), dict) else {}
        coverage = _target_coverage_template(preset_id, tuple(str(key) for key in raw_targets))
        for key, value in raw_targets.items():
            if isinstance(value, dict):
                coverage[str(key)] = dict(value)
    else:
        data = {
            "schemaVersion": 1,
            "serviceTargetPresetId": preset_id,
            "serviceTargetTitle": service_target_title(preset_id),
            "coveragePolicy": policy.mode,
            "coverageOrderMode": policy.order_mode,
            "recommendedScanMode": policy.recommended_scan_mode,
            "stopRule": policy.stop_rule,
            "scanMode": command.options.scan_mode,
            "createdAt": now,
            "targets": {},
        }
        coverage = _target_coverage_template(preset_id, targets)

    candidate_rel = _json_rel_path(command.candidate_log_path, root)
    coverage[target] = {
        "target": target,
        "status": _coverage_status_from_stats(stats),
        "availableStrategies": stats.available,
        "strategyChecks": stats.strategy_attempts,
        "unavailableStrategies": stats.unavailable,
        "unknownStrategies": stats.unknown,
        "portConnects": stats.port_connects,
        "portFailures": stats.port_failures,
        "verdict": stats.verdict,
        "lastLog": candidate_rel,
        "updatedAt": now,
    }
    data["updatedAt"] = now
    data["coveragePolicy"] = policy.mode
    data["coverageOrderMode"] = policy.order_mode
    data["recommendedScanMode"] = policy.recommended_scan_mode
    data["stopRule"] = policy.stop_rule
    data["scanMode"] = command.options.scan_mode
    data["targets"] = coverage
    data["summary"] = _summarize_coverage_targets(coverage)
    data["phases"] = list(_coverage_phases_in_policy_order(data, preset_id))
    data["notes"] = [
        "Coverage is interpreted through the service coverage policy, not only by raw target count.",
        "Stage 7b treats service phases as AND and targets inside one phase as OR alternatives.",
        "Strategy tournament semantics are record-holder based: one strategy is validated through phases until it fails or reaches full coverage.",
    ]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def blockcheck_coverage_manifest_path(root: Path | None = None) -> Path:
    layout = discover_layout(root)
    return layout.root / ".zap2" / "blockcheck" / "logs" / "candidates" / "coverage-manifest.json"


def blockcheck_coverage_to_text(root: Path | None = None) -> str:
    path = blockcheck_coverage_manifest_path(root)
    data = _read_coverage_manifest(path)
    if not data:
        return "Blockcheck target coverage\nmanifest: отсутствует\nread-only: yes\nexecutes now: no"
    targets = data.get("targets") if isinstance(data.get("targets"), dict) else {}
    lines = [
        "Blockcheck target coverage",
        f"manifest: {path}",
        f"service target preset: {data.get('serviceTargetPresetId', 'unknown')} ({data.get('serviceTargetTitle', 'unknown')})",
        f"coverage policy: {data.get('coveragePolicy', 'unknown')}; order: {data.get('coverageOrderMode', 'unknown')}",
        f"recommended scan mode: {data.get('recommendedScanMode', 'unknown')}",
        f"scan mode: {data.get('scanMode', 'unknown')}",
        f"updated at: {data.get('updatedAt', '')}",
        "targets:",
    ]
    for target, item in targets.items():
        if not isinstance(item, dict):
            continue
        lines.append(
            "  - "
            f"{target}: {item.get('status', 'unknown')} "
            f"(available={item.get('availableStrategies', 0)}; checks={item.get('strategyChecks', 0)}; log={item.get('lastLog', '')})"
        )
    phases = data.get("phases") if isinstance(data.get("phases"), list) else []
    if phases:
        lines.append("phases: AND between phases, OR between targets inside a phase")
        for phase in phases:
            if not isinstance(phase, dict):
                continue
            targets_label = ", ".join(
                str(item.get("target") or "")
                for item in phase.get("targets", [])
                if isinstance(item, dict)
            )
            lines.append(
                "  - "
                f"{phase.get('phaseId', 'unknown')}: {phase.get('status', 'unknown')} "
                f"({targets_label})"
            )
    lines.extend(["read-only: yes", "executes now: no", "mutates services/firewall now: no"])
    return "\n".join(lines)




def blockcheck_service_policy_to_text(preset_id: str = DEFAULT_SERVICE_TARGET_PRESET_ID) -> str:
    """Show the universal coverage semantics attached to one service preset."""

    return service_target_coverage_policy_to_text(preset_id)


def _coverage_items_in_policy_order(data: dict[str, object], preset_id: str) -> tuple[dict[str, object], ...]:
    targets = data.get("targets") if isinstance(data.get("targets"), dict) else {}
    try:
        ordered = service_target_ordered_targets(preset_id)
    except ValueError:
        ordered = tuple(str(key) for key in targets)
    rows: list[dict[str, object]] = []
    for target in ordered:
        item = targets.get(target) if isinstance(targets, dict) else None
        if isinstance(item, dict):
            rows.append(dict(item))
        else:
            rows.append({
                "target": target,
                "status": "not-tested",
                "availableStrategies": 0,
                "strategyChecks": 0,
                "lastLog": "",
                "updatedAt": "",
            })
    for target, item in targets.items() if isinstance(targets, dict) else ():
        if str(target) not in {str(row.get("target")) for row in rows} and isinstance(item, dict):
            rows.append(dict(item))
    return tuple(rows)


def _status_available(row: dict[str, object]) -> bool:
    return str(row.get("status") or "") == "available"


def _phase_status_for_rows(rows: tuple[dict[str, object], ...]) -> tuple[str, dict[str, object] | None]:
    """Return phase status using OR semantics for target alternatives."""

    if any(_status_available(row) for row in rows):
        winner = next(row for row in rows if _status_available(row))
        return "passed", winner
    if not rows or all(str(row.get("status") or "not-tested") == "not-tested" for row in rows):
        return "not-tested", rows[0] if rows else None
    if any(str(row.get("status") or "") == "not-tested" for row in rows):
        return "pending", next((row for row in rows if str(row.get("status") or "") == "not-tested"), rows[0])
    return "blocked", rows[0] if rows else None


def _coverage_phases_in_policy_order(data: dict[str, object], preset_id: str) -> tuple[dict[str, object], ...]:
    rows_by_target = {str(row.get("target") or ""): row for row in _coverage_items_in_policy_order(data, preset_id)}
    phases: list[dict[str, object]] = []
    try:
        chain = service_target_phase_chain(preset_id)
    except ValueError:
        return ()
    for phase in chain:
        target_rows = tuple(
            rows_by_target.get(
                target,
                {
                    "target": target,
                    "status": "not-tested",
                    "availableStrategies": 0,
                    "strategyChecks": 0,
                    "lastLog": "",
                },
            )
            for target in phase.targets
        )
        status, winner = _phase_status_for_rows(target_rows)
        phases.append(
            {
                "phaseId": phase.phase_id,
                "title": phase.title,
                "status": status,
                "required": phase.required,
                "targets": list(target_rows),
                "winner": winner or {},
                "summary": phase.summary,
            }
        )
    return tuple(phases)


def _phase_passed(phase: dict[str, object]) -> bool:
    return str(phase.get("status") or "") == "passed"


def blockcheck_tournament_to_text(root: Path | None = None, preset_id: str | None = None) -> str:
    """Render a read-only service coverage tournament snapshot.

    Stage 7b makes the tournament semantics explicit: strategies are record
    candidates, phases are AND, and target alternatives inside one phase are OR.
    The manifest is still per-target evidence; actual one-strategy validation is
    prepared by the custom-list helpers and recorded as best-so-far evidence once
    the owner runs it.
    """

    path = blockcheck_coverage_manifest_path(root)
    data = _read_coverage_manifest(path) or {}
    effective_preset_id = preset_id or str(data.get("serviceTargetPresetId") or DEFAULT_SERVICE_TARGET_PRESET_ID)
    preset = get_service_target_preset(effective_preset_id)
    policy = preset.policy
    rows = _coverage_items_in_policy_order(data, effective_preset_id) if data else tuple(
        {
            "target": target,
            "status": "not-tested",
            "availableStrategies": 0,
            "strategyChecks": 0,
            "lastLog": "",
        }
        for target in (preset.ordered_targets_for_policy() if not preset.is_custom else ())
    )
    phases = _coverage_phases_in_policy_order(data, effective_preset_id) if data else tuple(
        {
            "phaseId": phase.phase_id,
            "title": phase.title,
            "status": "not-tested",
            "required": phase.required,
            "targets": [
                {
                    "target": target,
                    "status": "not-tested",
                    "availableStrategies": 0,
                    "strategyChecks": 0,
                    "lastLog": "",
                }
                for target in phase.targets
            ],
            "winner": {},
            "summary": phase.summary,
        }
        for phase in (preset.phase_chain_for_policy() if not preset.is_custom else ())
    )
    available_rows = tuple(row for row in rows if _status_available(row))
    total_targets = len(rows)
    available_count = len(available_rows)
    required_phases = tuple(phase for phase in phases if bool(phase.get("required", True)))
    phase_passed_count = sum(1 for phase in required_phases if _phase_passed(phase))
    phase_prefix = 0
    first_blocker: dict[str, object] | None = None
    if policy.mode == SERVICE_COVERAGE_ORDERED_TARGET_CHAIN:
        for phase in required_phases:
            if _phase_passed(phase):
                phase_prefix += 1
                continue
            first_blocker = phase
            break
    success = False
    if policy.mode == SERVICE_COVERAGE_ANY_TARGET_AVAILABLE:
        success = available_count > 0
    elif policy.mode == SERVICE_COVERAGE_MAXIMIZE_TARGETS:
        success = total_targets > 0 and available_count == total_targets
    elif policy.mode == SERVICE_COVERAGE_ORDERED_TARGET_CHAIN:
        success = bool(required_phases) and phase_passed_count == len(required_phases)

    lines = [
        "Blockcheck service coverage tournament",
        f"manifest: {path if data else 'absent'}",
        f"preset: {preset.preset_id} ({preset.title})",
        f"coverage policy: {policy.mode}",
        f"order mode: {policy.order_mode}",
        f"recommended scan mode: {policy.recommended_scan_mode}",
        f"stop rule: {policy.stop_rule}",
        "strategy loop: one strategy at a time; a candidate advances phase-by-phase until it fails or covers the full chain",
        "phase logic: phases use AND; targets inside the same phase use OR",
        f"score: {available_count}/{total_targets} available",
        f"target score: {available_count}/{total_targets} available",
    ]
    if phases:
        lines.append(f"phase score: {phase_passed_count}/{len(required_phases)} required phases passed")
    if policy.mode == SERVICE_COVERAGE_ORDERED_TARGET_CHAIN:
        lines.append(f"phase prefix: {phase_prefix}/{len(required_phases)}")
        if first_blocker is not None:
            alternatives = ", ".join(
                f"{row.get('target')}={row.get('status', 'unknown')}"
                for row in first_blocker.get("targets", [])
                if isinstance(row, dict)
            )
            lines.append(
                "first blocker phase: "
                f"{first_blocker.get('phaseId')} ({first_blocker.get('status', 'unknown')}; {alternatives})"
            )
    elif policy.mode == SERVICE_COVERAGE_ANY_TARGET_AVAILABLE:
        lines.append(f"any-target success: {'yes' if available_count else 'no'}")
    lines.append(f"full coverage: {'yes' if success else 'no'}")
    if phases:
        lines.append("phases in policy order:")
        for index, phase in enumerate(phases, 1):
            alternatives = []
            for row in phase.get("targets", []):
                if isinstance(row, dict):
                    alternatives.append(
                        f"{row.get('target')}={row.get('status', 'unknown')}"
                        f"/available:{row.get('availableStrategies', 0)}"
                    )
            winner = phase.get("winner") if isinstance(phase.get("winner"), dict) else {}
            winner_label = str(winner.get("target") or "") if winner else ""
            suffix = f"; winner={winner_label}" if winner_label else ""
            lines.append(
                "  - "
                f"{index}. {phase.get('phaseId')} ({phase.get('title')}): {phase.get('status', 'unknown')}"
                f"{suffix}; alternatives: {', '.join(alternatives)}"
            )
    lines.append("targets in policy order:")
    for index, row in enumerate(rows, 1):
        target = str(row.get("target") or "")
        layer = service_target_layer_for_target(preset.preset_id, target) if target else "unknown"
        lines.append(
            "  - "
            f"{index}. {target}: {row.get('status', 'unknown')} "
            f"[{layer}; available={row.get('availableStrategies', 0)}; checks={row.get('strategyChecks', 0)}; log={row.get('lastLog', '')}]"
        )
    lines.extend([
        "record-holder interpretation:",
        "  - any-target-available: simple services such as YouTube may use the first working target as a useful candidate.",
        "  - ordered-target-chain: desktop-style services such as Discord should validate one strategy through phases and keep only the current record-holder plus optional former records.",
        "  - Stage 7b fixes the model from raw domain coverage to phase-aware strategy tournament semantics; automated candidate validation uses custom one-strategy lists rather than N-per-target buckets.",
        "read-only: yes",
        "executes now: no",
        "mutates services/firewall now: no",
    ])
    return "\n".join(lines)


def _coverage_rows_for_strategy(root: Path, service_target_preset_id: str, source_target: str) -> tuple[dict[str, object], ...]:
    manifest = _read_coverage_manifest(blockcheck_coverage_manifest_path(root))
    if not manifest or manifest.get("serviceTargetPresetId") != service_target_preset_id:
        return ({"target": source_target, "status": "available", "source": "single-log"},)
    targets = manifest.get("targets") if isinstance(manifest.get("targets"), dict) else {}
    rows: list[dict[str, object]] = []
    for target, item in targets.items():
        if isinstance(item, dict):
            rows.append(
                {
                    "target": str(target),
                    "status": str(item.get("status") or "unknown"),
                    "availableStrategies": int(item.get("availableStrategies") or 0),
                    "strategyChecks": int(item.get("strategyChecks") or 0),
                    "lastLog": str(item.get("lastLog") or ""),
                }
            )
    return tuple(rows or ({"target": source_target, "status": "available", "source": "single-log"},))


def _coverage_status_for_target(root: Path, service_target_preset_id: str, target: str) -> str:
    for row in _coverage_rows_for_strategy(root, service_target_preset_id, target):
        if str(row.get("target")) == target:
            return str(row.get("status") or "unknown")
    return "unknown"


def _candidate_export_logs_from_manifest(root: Path) -> tuple[Path, ...]:
    manifest = _read_coverage_manifest(blockcheck_coverage_manifest_path(root))
    if not manifest:
        return ()
    targets = manifest.get("targets") if isinstance(manifest.get("targets"), dict) else {}
    logs: list[Path] = []
    seen: set[Path] = set()
    for item in targets.values():
        if not isinstance(item, dict):
            continue
        if str(item.get("status")) != "available":
            continue
        rel_log = str(item.get("lastLog") or "")
        if not rel_log:
            continue
        path = (root / rel_log).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        if path.is_file() and path not in seen and _blockcheck_log_has_available_strategies(path):
            logs.append(path)
            seen.add(path)
    return tuple(logs)


def _select_blockcheck_export_logs(root: Path | None = None) -> tuple[Path, ...]:
    layout = discover_layout(root)
    candidate_logs = _candidate_export_logs_from_manifest(layout.root)
    if candidate_logs:
        return candidate_logs
    return (_select_blockcheck_export_log(layout.root),)


def _domains_from_blockcheck_log(text: str, fallback: str = "blockcheck") -> tuple[str, ...]:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("domains:"):
            raw_value = line.split(":", 1)[1]
            values = [item.strip() for item in raw_value.replace(",", " ").split() if item.strip()]
            if values:
                return tuple(values)
    return (fallback,)


def _service_target_preset_from_blockcheck_log(text: str, domains: tuple[str, ...]) -> str:
    """Return the service preset id captured in a Blockcheck log.

    Stage 5 writes the owner-selected preset into each command plan. Older logs
    are still exportable: for those we infer a preset from the domains when the
    mapping is unambiguous, otherwise the generated strategy is tagged custom.
    """

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("service target preset:"):
            value = line.split(":", 1)[1].strip().split(None, 1)[0]
            try:
                get_service_target_preset(value)
            except ValueError:
                return SERVICE_TARGET_CUSTOM
            return value
        if line.startswith("ZAP2_SERVICE_TARGET_PRESET="):
            value = line.split("=", 1)[1].strip()
            try:
                get_service_target_preset(value)
            except ValueError:
                return SERVICE_TARGET_CUSTOM
            return value
    return infer_service_target_preset_id(domains)


def _slug(value: str, *, max_len: int = 48) -> str:
    cleaned = value.lower().replace("://", "-").replace("/", "-")
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", cleaned).strip("-._")
    cleaned = re.sub(r"[-_.]{2,}", "-", cleaned)
    return (cleaned or "blockcheck")[:max_len].strip("-._") or "blockcheck"


def _catalog_relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _strategy_args_for_custom_list(runtime_args: tuple[str, ...]) -> tuple[str, ...]:
    """Return nfqws2 args suitable for upstream custom/list_https_*.txt.

    Runtime strategies contain GUI/runtime scaffolding such as --lua-init and
    protocol filters. blockcheck2 custom lists expect the candidate-specific
    nfqws2 parameters only, one strategy per line.
    """

    cleaned: list[str] = []
    for arg in runtime_args:
        value = str(arg).strip()
        if not value:
            continue
        if value.startswith("--lua-init"):
            continue
        if value.startswith("--filter-"):
            continue
        cleaned.append(value)
    if not cleaned:
        raise ValueError("strategy runtimeArgs do not contain blockcheck-testable nfqws2 parameters")
    return tuple(cleaned)


def _strategy_line_for_custom_list(runtime_args: tuple[str, ...]) -> str:
    return shlex.join(_strategy_args_for_custom_list(runtime_args))


def write_blockcheck_strategy_validation_lists(
    root: Path | None = None,
    strategy_id: str = "",
) -> BlockcheckStrategyValidationLists:
    """Materialize custom blockcheck lists with exactly one generated strategy.

    This is the Stage 7b bridge from the user's tournament sketch to upstream
    blockcheck2: a record-candidate strategy can be tested against the next phase
    without first gathering an arbitrary bucket of N strategies for one domain.
    """

    if not strategy_id:
        raise ValueError("strategy_id обязателен для one-strategy validation lists")
    from .workspace_profiles import load_strategy_catalog

    layout = discover_layout(root)
    strategies = load_strategy_catalog(layout.root).by_id()
    if strategy_id not in strategies:
        raise ValueError(f"Неизвестная стратегия: {strategy_id}. Доступно: {', '.join(sorted(strategies))}")
    strategy = strategies[strategy_id]
    line = _strategy_line_for_custom_list(strategy.runtime_args)
    list_root = layout.root / ".zap2" / "blockcheck" / "tournament" / "custom-lists" / _slug(strategy_id, max_len=96)
    list_root.mkdir(parents=True, exist_ok=True)
    files = {
        "LIST_HTTP": list_root / "list_http.txt",
        "LIST_HTTPS_TLS12": list_root / "list_https_tls12.txt",
        "LIST_HTTPS_TLS13": list_root / "list_https_tls13.txt",
        "LIST_QUIC": list_root / "list_quic.txt",
    }
    files["LIST_HTTP"].write_text("# intentionally empty for Stage 7b one-strategy TLS validation\n", encoding="utf-8")
    files["LIST_HTTPS_TLS12"].write_text(line + "\n", encoding="utf-8")
    files["LIST_HTTPS_TLS13"].write_text(line + "\n", encoding="utf-8")
    files["LIST_QUIC"].write_text("# intentionally empty for Discord non-voice Stage 7b TLS validation\n", encoding="utf-8")
    env_items = tuple((key, str(path)) for key, path in files.items()) + (("ZAP2_TOURNAMENT_STRATEGY_ID", strategy_id),)
    return BlockcheckStrategyValidationLists(strategy_id=strategy_id, root_dir=list_root, strategy_line=line, env_items=env_items)


def blockcheck_strategy_validation_plan_to_text(
    root: Path | None = None,
    strategy_id: str = "",
    target: str = "",
) -> str:
    """Read-only plan for validating one strategy against one target/phase alternative."""

    if not target.strip():
        raise ValueError("target обязателен для strategy validation plan")
    lists = write_blockcheck_strategy_validation_lists(root=root, strategy_id=strategy_id)
    from .workspace_profiles import load_strategy_catalog

    layout = discover_layout(root)
    strategy = load_strategy_catalog(layout.root).by_id()[strategy_id]
    service_target = strategy.service_target or {}
    preset_id = str(service_target.get("presetId") or infer_service_target_preset_id((target,)))
    opts = BlockcheckOptions(
        domains=target,
        service_target_preset_id=preset_id,
        scan_mode=BLOCKCHECK_SCAN_STOP_AFTER_FIRST_AVAILABLE,
        test="custom",
        scanlevel="quick",
        enable_http=False,
        enable_https_tls12=True,
        enable_https_tls13=True,
        enable_http3=False,
        custom_list_env=lists.env_items,
    )
    command = build_blockcheck_command(root=layout.root, options=opts)
    lines = [
        "Blockcheck one-strategy validation plan",
        f"strategy: {strategy_id}",
        f"target: {target}",
        f"service target preset: {preset_id}",
        "semantics: one strategy candidate is checked against one phase alternative; phases are AND, alternatives are OR",
        f"custom list root: {lists.root_dir}",
        f"strategy line: {lists.strategy_line}",
        "custom env:",
    ]
    lines.extend(f"  {key}={value}" for key, value in lists.env_items)
    lines.extend([
        "command preview:",
        f"  {command.redacted_command_preview()}",
        "executes now: no",
        "mutates services/firewall now: no",
        "mutates worktree now: yes (writes one-strategy custom lists)",
    ])
    return "\n".join(lines)


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
    service_target_preset_id: str,
    available: AvailableBlockcheckStrategy,
    source_log: Path,
    root: Path,
    index: int,
    generated_at: str,
    coverage_rows: tuple[dict[str, object], ...] = (),
    preset_path: str = "",
) -> dict[str, object]:
    try:
        source_path = _catalog_relative(source_log, root)
    except ValueError:
        source_path = str(source_log)
    service_preset = get_service_target_preset(service_target_preset_id)
    service_policy = service_preset.policy
    service_title = service_preset.title
    return {
        "schemaVersion": 1,
        "id": strategy_id,
        "title": title,
        "summary": summary,
        "philosophy": "blockcheck-generated-owner-choice",
        "intendedFor": [
            f"service target preset: {service_target_preset_id} ({service_title})",
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
        "presetPath": preset_path,
        "serviceTarget": {
            "presetId": service_target_preset_id,
            "title": service_title,
            "summary": service_preset.summary,
            "nonVoice": service_preset.non_voice,
            "targets": list(target_domains),
            "exportedCandidate": available.target,
            "coveragePolicy": {
                "mode": service_policy.mode,
                "orderMode": service_policy.order_mode,
                "recommendedScanMode": service_policy.recommended_scan_mode,
                "stopRule": service_policy.stop_rule,
            },
            "coverage": {
                "source": "blockcheck-candidate-coverage",
                "scope": "per-target; not a full-service guarantee unless every required target is available",
                "targets": list(coverage_rows),
            },
        },
        "sourcePreset": {
            "engine": "nfqws2",
            "id": "blockcheck-generated",
            "name": "Blockcheck generated AVAILABLE strategy",
            "serviceTargetPresetId": service_target_preset_id,
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
            "Stage 7 records per-target coverage so a single-target AVAILABLE strategy is not presented as proven coverage for a multi-target desktop path.",
            "Stage 7a records the service coverage policy that explains whether any target, unordered many targets, or an ordered target chain matters.",
        ],
    }


def export_blockcheck_available_strategies(root: Path | None = None, max_strategies: int = 0) -> BlockcheckGeneratedStrategiesResult:
    """Convert AVAILABLE strategies from recent blockcheck logs into catalog files."""

    layout = discover_layout(root)
    source_logs = _select_blockcheck_export_logs(layout.root)
    source_log = source_logs[0]
    catalog_path = layout.root / "strategies" / "catalog.json"
    generated_dir = layout.root / "strategies" / "generated"
    generated_preset_dir = layout.root / "presets" / "generated"
    for item in source_logs:
        if not item.is_file():
            raise ValueError(f"Успешный blockcheck log для экспорта не найден: {item}")

    gathered: list[tuple[Path, tuple[str, ...], str, AvailableBlockcheckStrategy]] = []
    for log_path in source_logs:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        domains = _domains_from_blockcheck_log(text)
        service_target_preset_id = _service_target_preset_from_blockcheck_log(text, domains)
        for available in parse_blockcheck_available_strategies(text):
            gathered.append((log_path, domains, service_target_preset_id, available))

    if max_strategies > 0:
        gathered = gathered[:max_strategies]

    first_domains = gathered[0][1] if gathered else _domains_from_blockcheck_log(source_log.read_text(encoding="utf-8", errors="replace")) if source_log.is_file() else ("blockcheck",)
    first_preset_id = gathered[0][2] if gathered else infer_service_target_preset_id(first_domains)
    service_slug = service_target_export_slug(first_preset_id)
    target_label = _slug(first_domains[0])
    export_label = _slug(service_slug) if first_preset_id != SERVICE_TARGET_CUSTOM else target_label
    if not gathered:
        return BlockcheckGeneratedStrategiesResult(
            source_log=source_log,
            target_label=target_label,
            service_target_preset_id=first_preset_id,
            generated=(),
            catalog_path=catalog_path,
            source_logs=source_logs,
        )

    generated_dir.mkdir(parents=True, exist_ok=True)
    generated_preset_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    files: list[GeneratedStrategyFile] = []
    for index, (log_path, domains, service_target_preset_id, item) in enumerate(gathered, 1):
        service_preset = get_service_target_preset(service_target_preset_id)
        service_slug = service_target_export_slug(service_target_preset_id)
        export_label = _slug(service_slug) if service_target_preset_id != SERVICE_TARGET_CUSTOM else _slug(domains[0])
        stamp = datetime.fromtimestamp(log_path.stat().st_mtime, timezone.utc).strftime("%Y%m%d-%H%M%S")
        candidate_label = _slug(item.target or domains[0], max_len=32)
        strategy_id = f"blockcheck-{export_label}-{candidate_label}-{stamp}-{index:02d}"
        filename = f"{strategy_id}.json"
        path = generated_dir / filename
        preset_path = generated_preset_dir / f"{strategy_id}.txt"
        preset_rel = _catalog_relative(preset_path, layout.root)
        coverage_rows = _coverage_rows_for_strategy(layout.root, service_target_preset_id, item.target or domains[0])
        target_status = _coverage_status_for_target(layout.root, service_target_preset_id, item.target or domains[0])
        coverage_summary = ", ".join(
            f"{row.get('target')}={row.get('status')}" for row in coverage_rows
        )
        found_at = datetime.fromtimestamp(log_path.stat().st_mtime, timezone.utc)
        title = blockcheck_title(service_preset.title, desync_functions(item.runtime_args), item.target or domains[0], found_at)
        if sum(1 for other in gathered if other[3].target == item.target) > 1:
            title += f" #{index:02d}"  # одна цель — несколько вариантов: различаем номером
        summary = (
            f"Generated AVAILABLE strategy for {service_preset.title} "
            f"candidate {item.target or domains[0]} from {item.probe} ({item.script}). "
            f"Coverage status for this candidate: {target_status}."
        )
        payload = _strategy_payload(
            strategy_id=strategy_id,
            title=title,
            summary=summary,
            target_domains=domains,
            service_target_preset_id=service_target_preset_id,
            available=item,
            source_log=log_path,
            root=layout.root,
            index=index,
            generated_at=generated_at,
            coverage_rows=coverage_rows,
            preset_path=preset_rel,
        )
        payload.setdefault("notes", []).append(f"Coverage snapshot: {coverage_summary}")
        preset_lines = [
            "# z2guiflin generated Zapret2 preset",
            f"# id: {strategy_id}",
            f"# source: {log_path}",
            *item.runtime_args,
        ]
        preset_path.write_text("\n".join(preset_lines).rstrip() + "\n", encoding="utf-8")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        files.append(
            GeneratedStrategyFile(
                strategy_id=strategy_id,
                path=path,
                source_probe=item.probe,
                source_target=item.target,
                service_target_preset_id=service_target_preset_id,
                coverage_status=target_status,
                runtime_args=item.runtime_args,
            )
        )
    _update_strategy_catalog(catalog_path, tuple(item.path for item in files), layout.root)
    return BlockcheckGeneratedStrategiesResult(
        source_log=source_log,
        target_label=target_label,
        service_target_preset_id=first_preset_id,
        generated=tuple(files),
        catalog_path=catalog_path,
        source_logs=source_logs,
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


def blockcheck_coverage_json_path(log_path: Path) -> Path:
    return log_path.with_name(log_path.stem + "-coverage.json")


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
    ]
    coverage_rows = parse_blockcheck_coverage(stdout)
    if coverage_rows:
        parts.extend(["\n===== BLOCKCHECK COVERAGE =====\n", blockcheck_coverage_rows_to_text(coverage_rows), "\n"])
    parts += [
        "\n===== STDERR =====\n",
        stderr,
    ]
    if footer.strip():
        parts.extend(["\n===== GUI FINISH =====\n", footer.rstrip(), "\n"])
    text = "".join(parts)
    command.log_path.write_text(text, encoding="utf-8")
    if coverage_rows:
        blockcheck_coverage_json_path(command.log_path).write_text(
            json.dumps(
                {"schemaVersion": 1, "source": "blockcheck2 * COVERAGE", "rows": [row.to_dict() for row in coverage_rows]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if command.candidate_log_path is not None:
        command.candidate_log_path.parent.mkdir(parents=True, exist_ok=True)
        command.candidate_log_path.write_text(text, encoding="utf-8")
        _update_blockcheck_coverage_manifest(command, stats, text)

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
