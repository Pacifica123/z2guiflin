"""Модели контекста запуска владельца.

Историческое имя WorkspaceProfile сохранено как alias. Оно не означает профиль
Zapret2: настоящий traffic-профиль является блоком внутри пресета.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HostlistRef:
    """Ссылка на локальный hostlist внутри workspace."""

    hostlist_id: str
    path: str
    purpose: str


@dataclass(frozen=True)
class WorkspaceSafety:
    """Safety boundary профиля на текущей стадии."""

    read_only_in_checks: bool
    requires_owner_confirmation_before_apply: bool
    may_use_sudo: bool
    may_mutate_services_or_firewall: bool


@dataclass(frozen=True)
class WorkspaceRuntimeContext:
    """Контекст запуска связывает выбранный пресет, build target и локальные данные."""

    schema_version: int
    profile_id: str
    title: str
    description: str
    strategy_id: str
    build_target: str
    hostlists: tuple[HostlistRef, ...]
    safety: WorkspaceSafety
    notes: tuple[str, ...]

    @property
    def runtime_context_id(self) -> str:
        """Canonical P04 name for the legacy profile_id field."""

        return self.profile_id

    @property
    def preset_id(self) -> str:
        """Canonical P04 name for the legacy strategy_id selection field."""

        return self.strategy_id

    @property
    def is_read_only_stage7(self) -> bool:
        return (
            self.safety.read_only_in_checks
            and self.safety.requires_owner_confirmation_before_apply
            and not self.safety.may_use_sudo
            and not self.safety.may_mutate_services_or_firewall
        )


# Совместимость со старыми импортами до завершения миграции терминов.
WorkspaceProfile = WorkspaceRuntimeContext
