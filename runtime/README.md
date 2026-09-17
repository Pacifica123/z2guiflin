# Runtime lifecycle contracts

`runtime/` — это слой контрактов будущего запуска, применения, сессий, сервисного режима, логов, подтверждений и rollback notes. Stage 8 намеренно не является executor: здесь нет запуска `nfqws2`, нет `sudo`, нет firewall mutation, нет `systemd` и нет bootstrap.

## Зачем нужен этот слой

До Stage 8 проект уже умеет читать vendored-ядро, строить local build plan и показывать workspace-профили/стратегии. Следующий рискованный шаг — runtime lifecycle. Чтобы не превратить его в случайный набор shell-команд, Stage 8 сначала вводит общий язык:

- `run plan` — верхнеуровневый план запуска/остановки/status;
- `apply plan` — будущие системные изменения, отделённые от запуска процесса;
- `session plan` — будущий lifecycle локального процесса в текущей сессии;
- `service plan` — будущий service mode как отдельный режим;
- `confirmation` — явное подтверждение владельца, связанное с конкретным plan hash;
- `runtime event` — запись будущего журнала runtime-действий;
- `rollback notes` — заранее записанные заметки отката.

## Состав

```text
runtime/
  README.md
  schemas/
    runtime-plan.schema.json
    runtime-event.schema.json
    confirmation.schema.json
  examples/
    manual-local-start.contract.json
    manual-local-start.event.json
    manual-local-start.confirmation.json
```

Схемы описывают обязательные поля и safety-флаги. Примеры являются contract fixtures для тестов и документации. Они не являются инструкцией к исполнению.

## Safety boundary Stage 8

Автоматические проверки могут читать и валидировать эти файлы, но не могут исполнять планы. Любой настоящий runtime executor должен появиться отдельным патчем после того, как будут готовы state dir, логи, confirmation gate и rollback notes.

Запрещено смешивать этот слой с bootstrap:

```text
remote download -> install script -> service enable -> runtime start
```

Правильная цепочка для будущих патчей:

```text
profile/strategy -> runtime plan -> owner confirmation -> execute locally -> log -> rollback/revert
```


## Runtime state Stage 10

Контрактный слой Stage 8 и генератор Stage 9 теперь дополнены workspace state gate. Рабочее состояние живёт не в этой директории `runtime/`, а в локальной `.zap2/runtime/`, чтобы отделить committed contracts от пользовательского runtime-журнала.

`.zap2/runtime` создаётся только локальной командой владельца и хранит prepared plans, confirmations, future session state, logs и rollback notes. Этот слой не исполняет plans и не является bootstrap.

## Stage 11: runtime session runner

После Stage 11 runtime lifecycle получает первый guarded executor для `session`-части. Он использует `.zap2/runtime/sessions/` и `.zap2/runtime/logs/`, требует prepared/confirmed start-plan и не применяет системные правила.

Это означает, что `runtime/` остаётся контрактным слоем, а фактическое локальное состояние запуска хранится в `.zap2/runtime`. Контракты, планы, confirmation и session record должны оставаться связаны через `planId` и `planHash`.


## Stage 12: owner-confirmed apply/revert

После Stage 12 runtime lifecycle получает отдельный слой системных правил. Apply/revert больше не являются абстрактной строкой в runtime plan: они представлены typed-plan в `runtime_apply.py`, сохраняются в `.zap2/runtime`, подтверждаются через `planHash` и только затем могут быть исполнены владельцем.

Автоматические проверки не исполняют реальные `nft`-команды. Первый backend создаёт и удаляет только workspace-owned nftables table `inet zap2_u<uid>_<workspace>_<profile>` с owner marker. Apply выполняется единым checked batch, а read-only reconciliation не удаляет unknown/conflicting resources. Подробности: `docs/RUNTIME_OWNERSHIP_RECOVERY.md`.

## Stage 13: service plans

Runtime layer теперь включает service plans. Они описывают systemd mode отдельно от session mode:

```bash
PYTHONPATH=gui python -m zap2_gui.app --service-plan install --profile default
PYTHONPATH=gui python -m zap2_gui.app --service-plan remove --profile default
```

Guarded execution для `install/remove` требует сохранённого plan, `--runtime-confirm` и локального owner-controlled запуска. Автоматические проверки не вызывают `systemctl` и не пишут в `/etc/systemd/system`.

## Stage 14: default workflow

Composite default workflow сохраняет plans, rollback notes, confirmations, session state и logs внутри `.zap2/runtime`. Реальные действия допускаются только после owner confirmation и не относятся к bootstrap.
