# Service target presets

`v0.4-alpha_stage_2` добавляет первый кодовый registry сервисных целей. Это
не новый runtime-режим и не автоматическое объединение сервисов. Registry нужен
как единый источник правды для тех доменов/URI, которые Blockcheck lab будет
подставлять в следующих патчах через GUI selector и CLI-флаг.

## Почему registry нужен до GUI selector

До Stage 2 базовый YouTube target был размазан как строка
`youtube.com www.youtube.com` в нескольких местах: adapter defaults, GUI поле и
CLI аргумент. Для Discord такой подход быстро стал бы хрупким, потому что
desktop-клиенту нужен не один домен, а набор API, gateway, update и media/CDN
targets. Registry фиксирует этот набор один раз и позволяет следующим stage
подключать его к GUI без нового копирования строк.

## Presets Stage 2

### `youtube-basic`

Проверенный baseline из `v0.3-stable`:

```text
youtube.com www.youtube.com
```

Этот preset остаётся default для `BlockcheckOptions`, GUI-поля и CLI
`--blockcheck-domains`, чтобы Stage 2 не ломал рабочую YouTube-цепочку.

### `discord-desktop`

Первичный Discord desktop non-voice seed:

```text
discord.com gateway.discord.gg cdn.discordapp.com discordapp.net discord.media media.discordapp.net updates.discord.com discord.gg
```

Назначение этого preset — первый практический слой Discord без voice/UDP:
login, gateway/WebSocket, updates и CDN/media. Голосовые каналы пока не входят в
минимальный критерий готовности.

### `custom`

Ручной режим без фиксированных targets. Он нужен, чтобы владелец мог продолжать
эксперименты с доменами/URI, но через ту же валидацию безопасных токенов.

## Граница безопасности

Registry принимает только домены/URI-подобные токены без пробелов и shell-like
символов. Значения вроде `discord.com;rm -rf /tmp/nope` или `$(whoami)`
отклоняются ещё до построения `sudo -A env ... blockcheck2.sh` команды.

Stage 2 не меняет `runtime_apply`, nftables scope, hostlist и Strategy UX.
Следующий ожидаемый шаг — Stage 3, где эти presets будут выведены в Blockcheck
Lab selector и CLI `--blockcheck-target-preset`.
