"""Owner-facing Discord non-voice verification loop for v0.4-alpha.

The loop is deliberately evidence-oriented and read-only by default. It does not
probe the network itself, does not start Discord, does not select strategies and
does not mutate firewall/service state. It gives the owner a reproducible script
for the last manual check before Stage 7 fixes are based on real observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..models.service_targets import (
    SERVICE_TARGET_DISCORD_DESKTOP,
    get_service_target_preset,
    service_target_string,
)
from ..project_paths import discover_layout

DISCORD_NON_VOICE_REPORT_NAME = "discord-non-voice-owner-check.md"


@dataclass(frozen=True)
class DiscordVerificationLoop:
    """Static owner-check recipe for Discord desktop non-voice."""

    preset_id: str
    title: str
    targets: tuple[str, ...]
    gui_steps: tuple[str, ...]
    cli_steps: tuple[str, ...]
    success_checks: tuple[str, ...]
    failure_buckets: tuple[str, ...]
    excluded_checks: tuple[str, ...]

    @property
    def target_string(self) -> str:
        return " ".join(self.targets)

    def to_text(self) -> str:
        target_lines = [f"  - {target}" for target in self.targets]
        gui_lines = [f"  {idx}. {step}" for idx, step in enumerate(self.gui_steps, start=1)]
        cli_lines = [f"  {idx}. {step}" for idx, step in enumerate(self.cli_steps, start=1)]
        success_lines = [f"  [ ] {item}" for item in self.success_checks]
        failure_lines = [f"  - {item}" for item in self.failure_buckets]
        excluded_lines = [f"  - {item}" for item in self.excluded_checks]
        return "\n".join(
            [
                "Discord non-voice owner verification loop",
                f"service target preset: {self.preset_id} ({self.title})",
                "scope: desktop Discord login/gateway/chats/CDN/media; голос/UDP не входит в критерий успеха",
                "executes now: no",
                "requires sudo now: no",
                "mutates firewall/services now: no",
                "stores credentials: no",
                "",
                "Targets:",
                *target_lines,
                "",
                "GUI loop:",
                *gui_lines,
                "",
                "CLI loop:",
                *cli_lines,
                "",
                "Success checklist:",
                *success_lines,
                "",
                "Failure buckets to record:",
                *failure_lines,
                "",
                "Explicitly excluded from this loop:",
                *excluded_lines,
                "",
                "Evidence rule: сохраняйте конкретные наблюдения и timestamps; Stage 7 должен чинить только то, что подтверждено owner report.",
            ]
        )


def create_discord_non_voice_verification_loop() -> DiscordVerificationLoop:
    """Return the current Stage 6 verification loop for Discord desktop."""

    preset = get_service_target_preset(SERVICE_TARGET_DISCORD_DESKTOP)
    target_string = service_target_string(SERVICE_TARGET_DISCORD_DESKTOP)
    return DiscordVerificationLoop(
        preset_id=preset.preset_id,
        title=preset.title,
        targets=preset.targets,
        gui_steps=(
            "Остановить Default workflow, VPN и другие DPI-bypass процессы, чтобы Blockcheck не смешивал эффекты.",
            "Во вкладке Blockcheck lab выбрать Service target: Discord desktop non-voice.",
            "Оставить HTTPS TLS1.2, HTTPS TLS1.3 и HTTP/3 QUIC включёнными; HTTP можно включать только как дополнительную пробу.",
            "Запустить sequential Blockcheck и дождаться хотя бы одного AVAILABLE либо явного dead-target/no-available результата.",
            "Нажать «Создать стратегии» и убедиться, что generated strategy помечена service target discord-desktop.",
            "Во вкладке «Стратегии» выбрать generated Discord strategy для Default profile.",
            "Через «Обзор» подготовить/подтвердить/запустить Default workflow обычным owner-confirmed путём.",
            "Полностью закрыть desktop Discord, запустить его заново и проверить non-voice признаки ниже.",
        ),
        cli_steps=(
            f"PYTHONPATH=gui python -m zap2_gui.app --blockcheck-plan --blockcheck-target-preset {preset.preset_id}",
            f"PYTHONPATH=gui python -m zap2_gui.app --blockcheck-run --blockcheck-target-preset {preset.preset_id}",
            "PYTHONPATH=gui python -m zap2_gui.app --blockcheck-export-strategies",
            "PYTHONPATH=gui python -m zap2_gui.app --list-strategies",
            "PYTHONPATH=gui python -m zap2_gui.app --select-strategy <blockcheck-discord-desktop-...>",
            "PYTHONPATH=gui python -m zap2_gui.app --default-start-plan",
            "PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-<strategy>-default-start-workflow-plan",
            "sudo PYTHONPATH=gui python -m zap2_gui.app --default-start --confirm runtime-default-<strategy>-default-start-workflow-plan",
            "Полностью перезапустить desktop Discord и заполнить owner report template.",
        ),
        success_checks=(
            "Discord desktop открывается после полного перезапуска приложения.",
            "Login/session проходит или существующая сессия переподключается без бесконечного Connecting.",
            "Gateway работает: список серверов/каналов появляется, статус подключения стабилен несколько минут.",
            "Текстовые чаты читаются и хотя бы одно тестовое сообщение отправляется/получается.",
            "CDN/media работают: аватарки, иконки серверов и простое изображение/attachment грузятся.",
            "Обновления/asset endpoints не блокируют запуск клиента в этом окружении.",
        ),
        failure_buckets=(
            "blockcheck-no-available: ни один Discord target не дал AVAILABLE strategy.",
            "dead-target: конкретный target не проходит port precheck и должен быть заменён/исключён.",
            "strategy-export-mismatch: strategy создана, но service target label не discord-desktop.",
            "runtime-selected-wrong-strategy: Default profile запускает YouTube/custom strategy вместо Discord-generated strategy.",
            "gateway-only-failure: UI открылся, но gateway.discord.gg не подключается или висит Connecting.",
            "cdn-media-failure: чаты работают, но cdn/media/avatars/attachments не грузятся.",
            "regression-youtube: после Discord проверки YouTube baseline перестал выбираться или запускаться прежним путём.",
        ),
        excluded_checks=(
            "Voice channels, звонки, screen share и UDP/STUN discovery.",
            "Гарантированная одновременная работа YouTube и Discord одной стратегией.",
            "Автоматическое объединение нескольких generated strategies.",
            "Портирование Windows WinDivert/wf/ipset presets целиком.",
            f"Ручной target override: Stage 6 проверяет именно registry seed `{target_string}`.",
        ),
    )


def discord_non_voice_verification_plan_to_text(root: Path | None = None) -> str:
    """Render the owner verification loop and point to the local template path."""

    layout = discover_layout(root)
    report_path = discord_non_voice_report_path(layout.root)
    loop = create_discord_non_voice_verification_loop()
    return "\n".join(
        [
            loop.to_text(),
            "",
            "Report template:",
            f"  path: {report_path}",
            "  create: PYTHONPATH=gui python -m zap2_gui.app --discord-verification-template",
            "  overwrites existing file: no",
        ]
    )


def discord_non_voice_report_path(root: Path | None = None) -> Path:
    """Return where the local owner report template should live."""

    layout = discover_layout(root)
    return layout.root / ".zap2" / "verification" / DISCORD_NON_VOICE_REPORT_NAME


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def discord_non_voice_report_template(created_at: str | None = None) -> str:
    """Return a Markdown template the owner can fill after the manual test."""

    loop = create_discord_non_voice_verification_loop()
    stamp = created_at or _utc_now()
    targets = "\n".join(f"- `{target}`" for target in loop.targets)
    success = "\n".join(f"- [ ] {item}" for item in loop.success_checks)
    failures = "\n".join(f"- [ ] {item}" for item in loop.failure_buckets)
    excluded = "\n".join(f"- {item}" for item in loop.excluded_checks)
    cli = "\n".join(f"{idx}. `{step}`" for idx, step in enumerate(loop.cli_steps, start=1))
    return f"""# Discord desktop non-voice owner verification report

Создано: `{stamp}`

Service target preset: `{loop.preset_id}` — {loop.title}
Scope: desktop Discord login/gateway/chats/CDN/media.
Voice/UDP: excluded from this report.

## Targets

{targets}

## Команды/действия, которые использовались

{cli}

## Условия перед проверкой

- [ ] Default workflow был остановлен перед Blockcheck.
- [ ] VPN/другие DPI-bypass процессы были выключены или явно отмечены ниже.
- [ ] Discord desktop был полностью закрыт перед финальным запуском.
- [ ] Выбранная strategy во вкладке «Стратегии» имеет service target `discord-desktop`.

## Success checklist

{success}

## Failure buckets

{failures}

## Explicitly excluded

{excluded}

## Наблюдения владельца

Дата/время локальной проверки:

Что сработало:

Что не сработало:

Какой generated strategy id был выбран:

Какие targets дали AVAILABLE в Blockcheck:

Какие targets были dead/no-available:

Содержимое `--default-status` после запуска:

Краткий вывод Discord desktop после полного перезапуска:

## Решение для Stage 7

- [ ] Достаточно для точечного Stage 7 fix.
- [ ] Нужен повторный Blockcheck с изменённым target list.
- [ ] Non-voice работает; можно обсуждать voice/UDP отдельно.
- [ ] Non-voice не подтверждён; voice/UDP пока не начинать.
"""


def write_discord_non_voice_report_template(root: Path | None = None, *, overwrite: bool = False) -> Path:
    """Create the local owner report template and return its path."""

    path = discord_non_voice_report_path(root)
    if path.exists() and not overwrite:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(discord_non_voice_report_template(), encoding="utf-8")
    return path


def write_discord_non_voice_report_template_to_text(root: Path | None = None, *, overwrite: bool = False) -> str:
    """Create the report template and render a short CLI response."""

    path = write_discord_non_voice_report_template(root, overwrite=overwrite)
    action = "created/kept"
    return "\n".join(
        [
            "Discord non-voice verification report template",
            f"path: {path}",
            f"state: {action}",
            "executes network checks now: no",
            "mutates firewall/services now: no",
            "next: run the owner verification loop, then fill this markdown file before Stage 7.",
        ]
    )
