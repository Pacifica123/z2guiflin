# Runner строки матрицы наблюдений Discord

Статус: справка по Stage 7o2a–7o2d.

## Команда

```bash
PYTHONPATH=gui python -m zap2_gui.app \
  --discord-observation-matrix-run-row <row-id>
```

Дополнительные параметры:

```text
--matrix-row-wait-seconds <0..600>
--matrix-row-no-wait
--matrix-row-auto
```

## Базовая строка

Для строки без Zapret runner требует остановленного managed workflow. Он не должен собирать baseline на фоне активного `nfqws2`, иначе сравнение теряет смысл.

## Строка стратегии

Runner:

1. проверяет строку и strategy ID;
2. выбирает стратегию в workspace;
3. проверяет build/runtime state;
4. подготавливает plan;
5. останавливается перед privileged boundary или продолжает при уже готовом состоянии;
6. запускает guided probe;
7. сохраняет отчёт.

## Почему root-запуск ограничен

Выбор стратегии меняет пользовательские workspace-файлы. Запуск всей команды от root может создать root-owned state и сломать обычный GUI workflow. Поэтому подготовка выполняется от владельца, а привилегированная фаза запускается отдельно.

## Исправления этапов

- Stage 7o2b исправил baseline state handling.
- Stage 7o2c добавил проверку готовности локальной сборки.
- Stage 7o2d добавил auto mode для безопасно автоматизируемых шагов.

## Граница

Runner не доказывает, что стратегия работает. Он только делает сбор наблюдения единообразным.
