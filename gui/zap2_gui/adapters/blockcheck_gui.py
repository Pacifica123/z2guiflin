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

from .gui_privilege import _desktop_env_for_askpass, ensure_sudo_askpass_helper, is_sudo_available
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
            "uses sudo askpass: yes",
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
