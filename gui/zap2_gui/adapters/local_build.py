"""Локальный build adapter для vendored-ядра zapret2.

Модуль намеренно строит *план* сборки, а не запускает сборку при импорте или в
автоматических проверках. Реальный `make` остаётся локальным действием владельца
проекта.
"""

from __future__ import annotations

import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from ..core_inventory import CoreBuildMap, CoreBuildUnit, load_core_build_map
from ..project_paths import discover_layout


@dataclass(frozen=True)
class BuildCommand:
    """Одна команда, которую владелец может выполнить локально."""

    label: str
    cwd: Path
    argv: tuple[str, ...]
    description: str
    mutates_worktree: bool
    requires_sudo: bool = False

    def shell_preview(self) -> str:
        quoted_cwd = shlex.quote(str(self.cwd))
        quoted_argv = " ".join(shlex.quote(part) for part in self.argv)
        return f"cd {quoted_cwd} && {quoted_argv}"


@dataclass(frozen=True)
class BuildArtifact:
    """Ожидаемый результат локальной сборки."""

    unit_name: str
    relative_path: str
    absolute_path: Path


@dataclass(frozen=True)
class ArtifactStatus:
    """Read-only состояние одного ожидаемого артефакта."""

    artifact: BuildArtifact
    exists: bool
    size_bytes: int | None


@dataclass(frozen=True)
class LocalBuildPlan:
    """Явный план локальной сборки ядра."""

    target: str
    core_root: Path
    commands: tuple[BuildCommand, ...]
    expected_artifacts: tuple[BuildArtifact, ...]
    required_libraries_hint: tuple[str, ...]
    automatic_checks_may_execute: bool
    may_require_sudo: bool
    may_mutate_services_or_firewall: bool

    def command_previews(self) -> tuple[str, ...]:
        return tuple(command.shell_preview() for command in self.commands)

    def to_text(self) -> str:
        libraries = ", ".join(self.required_libraries_hint) or "нет явных подсказок"
        artifacts = ", ".join(item.relative_path for item in self.expected_artifacts) or "нет"
        commands = "\n".join(f"  {command.shell_preview()}" for command in self.commands)
        return "\n".join(
            [
                f"Local build plan для target: {self.target}",
                f"core root: {self.core_root}",
                "commands:",
                commands,
                f"expected artifacts: {artifacts}",
                f"libraries hint: {libraries}",
                "automatic checks may execute: no",
                "requires sudo: no",
                "mutates services/firewall: no",
            ]
        )


def _unit_directory(unit: CoreBuildUnit) -> str:
    return str(Path(unit.makefile).parent).replace("\\", "/")


def _unit_outputs(core_root: Path, unit: CoreBuildUnit) -> tuple[BuildArtifact, ...]:
    return tuple(
        BuildArtifact(
            unit_name=unit.name,
            relative_path=relative_path,
            absolute_path=core_root / relative_path,
        )
        for relative_path in unit.linux_outputs
    )


def _unique(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def supported_build_targets(build_map: CoreBuildMap | None = None) -> tuple[str, ...]:
    """Возвращает цели, которые adapter умеет представить как локальный план."""

    actual_map = build_map or load_core_build_map()
    unit_targets = tuple(unit.name for unit in actual_map.units)
    return ("all", *unit_targets, "clean")


def create_local_build_plan(root: Path | None = None, target: str = "all") -> LocalBuildPlan:
    """Создаёт план локальной сборки без выполнения команд.

    `target` может быть `all`, именем одного build unit из `BUILD_MAP.json` или
    `clean`. Валидация опирается на committed build map, поэтому GUI сможет
    показывать ровно те действия, которые уже описаны в ядре проекта.
    """

    layout = discover_layout(root)
    core_root = layout.core_dir / "zapret2"
    build_map = load_core_build_map(layout.root)
    units_by_name = {unit.name: unit for unit in build_map.units}
    supported = supported_build_targets(build_map)
    if target not in supported:
        raise ValueError(f"Неизвестная цель сборки: {target}. Доступно: {', '.join(supported)}")

    build_adapter = layout.root / "tools" / "core_generation_build.py"
    if not build_adapter.is_file():
        raise ValueError(f"P03 generation build adapter не найден: {build_adapter}")

    command_target = target
    commands = (
        BuildCommand(
            label=("clean-core-build-artifacts" if target == "clean" else f"build-{target}"),
            cwd=layout.root,
            argv=(sys.executable, str(build_adapter), command_target),
            description=(
                "Удалить canonical build artifacts и staged generation build state."
                if target == "clean"
                else "Собрать exact pinned upstream в fresh staging tree после verified P03 source transforms; canonical source tree не изменяется."
            ),
            mutates_worktree=True,
        ),
    )
    if target in {"all", "clean"}:
        selected_units = tuple(build_map.units)
    else:
        selected_units = (units_by_name[target],)

    artifacts = tuple(
        artifact
        for unit in selected_units
        for artifact in _unit_outputs(core_root, unit)
    )
    required_libraries = _unique(
        [
            library
            for unit in selected_units
            for library in unit.declared_linux_libraries
        ]
    )

    return LocalBuildPlan(
        target=target,
        core_root=core_root,
        commands=commands,
        expected_artifacts=artifacts,
        required_libraries_hint=required_libraries,
        automatic_checks_may_execute=False,
        may_require_sudo=False,
        may_mutate_services_or_firewall=False,
    )


def inspect_artifacts(plan: LocalBuildPlan) -> tuple[ArtifactStatus, ...]:
    """Read-only проверка наличия ожидаемых артефактов после локальной сборки."""

    statuses: list[ArtifactStatus] = []
    for artifact in plan.expected_artifacts:
        path = artifact.absolute_path
        if path.exists():
            statuses.append(ArtifactStatus(artifact=artifact, exists=True, size_bytes=path.stat().st_size))
        else:
            statuses.append(ArtifactStatus(artifact=artifact, exists=False, size_bytes=None))
    return tuple(statuses)
