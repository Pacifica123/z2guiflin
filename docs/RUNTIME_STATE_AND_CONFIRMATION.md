# Runtime state, логи и confirmation gate

Stage 10 вводит локальный runtime state store в workspace проекта. Это ещё не executor и не запуск стратегии: слой только сохраняет plan-only данные, связывает подтверждение владельца с конкретным `planHash`, записывает rollback notes и ведёт журнал событий.

## Директория состояния

Локальное состояние создаётся в `.zap2/runtime/`:

```text
.zap2/
  runtime/
    plans/           сохранённые runtime plans
    confirmations/   подтверждения владельца
    sessions/        будущие session state файлы
    logs/            append-only runtime logs
    rollback/        rollback notes до исполнения
```

Эта директория относится к workspace владельца. Она не является bootstrap-слоем, не копирует файлы в `/opt`, не создаёт service unit, не меняет firewall и не требует `sudo`.

## CLI

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-prepare start --profile default
PYTHONPATH=gui python -m zap2_gui.app --runtime-confirm runtime-default-manual-local-start-plan
PYTHONPATH=gui python -m zap2_gui.app --runtime-log --profile default
```

`--runtime-prepare` делает только локальную подготовку:

- генерирует runtime plan через Stage 9 generator;
- сериализует plan payload в `.zap2/runtime/plans/<plan-id>.json`;
- считает стабильный SHA-256 `planHash`;
- сохраняет rollback notes в `.zap2/runtime/rollback/<plan-id>.md`;
- пишет событие `planned` в `.zap2/runtime/logs/<profile>.runtime.jsonl`.

`--runtime-confirm` читает сохранённый plan, заново проверяет hash его содержимого и создаёт confirmation record в `.zap2/runtime/confirmations/<plan-id>.confirmation.json`. Подтверждение не может быть автоматически переиспользовано и считается действительным только для конкретного `planHash`.

`--runtime-log` только читает JSONL-журнал. Он не чинит state, не запускает процесс и не выполняет rollback автоматически.

## Инварианты безопасности

Stage 10 допускает только workspace-only mutation. Разрешено создать и обновить `.zap2/runtime`, потому что это локальный журнал приложения. Запрещено:

- запускать `nfqws2`;
- вызывать `make`;
- вызывать `sudo`;
- менять firewall, routing, nftables, iptables, ipset или NFQUEUE;
- управлять `systemd`;
- исполнять upstream installer scripts;
- выполнять remote bootstrap через `curl` или `wget`.

Это нужно, чтобы будущий Stage 11/12 не начинался с прямого исполнения. Сначала у нас появляется проверяемый след: какой план подготовлен, какой hash подтверждён, где лежат rollback notes и какие события уже записаны.

## Что это даёт следующему этапу

Будущий session runner сможет требовать существующий prepared plan и owner confirmation. Будущий privileged apply/revert сможет сравнить текущий plan hash с подтверждённым hash и отказаться от действия, если plan изменился. Таким образом подтверждение становится привязанным к данным, а не к расплывчатой команде из истории терминала.
