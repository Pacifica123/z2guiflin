# GUI-first tables and copyable text

Дата: 2026-06-29

## Зачем

После GUI-first Overview стало видно, что один большой текстовый dump снова тянет пользователя в режим консольной отладки. Следующий слой UI должен показывать состояние как таблицу: выбранная стратегия, подготовленный plan, running session, owner-rules и итоговый verdict должны быть видны рядом.

При этом возможность копирования сохраняется: рядом с таблицей есть кнопка `Копировать таблицу`, которая кладёт в clipboard plain text/TSV. Нижнее текстовое окно остаётся для логов, probe reports и подробных действий, рядом с ним есть `Копировать вывод`.

## Модель

`GuiFirstRuntimeOverview.table_rows()` возвращает строки:

```text
section | field | value | status
```

`GuiFirstRuntimeOverview.to_table_text()` возвращает тот же набор в TSV-формате:

```text
section	field	value	status
```

GUI использует эти строки для `QTableWidget`, а copy button использует TSV. Значит визуальное представление и копируемый текст идут из одного источника.

## Что теперь видно в Overview

Таблица показывает:

- workspace profile;
- выбранную стратегию;
- стратегию подготовленного start-plan;
- running strategy;
- Default workflow state;
- nfqws2 session state/PID;
- owner-rules state;
- owner-rules strategy;
- NFQUEUE/table;
- итоговое состояние;
- следующее GUI-действие;
- issues.

Developer mode добавляет строки с plan id, session pid и developer hint, но по умолчанию эти детали скрыты.

## Почему это важно для последнего `.zap2`

Последний `.zap2` показал, что workflow реально запускался и штатно остановился. Но probe reports в GUI были трудны для чтения: часть verdict-ов относилась к запущенному workflow (`V1_NFT_COUNTER_READ_FAILED`), а последний verdict уже к остановленному workflow (`V0_WORKFLOW_NOT_RUNNING`). Таблица помогает разделить текущее состояние и результаты действий.

## Ограничение

Этот patch не чинит сам privileged Discord probe. Сейчас GUI-кнопка `Проверить Discord` всё ещё может упереться в `Operation not permitted` при чтении nft counters, если она вызвана без повышенных прав. Это отдельный следующий patch: privileged read-only probe через askpass/helper.
