# Матрица наблюдений Discord

Статус: справка по реализованному инструменту Stage 7o2.

Матрица приводит разные эксперименты к одному формату и не позволяет сравнивать их «по памяти». Она не добавляет новую стратегию и не запускает внешние scripts.

## Строки

| Строка | Назначение |
|---|---|
| `no zapret baseline` | Наблюдение при остановленном Zap2 runtime. |
| `diagnostic pktdebug` | Проверка, что цепочка наблюдения видит нужный трафик. |
| `current v2 strategy` | Повторная проверка `community-discord-syndata-edge-flow-v2`. |
| `kartavkun-like multisplit` | Linux reference-кандидат с multisplit-подходом. |
| `fake_tls_auto-like` | Кандидат generic TLS fake на базе идей zapret2. |
| `simple_fake-like` | Кандидат по мотивам Flowseal simple fake. |

## Команды

Показать plan:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-plan
```

Собрать отчёт из уже сохранённых наблюдений:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-report
```

Отчёты сохраняются в:

```text
.zap2/runtime/reports/discord-observation-matrix-*.json
.zap2/runtime/reports/discord-observation-matrix-*.md
```

## Цикл одной строки

1. Полностью закрыть Discord.
2. Выбрать стратегию строки.
3. Запустить Default workflow через owner confirmation.
4. Запустить guided probe с правами чтения nft counters.
5. Открыть Discord только после `MANUAL ACTION`.
6. Дождаться завершения окна наблюдения.
7. Остановить workflow.

## Правило продвижения

Кандидат не становится рекомендуемым из-за наличия во внешнем проекте. Нужна измеримая разница относительно baseline:

- состояние endpoint;
- delta counters;
- появление SYN+ACK;
- изменение Send-Q;
- изменения debug/log;
- переход updater на следующий этап.

## Runner строки

Одна строка запускается так:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row <row-id>
```

Подробное состояние runner: `DISCORD_OBSERVATION_MATRIX_ROW_RUNNER.md`.
