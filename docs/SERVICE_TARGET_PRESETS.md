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


## Stage 6: owner verification loop

`v0.4-alpha_stage_6` использует registry не для нового runtime-режима, а для воспроизводимой проверки. Verification loop привязан к preset `discord-desktop` и проверяет ровно тот же target seed, который уже прошёл Stage 2–5: registry, selector, hostlist/runtime alignment и service-aware export.

Новые команды:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-verification-plan
PYTHONPATH=gui python -m zap2_gui.app --discord-verification-template
```

План напоминает владельцу, что success criteria относятся к login/session, gateway, чатам и CDN/media. Voice channels, UDP/STUN discovery и одновременная работа YouTube+Discord одной стратегией остаются явно исключёнными из Stage 6.
## v0.4-alpha Stage 7: failure-driven target coverage

`v0.4-alpha_stage_7` меняет акцент после первой личной проверки владельца: найденные `AVAILABLE` стратегии для `discord.com` оказались полезным сигналом, но не доказали прохождение desktop Discord updater. Поэтому Stage 7 добавляет evidence-first coverage loop.

Главные изменения:

- `discord-desktop` preset расширен target-ом `stable.dl2.discordapp.net`, который относится к updater/download layer.
- Blockcheck options получили candidate scan mode:
  - `stop-after-first-available` — удобен для уже подтверждённого YouTube baseline;
  - `scan-all-targets` — default для `discord-desktop`, потому что desktop Discord состоит из updater, app/API/gateway и CDN/media слоёв;
  - `skip-dead-targets-only` — сохраняет старую осторожную модель перехода только после dead-target evidence.
- GUI Blockcheck Lab получил selector `Candidate mode` и кнопку `Coverage`.
- Каждый single-candidate run сохраняется в `.zap2/blockcheck/logs/candidates/`.
- Per-target manifest `.zap2/blockcheck/logs/candidates/coverage-manifest.json` показывает status для каждого target: `available`, `unavailable`, `dead-target`, `unknown` или `not-tested`.
- Export generated strategies теперь берёт AVAILABLE candidate logs из coverage manifest и кладёт coverage snapshot прямо в strategy JSON.
- Strategy UX показывает coverage summary, чтобы `discord.com`-only успех больше не выглядел как подтверждение всего Discord desktop path.

Новый owner-facing диагностический контур:

```bash
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-plan \
  --blockcheck-target-preset discord-desktop \
  --blockcheck-scan-mode scan-all-targets

PYTHONPATH=gui python -m zap2_gui.app --blockcheck-coverage
PYTHONPATH=gui python -m zap2_gui.app --blockcheck-export-strategies
```

Ключевой критерий после Stage 7: если desktop Discord зависает на `Checking for updates`, сначала смотреть coverage по `updates.discord.com` и `stable.dl2.discordapp.net`, а не считать любую стратегию для `discord.com` достаточной.

