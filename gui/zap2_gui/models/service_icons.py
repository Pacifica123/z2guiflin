"""Какому сервису принадлежит пресет, профиль или DNS-провайдер — для тематических иконок.

Только данные, без Qt: иконки рисует ui_icons по ключу отсюда.
"""

from __future__ import annotations

import colorsys
import hashlib
from typing import Iterable, Mapping

SERVICE_DISCORD = "discord"
SERVICE_YOUTUBE = "youtube"

# Порядок важен: ключи возвращаются в этом порядке.
_SERVICE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (SERVICE_DISCORD, ("discord", "dis.gd")),
    (SERVICE_YOUTUBE, ("youtube", "youtu.be", "googlevideo", "ytimg", "ggpht")),
)
_PRESET_SERVICE_IDS = {"discord-desktop": SERVICE_DISCORD, "youtube-basic": SERVICE_YOUTUBE, "youtube-googlevideo-auto": SERVICE_YOUTUBE}


def services_in_text(*texts: str) -> tuple[str, ...]:
    blob = " ".join(texts).lower()
    return tuple(key for key, markers in _SERVICE_MARKERS if any(marker in blob for marker in markers))


def services_for_profile(name: str, domains: Iterable[str] = ()) -> tuple[str, ...]:
    return services_in_text(name, *domains)


def services_for_preset(
    title: str,
    service_target: Mapping[str, object] | None = None,
    domains: Iterable[str] = (),
) -> tuple[str, ...]:
    """Сервисная цель Blockcheck и название важнее доменов профилей.

    Домены смотрятся, только когда ни цель, ни название сервис не называют: общий
    пресет с профилем Discord не должен выглядеть как «пресет Discord».
    """

    target = service_target or {}
    by_id = _PRESET_SERVICE_IDS.get(str(target.get("presetId") or target.get("id") or ""))
    named = services_in_text(title, str(target.get("title") or ""))
    keys = tuple(dict.fromkeys(((by_id,) if by_id else ()) + named))
    return keys or services_in_text(*domains)


def service_for_target_preset(preset_id: str) -> str:
    return _PRESET_SERVICE_IDS.get(preset_id, "")


# Буквенные значки DNS-провайдеров: короткая подпись и фирменный цвет. Логотипы не копируются.
DNS_BADGES: dict[str, tuple[str, str]] = {
    "cloudflare": ("CF", "#F38020"),
    "google": ("G", "#4285F4"),
    "quad9": ("Q9", "#C6007E"),
    "adguard": ("AG", "#68BC71"),
    "adguard-family": ("AG", "#4C9A5A"),
    "opendns": ("OD", "#F7941D"),
    "bizone": ("BZ", "#8A8A8A"),
    "dns4eu-protective": ("EU", "#1F4E9C"),
    "dns4eu": ("EU", "#3B6FC4"),
    "cleanbrowsing": ("CB", "#2BA5DE"),
    "controld-ads": ("CD", "#5C4EE5"),
    "controld": ("CD", "#7B70F0"),
    "dnssb": ("SB", "#0E8C7F"),
    "gcore": ("GC", "#FF4C00"),
    "cznic": ("CZ", "#1C6CB5"),
    "cira": ("CA", "#D52B1E"),
    "ffmuc": ("FF", "#DC0067"),
    "surfshark": ("SS", "#1EBFBF"),
    "wikimedia": ("W", "#3366CC"),
    "zapret-dns": ("Z", "#7E57C2"),
    "comss": ("CO", "#2E7D32"),
}


def dns_badge(provider_id: str, name: str) -> tuple[str, str]:
    """Подпись и цвет значка; для провайдеров без фирменного цвета — инициалы и стабильный цвет."""

    if provider_id in DNS_BADGES:
        return DNS_BADGES[provider_id]
    words = [word for word in name.replace(".", " ").replace("-", " ").split() if word]
    letters = "".join(word[0] for word in words[:2]).upper() or "?"
    hue = int(hashlib.sha256(provider_id.encode("utf-8")).hexdigest()[:4], 16) % 360
    red, green, blue = colorsys.hls_to_rgb(hue / 360, 0.45, 0.45)
    return letters, "#{:02X}{:02X}{:02X}".format(round(red * 255), round(green * 255), round(blue * 255))


__all__ = [
    "DNS_BADGES",
    "SERVICE_DISCORD",
    "SERVICE_YOUTUBE",
    "dns_badge",
    "service_for_target_preset",
    "services_for_preset",
    "services_for_profile",
    "services_in_text",
]
