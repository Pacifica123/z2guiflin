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

## Stage 3: GUI и CLI selector

`v0.4-alpha_stage_3` делает registry видимым в Blockcheck Lab:

- selector `Service target` показывает presets в стабильном порядке registry;
- `youtube-basic` остаётся выбранным по умолчанию и подставляет
  `youtube.com www.youtube.com`;
- `discord-desktop` подставляет полный non-voice seed для desktop Discord;
- `custom` не имеет фиксированных targets, разблокирует поле ввода и сохраняет
  последнюю ручную строку при переключении между preset-ами.

CLI получает аналогичный путь:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-plan   --blockcheck-target-preset discord-desktop
```

Если нужно вручную переопределить targets, используется старый явный ввод:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-plan   --blockcheck-target-preset custom   --blockcheck-domains "example.com api.example.com"
```

`--blockcheck-target-preset custom` без `--blockcheck-domains` считается ошибкой,
потому что custom preset не хранит фиксированный target list.

Stage 3 не меняет hostlist/runtime alignment. Поэтому Discord strategy, найденная
через selector, всё ещё требует следующего stage: убедиться, что Default workflow
применяет выбранные args к тем же Discord hostlist entries.

## Stage 4: hostlist/runtime alignment

`v0.4-alpha_stage_4` добавляет минимальный coverage contract между registry и
runtime hostlist. Теперь `profiles/hostlists/default.hosts` обязан покрывать
фиксированные targets preset-ов:

- `youtube-basic`;
- `discord-desktop`.

Для Discord Stage 4 явно добавляет недостающие entries:

```text
gateway.discord.gg
cdn.discordapp.com
media.discordapp.net
```

Также появился небольшой parser/validator в `service_targets.py`: он нормализует
строки hostlist, умеет сравнивать домены с URI-like targets и возвращает список
недостающих entries. Это не runtime auto-switching и не объединение стратегий:
цель только в том, чтобы strategy, найденная через Discord Blockcheck preset, не
потеряла эти же targets при запуске через Default workflow hostlist.

## Stage 5: service-aware export

`v0.4-alpha_stage_5` связывает registry не только с Blockcheck input и hostlist,
но и с generated strategy output. `BlockcheckOptions` теперь несёт
`service_target_preset_id`, а план запуска сохраняет его в двух местах:

```text
service target preset: discord-desktop (Discord desktop non-voice)
ZAP2_SERVICE_TARGET_PRESET=discord-desktop
```

Это нужно из-за sequential Blockcheck: успешный source log может содержать один
candidate-домен, например `gateway.discord.gg`, но экспорт не должен превращать
его в безымянную custom-стратегию. Если service id есть в логе, он считается
источником истины; для старых логов exporter пытается вывести preset из списка
доменов и только затем падает обратно в `custom`.

Generated strategy JSON теперь содержит:

```json
{
  "serviceTarget": {
    "presetId": "discord-desktop",
    "title": "Discord desktop non-voice",
    "exportedCandidate": "gateway.discord.gg"
  }
}
```

Strategy catalog остаётся plan-only. Service label помогает владельцу выбрать
правильную стратегию, но не запускает runtime и не объединяет несколько
стратегий автоматически.
