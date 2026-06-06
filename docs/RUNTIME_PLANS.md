# Runtime plans

`runtime plans` — это машинно читаемые договоры будущих действий. Они живут в `runtime/` и описываются JSON-схемами. Stage 8 добавляет только контрактный слой: ни один plan не исполняется автоматически.

## Раскладка

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

## runtime-plan.schema.json

Основная схема описывает будущий план действия. В каждом плане должны быть:

- `planId` — стабильный идентификатор плана;
- `profileId` — workspace-профиль;
- `strategyId` — стратегия;
- `action` — действие вроде `start`, `stop`, `status`;
- `lifecycle` — Stage 8 boundary;
- `safety` — флаги подтверждения, sudo/service/firewall и запреты bootstrap;
- `sections` — секции `run`, `apply`, `session`, `service`;
- `rollbackNotes` — обязательные заметки отката.

На Stage 8 план обязан содержать все четыре секции, даже если часть из них пока остаётся описательной. Это защищает архитектуру от смешивания “запустить процесс” и “изменить систему”.

## runtime-event.schema.json

Runtime event — будущая запись журнала. Она связывается с `planId` и описывает факт вроде `planned`, `confirmed`, `started`, `stopped`, `failed`, `rolled-back` или `status`.

На Stage 8 events являются только примерами контрактов. Настоящие runtime logs появятся после state dir и confirmation gate.

## confirmation.schema.json

Confirmation contract описывает будущую подпись владельца под конкретным plan hash. Важные правила:

- confirmation не должен переиспользоваться автоматически;
- confirmation должен истекать при изменении плана;
- example-confirmation в Stage 8 не является настоящим разрешением;
- будущий executor не должен принимать подтверждение, которое не связано с конкретным сохранённым планом.

## CLI Stage 8

Для просмотра контрактов:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-contracts
```

Для валидации контрактов:

```bash
PYTHONPATH=gui python -m zap2_gui.app --validate-runtime-contracts
python tools/check_runtime_lifecycle.py
```

Эти команды читают файлы и проверяют инварианты. Они не выполняют планы.

## Инварианты безопасности

В runtime contracts Stage 8 должны оставаться истинными следующие утверждения:

```text
automaticChecksMayExecute = false
bootstrapMixedIn = false
requiresOwnerConfirmation = true
containsRemoteBootstrap = false
containsUpstreamInstallerScript = false
```

Если будущий патч меняет эти утверждения, он должен быть отдельным runtime execution patch с явным объяснением, проверками и rollback story.
