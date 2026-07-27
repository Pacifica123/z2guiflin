"""Каталог Discord Voice-профилей, перенесённых в Linux/nfqws2.

Модуль не запускает сеть. Он фиксирует происхождение профилей и объясняет,
какие Windows/WinDivert части заменены Linux capturePolicy поверх nftables.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..project_paths import discover_layout
from .presets import load_preset


DISCORD_VOICE_PRESET_IDS = (
    "discord-voice-upstream-conservative",
    "discord-voice-flowseal-narrow",
    "discord-voice-guiwin-wide",
)


@dataclass(frozen=True)
class DiscordVoiceProfileInfo:
    preset_id: str
    title: str
    source_family: str
    udp_ports: tuple[str, ...]
    l7: tuple[str, ...]
    payloads: tuple[str, ...]
    repeats: int
    risk: str
    source_notes: tuple[str, ...]

    def to_text(self, *, root: Path | None = None) -> str:
        entry = load_preset(self.preset_id, root)
        profile = entry.preset.profiles[0]
        lines = [
            f"Discord Voice profile: {self.preset_id}",
            f"title: {self.title}",
            f"source family: {self.source_family}",
            f"UDP capture: {', '.join(self.udp_ports)}",
            f"L7: {', '.join(self.l7)}",
            f"payloads: {', '.join(self.payloads)}",
            f"fake repeats: {self.repeats}",
            f"risk: {self.risk}",
            f"runtime profile: {profile.traffic_filter.summary}",
            f"runtime strategy: {profile.strategy_label}",
            "executes now: no",
            "requires sudo now: no",
            "mutates firewall/services now: no",
            "source notes:",
            *(f"  - {item}" for item in self.source_notes),
        ]
        return "\n".join(lines)


VOICE_PROFILES = (
    DiscordVoiceProfileInfo(
        preset_id="discord-voice-upstream-conservative",
        title="Discord Voice upstream conservative",
        source_family="bol-van/zapret2 Linux custom.d examples",
        udp_ports=("50000-50099",),
        l7=("discord",),
        payloads=("discord_ip_discovery",),
        repeats=2,
        risk="узкий диапазон; не ловит отдельный STUN за пределами Discord media ports",
        source_notes=(
            "Основано на core/zapret2/init.d/custom.d.examples.linux/50-discord-media.",
            "WinDivert raw-part не нужен: Linux nft capture задаётся через capturePolicy и filter-udp.",
        ),
    ),
    DiscordVoiceProfileInfo(
        preset_id="discord-voice-flowseal-narrow",
        title="Discord Voice Flowseal narrow",
        source_family="Flowseal zapret-discord-youtube + zapret2 GUI Windows",
        udp_ports=("19294-19344", "50000-50100"),
        l7=("stun", "discord"),
        payloads=("stun", "discord_ip_discovery"),
        repeats=6,
        risk="средний; два известных голосовых диапазона, без захвата всего UDP",
        source_notes=(
            "Flowseal general*.bat использует UDP 19294-19344,50000-50100 и L7 discord,stun.",
            "Windows fake-discord/fake-stun blob заменён нулевым UDP blob из upstream zapret2 примеров.",
            "Windows --wf-* и --dpi-desync-* не исполняются; перенесена только смысловая nfqws2-схема.",
        ),
    ),
    DiscordVoiceProfileInfo(
        preset_id="discord-voice-guiwin-wide",
        title="Discord Voice GUI Windows wide L7",
        source_family="zapret2-gui_windows winws2 builtins",
        udp_ports=("443-65535",),
        l7=("stun", "discord"),
        payloads=("stun", "discord_ip_discovery"),
        repeats=6,
        risk="высокий capture envelope; nfqws2 действует только после L7 match, но очередь получает широкий UDP диапазон",
        source_notes=(
            "Default/general game-filter presets используют широкий --wf-udp-out=443-65535.",
            "Профиль Голосовые звонки/чаты использует filter-l7=stun,discord и payload=stun,discord_ip_discovery.",
            "IP-set Discord UDP ветки оставлены reference-only: исходный ipset-discord.txt отсутствует в переданном архиве.",
        ),
    ),
)


def list_discord_voice_profiles() -> tuple[DiscordVoiceProfileInfo, ...]:
    return VOICE_PROFILES


def get_discord_voice_profile(preset_id: str) -> DiscordVoiceProfileInfo:
    for item in VOICE_PROFILES:
        if item.preset_id == preset_id:
            return item
    raise ValueError(
        f"Неизвестный Discord Voice preset: {preset_id}. "
        f"Доступно: {', '.join(DISCORD_VOICE_PRESET_IDS)}"
    )


def discord_voice_profiles_to_text(*, root: Path | None = None) -> str:
    layout = discover_layout(root)
    lines = [
        "Discord Voice source bridge",
        f"project root: {layout.root}",
        "executes now: no",
        "requires sudo now: no",
        "mutates firewall/services now: no",
        "selection rule: это альтернативы; одновременно включать все три не требуется",
        "HAR boundary: browser HAR не видит RTP/SRTP/Discord UDP media packets и не выбирает voice preset автоматически",
        "",
    ]
    for index, item in enumerate(VOICE_PROFILES, 1):
        lines.extend(
            [
                f"{index}. {item.preset_id} — {item.title}",
                f"   source: {item.source_family}",
                f"   UDP: {', '.join(item.udp_ports)}; L7: {', '.join(item.l7)}; payload: {', '.join(item.payloads)}",
                f"   repeats: {item.repeats}; risk: {item.risk}",
            ]
        )
    lines.extend(
        [
            "",
            "Рекомендуемый порядок проверки:",
            "  1. discord-voice-upstream-conservative",
            "  2. discord-voice-flowseal-narrow",
            "  3. discord-voice-guiwin-wide только если узкие варианты не дали результата",
        ]
    )
    return "\n".join(lines)
