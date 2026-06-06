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


## Stage 9: генератор default runtime plans

Stage 9 использует эти контракты как основу для конкретных plan-only представлений `start`, `stop` и `status`. Генератор находится в `gui/zap2_gui/adapters/runtime_plan_generator.py` и строит план из `profiles/default.json`, `strategies/manual-local.json` и `BUILD_MAP.json` через local build adapter.

CLI:

```bash
PYTHONPATH=gui python -m zap2_gui.app --runtime-plan start --profile default
PYTHONPATH=gui python -m zap2_gui.app --runtime-plan stop --profile default
PYTHONPATH=gui python -m zap2_gui.app --runtime-plan status --profile default
```

Планы показывают будущие session/log/rollback paths, required artifacts, apply steps и rollback notes. Они не исполняются автоматическими проверками и не создают runtime state. `status` является полностью read-only планом. `start` и `stop` могут указывать, что будущий apply/revert потребует `sudo`, но это только metadata для будущего owner-confirmed executor.


## Prepared plan и plan hash

Stage 10 добавляет состояние prepared plan. Сгенерированный plan сериализуется в стабильный JSON-compatible payload, после чего для него считается SHA-256 `planHash`. Confirmation record хранит этот hash и флаги `expiresWhenPlanChanges=true`, `allowsAutomaticReuse=false`.

Это правило важно для будущего исполнения: пользователь подтверждает не абстрактный `start`, а конкретный план с конкретным набором секций, команд-preview, rollback notes, binary path, hostlists и safety flags.
