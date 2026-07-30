# Перенос источников Discord Voice — v0.4-alpha Stage 8d

## Вывод

Discord Voice нельзя достоверно восстановить из browser HAR. Голосовой media-flow
идёт отдельно от HTTP/WebSocket запросов и использует UDP-пакеты, которых в HAR
нет. Поэтому Stage 8d разделяет две линии:

1. HAR workbench — web/API/gateway/CDN и возможный HTTP/3.
2. Discord Voice source bridge — UDP/STUN/Discord IP Discovery из готовых
   Flowseal, GUI Windows и upstream zapret2 конфигураций.

Эти линии сходятся только на уровне итогового пресета. HAR не выбирает voice
стратегию автоматически.

## Что перенесено

В каталог добавлены три Linux/nfqws2-пресета. Это альтернативы, а не три части
одного обязательного пресета.

| Preset | UDP capture | L7/payload | Назначение |
| --- | --- | --- | --- |
| `discord-voice-upstream-conservative` | `50000-50099` | `discord` / `discord_ip_discovery` | первый, минимальный кандидат |
| `discord-voice-flowseal-narrow` | `19294-19344,50000-50100` | `stun,discord` / `stun,discord_ip_discovery` | перенос общей Flowseal voice-ветки |
| `discord-voice-guiwin-wide` | `443-65535` | `stun,discord` / `stun,discord_ip_discovery` | широкий последний кандидат из GUI Windows |

Во всех трёх случаях Windows `--wf-*` не передаётся в `nfqws2`. Захват задаёт
`capturePolicy`, а runtime применяет его через текущую nftables/NFQUEUE схему с
owner UID. Windows `--dpi-desync-*` также не копируется буквально: используется
эквивалентная Zapret2 Lua-схема `fake`.

## Источники

Главный Linux-ориентир:

- `core/zapret2/init.d/custom.d.examples.linux/50-discord-media`;
- `core/zapret2/init.d/custom.d.examples.linux/50-stun4all`.

Flowseal даёт повторяющуюся узкую схему:

```text
UDP 19294-19344,50000-50100
L7 discord,stun
fake repeats=6
```

GUI Windows даёт отдельный каталог voice-стратегий и широкие built-in presets:

```text
--wf-udp-out=443-65535
--filter-l7=stun,discord
--payload=stun,discord_ip_discovery
```

Полный аудит сохранён в
`references/external/discord_voice_source_inventory.json`. В нём перечислены все
найденные Flowseal BAT, все entries каталогов `winws1/voice.txt` и
`winws2/voice.txt`, а также все built-in winws2 presets с voice-секцией.

## Что оставлено reference-only

Legacy winws1 варианты `discord_voice_dtls`, `badseq`, `md5sig`, `tamper` и
похожие параметры не переведены автоматически. У winws1 и nfqws2 разные команды
и разный capture layer. Механическая замена создала бы правдоподобный, но
непроверенный профиль.

IP-set voice-ветки GUI Windows также не исполняются: упоминаемый
`ipset-discord.txt` отсутствует в переданном архиве.

## Порядок проверки

1. Выбрать `discord-voice-upstream-conservative`.
2. Подготовить обычный runtime plan и проверить его args/nft capture.
3. Запустить только после owner confirmation.
4. Проверить вход в voice channel, подключение к RTC и двусторонний звук.
5. При провале перейти к `discord-voice-flowseal-narrow`.
6. `discord-voice-guiwin-wide` использовать последним и отдельно проверить
   посторонний UDP-трафик владельца.

Команда инвентаризации:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-voice-profiles
```
