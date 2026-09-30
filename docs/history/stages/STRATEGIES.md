# Стратегии

Stage 7 вводит каталог **стратегий**. Стратегия — это не shell script и не набор низкоуровневых команд. Это описание типа workflow, который GUI должен показать владельцу.

## Где лежат стратегии

```text
strategies/
  README.md
  catalog.json
  manual-local.json
  read-only-diagnostics.json
```

`strategies/catalog.json` перечисляет файлы стратегий и фиксирует общий safety contract: автоматические проверки не исполняют стратегии, а сами стратегии на Stage 7 являются plan-only описаниями.

## Текущие стратегии

`manual-local` — основная стратегия по умолчанию. Она следует философии `toolbox/apothecary`: GUI должен быть набором понятных инструментов, рецептов и планов, а не чёрным ящиком, который тайно применяет системные изменения.

`read-only-diagnostics` — безопасная стратегия-заглушка для будущего диагностического workflow. Она показывает, что каталог может содержать разные сценарии без немедленного исполнения.

## Что стратегия может описывать

Стратегия описывает:

- философию workflow;
- для чего она предназначена;
- последовательность высокоуровневых шагов вроде `inspect -> plan -> present`;
- capabilities, которые GUI может отобразить;
- ограничения Stage 7.

Стратегия не содержит команд `sudo`, не меняет службы, не управляет firewall и не запускается автоматически.

## Команды CLI

```bash
PYTHONPATH=gui python -m zap2_gui.app --list-strategies
PYTHONPATH=gui python -m zap2_gui.app --show-strategy manual-local
```

Так мы получаем основу для будущей вкладки `Стратегии`: сначала видимые данные и валидация, затем редактор профиля, и только позднее — owner-confirmed runtime lifecycle.

## v0.3-beta Stage 4: Default strategy import и GUI runtime controls

Stage 4 переносит первую базовую стратегию из Windows GUI: `Default v1 (game filter)`. Перенос частичный и контролируемый: оригинальный Windows preset хранится как reference, а Linux runtime получает только seed hostlist и минимальные `nfqws2`-совместимые Lua-аргументы. Полный WinDivert preset не исполняется напрямую.

Также Stage 4 переносит CLI build/start/stop/status workflow во вкладку `Обзор` PyQt shell. GUI не запускает `sudo` и не применяет firewall скрыто: он готовит планы, подтверждает plan id через существующий confirmation gate и показывает owner-команды для терминала.

## v0.3-dev Stage 6: generated strategies и выбор для Default

После Blockcheck lab каталог может пополняться локально сгенерированными
стратегиями:

```text
strategies/generated/
  blockcheck-youtube-com-YYYYMMDD-HHMMSS-01.json
  blockcheck-youtube-com-YYYYMMDD-HHMMSS-02.json
```

Эти файлы создаются из конкретных `AVAILABLE` строк последнего blockcheck log и
автоматически добавляются в `strategies/catalog.json`. Они остаются обычными
plan-only strategy data: сами по себе не запускают процессы и не меняют firewall.

Вкладка `Стратегии` теперь не placeholder: она показывает список catalog
strategies, детали выбранной стратегии и кнопку `Выбрать для Default`. Выбор
пишется в:

```text
.zap2/strategies/default.active-strategy.json
```

После выбора все следующие Default build/start/stop/status plans строятся уже
для выбранной strategy id. Если стратегия поменялась, старые confirmations
устаревают: нужно заново подготовить и подтвердить start-plan перед запуском.

CLI-эквивалент выбора:

```bash
PYTHONPATH=gui python -m zap2_gui.app --select-strategy <strategy-id>
```

Выбор стратегии не исполняется как сетевое действие. Это только локальное
состояние owner choice, которое последующие plan/confirmation этапы используют
как входные данные.

## v0.3-dev Stage 7: safe Blockcheck export source

Stage 7 меняет источник экспорта generated strategies. `strategies/generated/*.json` теперь создаются не из любого последнего Blockcheck лога, а из последнего лога, где были обнаружены реальные `AVAILABLE` nfqws2 strategy attempts. Такой лог сохраняется как `.zap2/blockcheck/logs/latest-successful-blockcheck.txt`.

Это защищает пользовательскую цепочку от ситуации, когда после удачного поиска стратегий пользователь запускает новый candidate с мёртвым TCP/443 port precheck. `last-blockcheck.txt` может стать диагностически неудачным, но кнопка «Создать стратегии» не потеряет предыдущий успешный источник.

## v0.3-stable и v0.4-alpha: service-specific generated strategies

`v0.3-stable` подтверждает, что generated strategies — не только тестовые JSON-файлы. В рабочем сценарии владелец может получить `AVAILABLE` строки из Blockcheck, экспортировать их, выбрать одну стратегию и затем запустить Default workflow так, что выбранная стратегия реально применяется к runtime.

Для `v0.4-alpha` каталог стратегий должен оставаться удобным при появлении Discord-целей. Желательное правило именования generated files:

```text
strategies/generated/blockcheck-<service-or-target>-<timestamp>-NN.json
```

Например, YouTube и Discord generated strategies должны быть различимы в списке без открытия JSON. Пока не нужно автоматически склеивать стратегии разных сервисов. Если для YouTube и Discord нужны разные `nfqws2` args, владелец выбирает одну активную strategy для Default profile и заново проходит plan/confirmation/start.


## v0.4-alpha Stage 5: service-aware generated strategies

Stage 5 добавляет в generated strategies явный service context. Экспорт из
Blockcheck больше не полагается только на первый домен в логе: он читает
`service target preset` из сохранённого плана и записывает его в JSON стратегии.

Пример ожидаемого имени для Discord candidate:

```text
strategies/generated/blockcheck-discord-desktop-gateway.discord.gg-YYYYMMDD-HHMMSS-01.json
```

Внутри strategy data появляется блок `serviceTarget`, а текстовые представления
`--list-strategies`, `--show-strategy` и вкладка `Стратегии` показывают service
label. Это снижает риск выбрать YouTube strategy при проверке Discord или
наоборот. Выбор всё ещё один на Default profile и не запускает систему без
отдельного owner-confirmed plan/start.


## v0.4-alpha Stage 6: проверка выбранной Discord strategy

Stage 6 не меняет формат strategy JSON, но добавляет owner verification loop вокруг уже выбранной strategy. После экспорта Discord-generated strategy владелец должен увидеть service label `Discord desktop non-voice (discord-desktop)`, выбрать эту strategy для Default profile, заново подготовить и подтвердить start-plan, а затем проверить desktop Discord после полного перезапуска приложения.

Результат проверки записывается в `.zap2/verification/discord-non-voice-owner-check.md`. Это помогает Stage 7 отличить проблемы выбора strategy от проблем gateway, CDN/media или отсутствующих targets. Voice/UDP остаётся отдельной будущей задачей, а не причиной считать non-voice strategy проваленной.
