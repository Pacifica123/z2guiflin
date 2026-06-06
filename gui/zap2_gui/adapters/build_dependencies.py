"""Read-only build dependency preflight для локальной сборки vendored-ядра.

Модуль не устанавливает пакеты, не вызывает sudo и не запускает `make`. Он только
проверяет наличие базовых команд/заголовков, которые нужны build target `nfqws2`,
и возвращает owner-facing подсказки по пакетам для популярных семейств Linux.
"""

from __future__ import annotations

import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

CommandResolver = Callable[[str], str | None]

BUILD_DEPENDENCY_STAGE = "v0.3-beta_stage_2"
BUILD_DEPENDENCY_MARKER = "zap2-build-dependency-preflight-v1"

PACKAGE_HINTS: dict[str, tuple[str, ...]] = {
    "Debian/Ubuntu": (
        "sudo apt install build-essential pkg-config zlib1g-dev libnetfilter-queue-dev libnfnetlink-dev libmnl-dev libluajit-5.1-dev",
        "если LuaJIT недоступен: sudo apt install liblua5.4-dev или liblua5.3-dev",
    ),
    "Fedora/RHEL-like": (
        "sudo dnf install gcc make pkgconf-pkg-config zlib-devel libnetfilter_queue-devel libnfnetlink-devel libmnl-devel luajit-devel",
    ),
    "Arch/Manjaro": (
        "sudo pacman -S --needed base-devel pkgconf zlib libnetfilter_queue libnfnetlink libmnl luajit",
    ),
    "openSUSE": (
        "sudo zypper install gcc make pkg-config zlib-devel libnetfilter_queue-devel libnfnetlink-devel libmnl-devel luajit-devel",
    ),
}

COMMAND_REQUIREMENTS: tuple[tuple[str, str, tuple[str, ...], bool], ...] = (
    ("make", "make", ("make",), True),
    ("c-compiler", "C compiler", ("cc", "gcc", "clang"), True),
    ("pkg-config", "pkg-config", ("pkg-config", "pkgconf"), False),
)

HEADER_REQUIREMENTS: tuple[tuple[str, str, tuple[str, ...], bool], ...] = (
    ("zlib", "zlib header", ("zlib.h",), True),
    (
        "libnetfilter_queue",
        "libnetfilter_queue header",
        ("libnetfilter_queue/libnetfilter_queue.h",),
        True,
    ),
    ("libnfnetlink", "libnfnetlink header", ("libnfnetlink/libnfnetlink.h",), True),
    ("libmnl", "libmnl header", ("libmnl/libmnl.h",), True),
    (
        "lua",
        "LuaJIT или Lua header",
        (
            "luajit-2.1/lua.h",
            "luajit-2.0/lua.h",
            "lua5.5/lua.h",
            "lua5.4/lua.h",
            "lua5.3/lua.h",
            "lua5.2/lua.h",
            "lua5.1/lua.h",
            "lua/lua.h",
            "lua.h",
        ),
        True,
    ),
)


@dataclass(frozen=True)
class BuildDependencyCheck:
    """Результат одной read-only проверки зависимости сборки."""

    check_id: str
    label: str
    kind: str
    required: bool
    status: str
    details: str
    candidates: tuple[str, ...]
    found: str | None = None

    @property
    def ok_for_build(self) -> bool:
        return self.status == "ok" or not self.required

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.check_id,
            "label": self.label,
            "kind": self.kind,
            "required": self.required,
            "status": self.status,
            "details": self.details,
            "candidates": list(self.candidates),
            "found": self.found,
        }


@dataclass(frozen=True)
class BuildDependencyReport:
    """Полный preflight-отчёт по зависимостям build target."""

    target: str
    stage: str
    marker: str
    checks: tuple[BuildDependencyCheck, ...]
    install_hints: dict[str, tuple[str, ...]]
    executes_install_now: bool = False
    requires_sudo_now: bool = False
    runs_make_now: bool = False

    @property
    def ok(self) -> bool:
        return all(check.ok_for_build for check in self.checks)

    @property
    def missing_required(self) -> tuple[BuildDependencyCheck, ...]:
        return tuple(check for check in self.checks if check.required and check.status != "ok")

    @property
    def warnings(self) -> tuple[BuildDependencyCheck, ...]:
        return tuple(check for check in self.checks if not check.required and check.status != "ok")

    def summary_line(self) -> str:
        if self.ok:
            return "ok"
        missing = ", ".join(check.check_id for check in self.missing_required)
        return f"failed; missing required: {missing}"

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "stage": self.stage,
            "marker": self.marker,
            "ok": self.ok,
            "summary": self.summary_line(),
            "checks": [check.to_dict() for check in self.checks],
            "missingRequired": [check.to_dict() for check in self.missing_required],
            "warnings": [check.to_dict() for check in self.warnings],
            "installHints": {key: list(value) for key, value in self.install_hints.items()},
            "executesInstallNow": self.executes_install_now,
            "requiresSudoNow": self.requires_sudo_now,
            "runsMakeNow": self.runs_make_now,
        }

    def to_text(self) -> str:
        lines = [
            f"Build dependency preflight для target: {self.target}",
            f"status: {self.summary_line()}",
            "checks:",
        ]
        for check in self.checks:
            required = "required" if check.required else "recommended"
            found = f"; found: {check.found}" if check.found else ""
            lines.append(f"  - {check.status}: {check.check_id} ({required}) — {check.details}{found}")
        if self.missing_required:
            lines.append("owner action hints:")
            for family, commands in self.install_hints.items():
                lines.append(f"  {family}:")
                for command in commands:
                    lines.append(f"    - {command}")
        lines.extend(
            [
                "executes install now: no",
                "requires sudo now: no",
                "runs make now: no",
            ]
        )
        return "\n".join(lines)


def build_dependency_requirements_for_target(target: str) -> dict[str, object]:
    """Возвращает hash-stable описание требований без host-specific статуса."""

    if target != "nfqws2":
        return {
            "stage": BUILD_DEPENDENCY_STAGE,
            "marker": BUILD_DEPENDENCY_MARKER,
            "target": target,
            "commandRequirements": [],
            "headerRequirements": [],
            "installHints": {key: list(value) for key, value in PACKAGE_HINTS.items()},
            "executesInstallNow": False,
            "requiresSudoNow": False,
            "runsMakeNow": False,
        }
    return {
        "stage": BUILD_DEPENDENCY_STAGE,
        "marker": BUILD_DEPENDENCY_MARKER,
        "target": target,
        "commandRequirements": [
            {"id": item_id, "label": label, "candidates": list(candidates), "required": required}
            for item_id, label, candidates, required in COMMAND_REQUIREMENTS
        ],
        "headerRequirements": [
            {"id": item_id, "label": label, "headers": list(headers), "required": required}
            for item_id, label, headers, required in HEADER_REQUIREMENTS
        ],
        "installHints": {key: list(value) for key, value in PACKAGE_HINTS.items()},
        "executesInstallNow": False,
        "requiresSudoNow": False,
        "runsMakeNow": False,
    }


def _split_env_paths(value: str | None) -> tuple[Path, ...]:
    if not value:
        return ()
    return tuple(Path(item).expanduser() for item in value.split(os.pathsep) if item)


def default_include_paths(env: dict[str, str] | None = None) -> tuple[Path, ...]:
    """Возвращает типовые include paths без вызова компилятора или pkg-config."""

    actual_env = env if env is not None else os.environ
    paths: list[Path] = []
    paths.extend(_split_env_paths(actual_env.get("CPATH")))
    paths.extend(_split_env_paths(actual_env.get("C_INCLUDE_PATH")))
    paths.extend(
        Path(item)
        for item in (
            "/usr/local/include",
            "/usr/include",
            "/usr/include/x86_64-linux-gnu",
            "/usr/include/aarch64-linux-gnu",
            "/usr/include/arm-linux-gnueabihf",
            "/usr/include/i386-linux-gnu",
            "/usr/include/x86_64-linux-musl",
        )
    )
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return tuple(unique)


def _find_header(headers: Iterable[str], include_paths: Iterable[Path]) -> tuple[str | None, str]:
    searched: list[str] = []
    for include_dir in include_paths:
        for header in headers:
            candidate = include_dir / header
            searched.append(str(candidate))
            if candidate.exists():
                return str(candidate), f"header найден: {header}"
    return None, "header не найден в include paths"


def _check_command(
    check_id: str,
    label: str,
    candidates: tuple[str, ...],
    required: bool,
    resolver: CommandResolver,
) -> BuildDependencyCheck:
    for candidate in candidates:
        found = resolver(candidate)
        if found:
            return BuildDependencyCheck(
                check_id=check_id,
                label=label,
                kind="command",
                required=required,
                status="ok",
                details=f"команда доступна: {candidate}",
                candidates=candidates,
                found=found,
            )
    status = "missing" if required else "warning"
    return BuildDependencyCheck(
        check_id=check_id,
        label=label,
        kind="command",
        required=required,
        status=status,
        details=f"команда не найдена: {', '.join(candidates)}",
        candidates=candidates,
    )


def _compiler_candidates(env: dict[str, str] | None = None) -> tuple[str, ...]:
    actual_env = env if env is not None else os.environ
    cc = actual_env.get("CC", "").strip()
    if cc:
        try:
            first = shlex.split(cc)[0]
        except ValueError:
            first = cc.split()[0]
        defaults = tuple(item for item in ("cc", "gcc", "clang") if item != first)
        return (first, *defaults)
    return ("cc", "gcc", "clang")


def make_success_report(target: str = "nfqws2") -> BuildDependencyReport:
    """Synthetic OK report для тестов fake-runner без host dependency assumptions."""

    checks: list[BuildDependencyCheck] = []
    for check_id, label, candidates, required in COMMAND_REQUIREMENTS:
        checks.append(
            BuildDependencyCheck(
                check_id=check_id,
                label=label,
                kind="command",
                required=required,
                status="ok",
                details="synthetic test dependency satisfied",
                candidates=candidates,
                found=candidates[0],
            )
        )
    for check_id, label, headers, required in HEADER_REQUIREMENTS:
        checks.append(
            BuildDependencyCheck(
                check_id=check_id,
                label=label,
                kind="header",
                required=required,
                status="ok",
                details="synthetic test dependency satisfied",
                candidates=headers,
                found=headers[0],
            )
        )
    return BuildDependencyReport(
        target=target,
        stage=BUILD_DEPENDENCY_STAGE,
        marker=BUILD_DEPENDENCY_MARKER,
        checks=tuple(checks),
        install_hints=PACKAGE_HINTS,
    )


def run_build_dependency_preflight(
    target: str = "nfqws2",
    *,
    include_paths: tuple[Path, ...] | None = None,
    command_resolver: CommandResolver | None = None,
    env: dict[str, str] | None = None,
) -> BuildDependencyReport:
    """Проверяет build dependencies без установки пакетов и без запуска `make`."""

    if target != "nfqws2":
        return BuildDependencyReport(
            target=target,
            stage=BUILD_DEPENDENCY_STAGE,
            marker=BUILD_DEPENDENCY_MARKER,
            checks=(),
            install_hints=PACKAGE_HINTS,
        )

    resolver = command_resolver or shutil.which
    actual_include_paths = include_paths if include_paths is not None else default_include_paths(env)
    checks: list[BuildDependencyCheck] = []
    for check_id, label, candidates, required in COMMAND_REQUIREMENTS:
        actual_candidates = _compiler_candidates(env) if check_id == "c-compiler" else candidates
        checks.append(_check_command(check_id, label, actual_candidates, required, resolver))
    for check_id, label, headers, required in HEADER_REQUIREMENTS:
        found, details = _find_header(headers, actual_include_paths)
        checks.append(
            BuildDependencyCheck(
                check_id=check_id,
                label=label,
                kind="header",
                required=required,
                status="ok" if found else "missing",
                details=details,
                candidates=headers,
                found=found,
            )
        )
    return BuildDependencyReport(
        target=target,
        stage=BUILD_DEPENDENCY_STAGE,
        marker=BUILD_DEPENDENCY_MARKER,
        checks=tuple(checks),
        install_hints=PACKAGE_HINTS,
    )
