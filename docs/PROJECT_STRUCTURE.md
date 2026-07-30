# Структура проекта

## Корень

```text
z2guiflin/
├── core/
├── gui/
├── docs/
├── profiles/
├── presets/
├── strategies/
├── runtime/
├── references/
├── tools/
├── tests/
├── meta_tools/
├── pyproject.toml
└── run.sh
```

## `core/`

Содержит vendored-копию `zapret2` и проектные метаданные импорта.

```text
core/zapret2/             upstream source tree
core/zapret2/UPSTREAM_IMPORT.*
core/zapret2/CORE_INVENTORY.json
core/zapret2/BUILD_MAP.json
```

Upstream-файлы не используются как место для логики GUI. Локальные изменения ядра должны быть явно отделены и задокументированы.

## `gui/`

Python package `zap2_gui`:

```text
models/       модели данных без системных действий
adapters/     filesystem/runtime/diagnostic orchestration
widgets/      страницы и элементы PyQt
windows/      главные окна
app.py        CLI
qt_app.py     GUI entry point
```

Адаптеры могут строить планы и читать локальное состояние. Реальные привилегированные действия должны проходить через confirmation и отдельный executor.

## `profiles/`

Workspace-контексты владельца:

- выбранная стратегия;
- hostlists;
- runtime defaults;
- локальные параметры среды.

Секреты и runtime state сюда не коммитятся.

## `presets/`

Пресет — упорядоченный список traffic-профилей. Текстовый формат совместим с моделью аргументов `nfqws2`, но Linux capture scope формируется отдельно через runtime adapter.

`presets/generated/` содержит экспортированные результаты. `presets/workspace/` — локальные и reference-пресеты.

## `strategies/`

JSON-каталог стратегий. Здесь хранятся capabilities, runtimeArgs, capturePolicy, source metadata и diagnostic hints.

Стратегия не запускается автоматически только из-за присутствия в каталоге.

## `runtime/` и `.zap2/`

`runtime/` содержит документацию и контракты.

Локальное изменяемое состояние хранится в `.zap2/`:

```text
.zap2/runtime/     plans, confirmations, sessions, logs, reports
.zap2/tunnel/      redacted tunnel profiles, configs and managed PID state
```

`.zap2/` не является частью patch payload.

## `references/`

Локальные сводки внешних проектов. Они используются для анализа и переноса идей, но не исполняются напрямую.

## `tools/`

- `gui_checks/` — стабильные read-only проверки;
- `experimental/` — прототипы;
- `lowlevel/` — низкоуровневые сетевые утилиты.

Проверки devctl не должны требовать реального `sudo`, сети или изменения firewall.

## `tests/`

Автономные unit/contract tests. Для runtime используются временные workspace и fake runners.

Реальный успех обхода DPI не является unit-тестом и подтверждается owner-report.

## `meta_tools/`

Инструменты процесса разработки, не входящие в runtime приложения. `meta_tools/devctl/` хранит reference-снимок формата devctl patch.
