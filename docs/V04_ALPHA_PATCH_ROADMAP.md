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

Синхронизировать то, что проверяется Blockcheck, с тем, к чему затем применяется
Default workflow:

- добавить недостающие Discord hostlist entries, особенно `gateway.discord.gg`,
  `cdn.discordapp.com`, `media.discordapp.net`;
- документировать, что generated Discord strategy должна запускаться на hostlist,
  где эти targets реально присутствуют;
- не удалять YouTube entries из default hostlist;
- не пытаться автоматически объединять несовместимые `nfqws2` args.

Ожидаемый результат: если Blockcheck нашёл стратегию для Discord target, runtime
не теряет этот target на стадии применения.

### Stage 5 — service-aware export и Strategy UX

Уменьшить риск выбора «не той» стратегии:

- generated strategy names/metadata должны отражать `youtube-basic`,
  `discord-desktop` или `custom`;
- вкладка `Стратегии` должна показывать сервисный контекст;
- active strategy для Default profile остаётся одной выбранной стратегией;
- пользователь явно понимает, что переключение с YouTube strategy на Discord
  strategy меняет текущий фокус запуска.

Ожидаемый результат: выбор Discord strategy становится таким же понятным, как
текущий выбор YouTube strategy.

### Stage 6 — owner verification loop для Discord non-voice

Собрать owner-facing проверочный сценарий:

- прогнать Discord preset;
- экспортировать `AVAILABLE` strategies;
- выбрать generated Discord strategy;
- запустить Default workflow;
- полностью перезапустить desktop Discord;
- зафиксировать, что работает: login, gateway, список серверов, чаты, CDN/media;
- зафиксировать, что не работает, отдельно от voice.

Ожидаемый результат: есть evidence log, по которому можно понять, достаточно ли
доменного подхода для desktop Discord non-voice.

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
