"""Средства восстановления доступа и их связь с вердиктом диагностики.

Программа собрана из разных средств (обход DPI, туннели, DNS и Tor).
Пользователю не нужно знать, какое из них выбрать: диагностика даёт вердикт,
а эта таблица отвечает «что попробовать» и честно говорит, что изменится.

Только данные, без Qt и без побочных эффектов.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Remedy:
    key: str
    title: str
    layer: str  # dpi | route | local
    what_changes: str
    needs_root: bool
    reversible: bool
    page_key: str | None  # страница навигации; None — только совет


REMEDIES: dict[str, Remedy] = {
    remedy.key: remedy
    for remedy in (
        Remedy(
            key="zapret",
            title="Включить обход DPI",
            layer="dpi",
            what_changes="Запускает zapret2 с активным пресетом; правила nftables ставятся и снимаются программой.",
            needs_root=True,
            reversible=True,
            page_key="overview",
        ),
        Remedy(
            key="presets",
            title="Сменить или подобрать пресет",
            layer="dpi",
            what_changes="Меняет стратегию обхода; если пресет перестал работать — подберите новый в Blockcheck.",
            needs_root=False,
            reversible=True,
            page_key="strategies",
        ),
        Remedy(
            key="tunnel",
            title="Пустить трафик через туннель",
            layer="route",
            what_changes="Отправляет трафик выбранных приложений через VLESS/SOCKS: помогает, когда адрес заблокирован целиком.",
            needs_root=False,
            reversible=True,
            page_key="tunnel",
        ),
        Remedy(
            key="tor",
            title="Пустить трафик через Tor",
            layer="route",
            what_changes="Запускает системный Tor или Arti с локальным SOCKS; с мостами работает и там, где Tor заблокирован. Медленнее туннеля.",
            needs_root=False,
            reversible=True,
            page_key="tor",
        ),
        Remedy(
            key="dns",
            title="Сменить DNS-сервер",
            layer="dns",
            what_changes="Меняет DNS подключения через NetworkManager: до переподключения или постоянно; прежние значения возвращаются кнопкой.",
            needs_root=False,
            reversible=True,
            page_key="dns",
        ),
        Remedy(
            key="local-network",
            title="Сначала починить локальную сеть",
            layer="local",
            what_changes="Обход блокировок здесь не поможет: проблема до провайдера (Wi-Fi, роутер, кабель, DHCP).",
            needs_root=False,
            reversible=True,
            page_key=None,
        ),
        Remedy(
            key="isp-uplink",
            title="Проблема у провайдера",
            layer="local",
            what_changes="Обход блокировок не ускорит перегруженный или упавший канал провайдера; повторите проверку позже.",
            needs_root=False,
            reversible=True,
            page_key=None,
        ),
    )
}

VERDICT_REMEDIES: dict[str, tuple[str, ...]] = {
    "DPI_SELECTIVE": ("zapret", "presets"),
    "IP_BLOCK": ("tunnel", "tor"),
    "DNS": ("dns",),
    "LOCAL_NO_ROUTE": ("local-network",),
    "LOCAL_LINK_OR_ROUTER": ("local-network",),
    "ISP_UPLINK": ("isp-uplink",),
    "OK": (),
    "INCONCLUSIVE": (),
}


def remedies_for_verdict(code: str) -> tuple[Remedy, ...]:
    """Средства для кода вердикта net_verdict в порядке «сначала попробуйте это»."""

    return tuple(REMEDIES[key] for key in VERDICT_REMEDIES.get(str(code), ()))


def remedy_hint(remedy: Remedy) -> str:
    flags = ["нужен root" if remedy.needs_root else "без root", "обратимо" if remedy.reversible else "необратимо"]
    return f"{remedy.what_changes} ({', '.join(flags)})"


__all__ = ["Remedy", "REMEDIES", "VERDICT_REMEDIES", "remedies_for_verdict", "remedy_hint"]
