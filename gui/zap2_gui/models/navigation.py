"""Pure Python model of the GUI navigation shell."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NavigationSection:
    """Одна вкладка/секция PyQt-оболочки."""

    key: str
    title: str
    purpose: str
    ready_state: str
    group: str = ""


NAVIGATION_GROUPS: tuple[tuple[str, str], ...] = (
    ("", ""),
    ("remedies", "Средства"),
    ("system", "Система"),
)
"""Порядок групп в левой панели: (ключ, подпись). Пустая подпись — без заголовка."""


def default_navigation_sections() -> tuple[NavigationSection, ...]:
    """Return navigation sections in display order.

    Путь пользователя: «Главная» → «Диагностика» (что сломано) → средства
    (что попробовать) → системные страницы. Ключи стабильны: по ним
    работают поиск Ctrl+K, переходы «Что попробовать» и запоминание страницы.
    """

    return (
        NavigationSection(
            key="home",
            title="Главная",
            purpose="О программе: откуда она взялась и на чьих плечах стоит. Ничего не проверяет и не трогает сеть.",
            ready_state="showcase",
        ),
        NavigationSection(
            key="diagnostics",
            title="Диагностика",
            purpose="Что сломано: вердикт сети и Blockcheck lab для ручного подбора стратегии под домен без скрытых действий.",
            ready_state="blockcheck-backed",
        ),
        NavigationSection(
            key="overview",
            title="Запуск",
            purpose="Запуск и остановка выбранных компонентов: zapret2 с активным пресетом и туннель.",
            ready_state="runtime-backed",
            group="remedies",
        ),
        NavigationSection(
            key="strategies",
            title="Пресеты",
            purpose="Каталог пресетов и их упорядоченных traffic-профилей: filter, strategy, range и direction.",
            ready_state="preset-profiles-backed",
            group="remedies",
        ),
        NavigationSection(
            key="dns",
            title="DNS",
            purpose="Смена DNS-сервера через NetworkManager с откатом: каталог провайдеров, проверка перехвата и подмены.",
            ready_state="networkmanager-backed",
            group="remedies",
        ),
        NavigationSection(
            key="tunnel",
            title="Туннель",
            purpose="Экспериментальная SOCKS/VLESS-ветка для Discord: профили, probes и guided CLI.",
            ready_state="tunnel-backed",
            group="remedies",
        ),
        NavigationSection(
            key="tor",
            title="Tor",
            purpose="Системный C Tor или Arti: мосты и pluggable transports, приложения через Tor или Tor перед VLESS.",
            ready_state="tor-backed",
            group="remedies",
        ),
        NavigationSection(
            key="core",
            title="Ядро",
            purpose="Инвентаризация vendored-ядра, build units и локальный build workflow.",
            ready_state="inventory-backed",
            group="system",
        ),
        NavigationSection(
            key="logs",
            title="Логи",
            purpose="История операций, dry-run планов, проверок и результатов исполнения.",
            ready_state="runtime-logs-backed",
            group="system",
        ),
        NavigationSection(
            key="settings",
            title="Настройки",
            purpose="Внешний вид и локальные параметры интерфейса.",
            ready_state="appearance-backed",
            group="system",
        ),
    )


def navigation_group_title(group: str) -> str:
    return dict(NAVIGATION_GROUPS).get(group, "")
