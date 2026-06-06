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
