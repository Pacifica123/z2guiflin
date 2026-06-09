# v0.4-alpha Stage 1: roadmap выбора YouTube или Discord

`v0.4-alpha_stage_1` фиксирует план реализации цели `v0.4-*` по патчам. Это
документационный stage: он не меняет runtime, не добавляет новые firewall rules и
не обещает одновременную работу YouTube и Discord.

Главная цель цикла остаётся простой: в конце `v0.4-*` пользователь должен иметь
понятный выбор целевого сервиса и запустить рабочую цепочку хотя бы для одного
выбранного сервиса:

```text
выбрать YouTube -> прогнать/выбрать YouTube strategy -> запустить Default workflow
или
выбрать Discord -> прогнать/выбрать Discord strategy -> запустить Default workflow
```

Одновременная работа YouTube и Discord допускается как удачный побочный эффект,
но не является критерием готовности `v0.4-*`. Автоматическая композиция
нескольких сервисов в одну универсальную стратегию переносится на будущую веху.

## Почему первый шаг действительно небольшой

Для non-voice части desktop Discord текущая гипотеза такая: уже существующая
цепочка YouTube может быть повторена на Discord-доменах. То есть первый
реализационный шаг после этого документа должен быть не переписыванием runtime,
а service preset для Blockcheck и hostlist/runtime target alignment.

Базовый Discord target seed для первого non-voice прохода:

```text
discord.com
gateway.discord.gg
cdn.discordapp.com
discordapp.net
discord.media
media.discordapp.net
updates.discord.com
discord.gg
```

Ожидаемый результат первого Discord-прохода: desktop-клиент запускается,
подключается к gateway, показывает чаты и грузит базовые media/CDN ресурсы.
Голосовые каналы не входят в этот минимальный критерий.

## Термины цикла

### Service target preset

Именованный набор доменов/probes, который Blockcheck lab может подставить без
ручного ввода длинной строки. Минимальные presets цикла:

- `youtube-basic` — сохраняет уже подтверждённую YouTube-цепочку;
- `discord-desktop` — добавляет Discord desktop non-voice targets;
- `custom` — оставляет владельцу ручной ввод доменов.

### Active service target

Выбранный пользователем сервисный фокус текущего прогона. В `v0.4-*` он нужен не
для запрета второго сервиса, а для снижения неоднозначности: GUI должен явно
показывать, что сейчас пользователь подбирает или запускает стратегию под
YouTube, Discord или custom target.

### Service-aware generated strategy

Generated strategy должна сохранять достаточно metadata, чтобы пользователь видел
не только строку `nfqws2`, но и исходный сервисный контекст: preset, source target,
protocol family и путь к successful blockcheck log. Это не меняет смысл стратегии,
но предотвращает путаницу между YouTube и Discord результатами.

## План патчей v0.4-alpha

### Stage 1 — roadmap и критерии готовности

Текущий patch. Фиксирует:

- цель финального `v0.4-*` как выбор между YouTube и Discord;
- отсутствие обязательной гарантии одновременной работы;
- Discord non-voice как первый реализационный слой;
- voice/UDP как отдельную позднюю задачу;
- последовательность следующих патчей.

### Stage 2 — registry service target presets

Реализационный patch добавляет кодовый registry presets без изменения runtime apply:

- `youtube-basic` с текущими `youtube.com www.youtube.com`;
- `discord-desktop` с Discord target seed;
- `custom` как безопасный ручной режим;
- shared validation для доменов/URI без shell-like targets;
- unit tests на состав доменов, имена presets, default YouTube baseline и запрет опасных tokens.

Ожидаемый результат: в коде появляется единый источник правды для target lists,
но GUI ещё остаётся минимальным. Selector и CLI-флаг preset — задача Stage 3.

### Stage 3 — Blockcheck Lab preset selector

Текущий patch подключает Stage 2 registry к GUI и CLI:

- combobox `Service target` в Blockcheck Lab;
- автозаполнение доменного поля при выборе YouTube/Discord;
- preset-owned targets отображаются read-only, а ручные правки делаются через `custom`;
- CLI-флаг `--blockcheck-target-preset discord-desktop`;
- `--blockcheck-domains` остаётся ручным custom override;
- тесты подтверждают, что default поведение не ломает YouTube baseline.

Ожидаемый результат: Discord можно прогнать без ручного вписывания всех доменов.
Stage 3 всё ещё не меняет runtime apply и hostlist.

### Stage 4 — Discord hostlist/runtime alignment

Текущий patch синхронизирует то, что проверяется Blockcheck, с тем, к чему затем
применяется Default workflow:

- добавлены недостающие Discord hostlist entries, особенно `gateway.discord.gg`,
  `cdn.discordapp.com`, `media.discordapp.net`;
- default hostlist теперь покрывает полный `discord-desktop` non-voice seed из
  registry;
- YouTube entries не удалены и остаются baseline-путём;
- добавлен parser/validator, который проверяет drift между service target preset
  и hostlist;
- автоматическое объединение несовместимых `nfqws2` args не вводится.

Ожидаемый результат: если Blockcheck нашёл стратегию для Discord target, runtime
не теряет этот target на стадии применения через Default workflow hostlist.

### Stage 5 — service-aware export и Strategy UX

Текущий patch уменьшает риск выбора «не той» стратегии:

- `BlockcheckOptions` сохраняет `service_target_preset_id`;
- Blockcheck plan/log пишет `service target preset: ...` и
  `ZAP2_SERVICE_TARGET_PRESET=...`;
- exporter использует этот service id при генерации strategy id/title/metadata;
- generated JSON получает блок `serviceTarget`;
- вкладка `Стратегии` и CLI-детали показывают сервисный контекст;
- active strategy для Default profile остаётся одной выбранной стратегией;
- пользователь явно понимает, что переключение с YouTube strategy на Discord
  strategy меняет текущий фокус запуска.

Ожидаемый результат Stage 5: Discord-generated и YouTube-generated strategies
различимы без ручного открытия каждого JSON, но runtime всё ещё запускает только
одну явно выбранную strategy.

### Stage 6 — owner verification loop для Discord non-voice

Текущий patch добавляет owner-facing проверочный сценарий:

- CLI `--discord-verification-plan` показывает полную петлю проверки без исполнения;
- CLI `--discord-verification-template` создаёт `.zap2/verification/discord-non-voice-owner-check.md`;
- вкладка Blockcheck lab получает кнопку `Discord checklist`;
- сценарий ведёт владельца через Discord preset, export `AVAILABLE`, выбор generated Discord strategy и Default workflow;
- success checklist разделяет login/session, gateway, список серверов, чаты и CDN/media;
- failure buckets разделяют no-available, dead target, wrong strategy selection, gateway-only failure и CDN/media failure;
- voice/UDP, звонки и screen share явно исключены из критерия успеха.

Ожидаемый результат: владелец получает evidence log, по которому Stage 7 сможет
понять, достаточно ли доменного подхода для desktop Discord non-voice и какие
точечные исправления действительно нужны.

### Stage 7 — точечные исправления по результатам Discord проверки

Этот stage резервируется под реальные наблюдения владельца:

- dead targets;
- лишние или отсутствующие домены;
- конфликтующие protocols;
- неправильные имена generated strategies;
- regression в YouTube baseline.

Ожидаемый результат: Discord non-voice становится достаточно воспроизводимым для
перехода к beta-кандидату или к voice-исследованию.

### Stage 8 — optional Discord voice/UDP investigation

Не начинать до подтверждения non-voice слоя. Voice требует отдельного подхода:

- UDP queue scope;
- `--filter-udp`, а не только `--filter-l7=stun,discord`;
- STUN/Discord IP discovery payloads;
- отдельные риски широких UDP-диапазонов.

Ожидаемый результат: либо voice явно выносится за рамки `v0.4-*`, либо получает
собственный owner-approved plan без смешивания с non-voice baseline.

## Критерии готовности финального v0.4-* patch

Финальный patch цикла можно считать достигшим цели, если выполнены условия:

- YouTube baseline не утрачен: его можно выбрать как отдельный service target;
- Discord desktop non-voice можно выбрать как отдельный service target;
- Blockcheck lab не требует ручного запоминания всех Discord-доменов;
- generated strategies имеют понятный service context;
- Default workflow запускает выбранную стратегию через прежний confirmation/sudo
  safety boundary;
- владелец может выбрать YouTube или Discord и получить рабочий результат хотя
  бы для одного выбранного сервиса в своём окружении;
- документация честно говорит, что одновременная работа двух сервисов не
  гарантируется в `v0.4-*`.

## Что не делать внутри v0.4-alpha без отдельного решения

- Не вводить скрытый режим «лечить всё сразу».
- Не удалять подтверждённый YouTube путь ради Discord.
- Не считать Discord voice частью минимального non-voice успеха.
- Не запускать privileged changes без существующего owner-confirmed workflow.
- Не импортировать Windows GUI presets целиком: брать из них target knowledge, но
  не переносить Windows-specific WinDivert/wf-фрагменты в Linux runtime.
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

