"""Pure Python model of the initial GUI navigation shell."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NavigationSection:
    """Одна вкладка/секция будущей PyQt-оболочки."""

    key: str
    title: str
    purpose: str
    ready_state: str


def default_navigation_sections() -> tuple[NavigationSection, ...]:
    """Return the stable v0.3-alpha navigation skeleton."""

    return (
        NavigationSection(
            key="overview",
            title="Обзор",
            purpose="Сводка состояния проекта, ядра и ближайшего безопасного действия.",
            ready_state="placeholder",
        ),
        NavigationSection(
            key="core",
            title="Ядро",
            purpose="Инвентаризация vendored-ядра, build units и будущий локальный build workflow.",
            ready_state="inventory-backed",
        ),
        NavigationSection(
            key="strategies",
            title="Стратегии",
            purpose="Workspace-профили, hostlists и каталог стратегий без скрытого запуска команд.",
            ready_state="profiles-backed",
        ),
        NavigationSection(
            key="diagnostics",
            title="Диагностика",
            purpose="Blockcheck lab для ручного подбора стратегии под домен без скрытых действий.",
            ready_state="blockcheck-backed",
        ),
        NavigationSection(
            key="tunnel",
            title="Туннель",
            purpose="Экспериментальная SOCKS/VLESS-ветка для Discord: профили, probes и guided CLI.",
            ready_state="tunnel-backed",
        ),
        NavigationSection(
            key="settings",
            title="Настройки",
            purpose="Язык, пути, политика подтверждений и будущие developer-oriented параметры.",
            ready_state="placeholder",
        ),
        NavigationSection(
            key="logs",
            title="Логи",
            purpose="Будущая история операций, dry-run планов, проверок и результатов исполнения.",
            ready_state="placeholder",
        ),
    )
