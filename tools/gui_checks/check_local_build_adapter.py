#!/usr/bin/env python3
"""Проверка Stage 6: local build adapter строит план, но не выполняет make."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gui"))

from zap2_gui.adapters.local_build import create_local_build_plan, inspect_artifacts, supported_build_targets  # noqa: E402


FORBIDDEN_ARGV_PARTS = {"sudo", "su", "systemctl", "service", "iptables", "nft", "ipset"}


def _assert_safe_plan(target: str) -> None:
    plan = create_local_build_plan(ROOT, target=target)
    if plan.automatic_checks_may_execute:
        raise AssertionError("Автоматические проверки не должны выполнять build plan")
    if plan.may_require_sudo:
        raise AssertionError("Local build plan не должен требовать sudo")
    if plan.may_mutate_services_or_firewall:
        raise AssertionError("Local build plan не должен менять services/firewall")
    if not plan.commands:
        raise AssertionError("Local build plan должен содержать хотя бы одну команду")
    for command in plan.commands:
        if command.requires_sudo:
            raise AssertionError(f"Команда {command.label} неожиданно требует sudo")
        forbidden = FORBIDDEN_ARGV_PARTS.intersection(command.argv)
        if forbidden:
            raise AssertionError(f"Команда {command.label} содержит запрещённые части argv: {sorted(forbidden)}")
        if command.argv[0] != "make":
            raise AssertionError(f"Команда {command.label} должна быть make-командой")
    inspect_artifacts(plan)


def main() -> int:
    targets = supported_build_targets()
    # Повторно задаём ожидаемый набор явно, чтобы сломанный build map не прошёл тихо.
    expected = ("all", "nfqws2", "ip2net", "mdig", "clean")
    if targets != expected:
        raise AssertionError(f"Неожиданные build targets: {targets}")
    for target in expected:
        _assert_safe_plan(target)
    print("Local build adapter OK: планы валидируются без запуска make/sudo/services/firewall")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
