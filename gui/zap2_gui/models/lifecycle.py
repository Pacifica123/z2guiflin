"""Базовые константы и boundary для controlled runtime lifecycle."""

from __future__ import annotations

from dataclasses import dataclass

RUNTIME_CONTRACT_STAGE = "v0.3-alpha_stage_8"
PLAN_SECTION_KINDS = ("run", "apply", "session", "service")
RUNTIME_ACTIONS = ("start", "stop", "status", "install-service", "remove-service")
RUNTIME_EVENT_TYPES = ("planned", "confirmed", "started", "stopped", "failed", "rolled-back", "status")
RUNTIME_EVENT_LEVELS = ("debug", "info", "warning", "error")


@dataclass(frozen=True)
class LifecycleBoundary:
    """Safety boundary контрактного runtime-слоя.

    Stage 8 разрешает только чтение и валидацию контрактов. Исполнение планов,
    bootstrap, service management и firewall mutation должны появляться только
    отдельными owner-confirmed патчами.
    """

    contract_stage: str = RUNTIME_CONTRACT_STAGE
    bootstrap_mixed_in: bool = False
    automatic_checks_may_execute: bool = False
    may_start_processes: bool = False
    may_mutate_services_or_firewall: bool = False

    @property
    def is_stage8_plan_only(self) -> bool:
        return (
            self.contract_stage == RUNTIME_CONTRACT_STAGE
            and not self.bootstrap_mixed_in
            and not self.automatic_checks_may_execute
            and not self.may_start_processes
            and not self.may_mutate_services_or_firewall
        )


def default_lifecycle_boundary() -> LifecycleBoundary:
    """Возвращает boundary, который обязателен для Stage 8."""

    return LifecycleBoundary()
