# Планы runtime

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
python tools/gui_checks/check_runtime_lifecycle.py
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


## Owner-rules plans Stage 12

Для системных правил используются отдельные plan id:

```text
runtime-default-manual-local-apply-owner-rules-plan
runtime-default-manual-local-revert-owner-rules-plan
```

Они не заменяют `runtime-default-manual-local-start-plan` и `runtime-default-manual-local-stop-plan`. Start/stop остаются верхнеуровневым workflow, а apply/revert являются их системной частью.

Каждый owner-rules plan обязан содержать:

- `planHash`;
- `confirmationRequired=true`;
- `containsRemoteBootstrap=false`;
- `containsUpstreamInstallerScript=false`;
- rollback notes до исполнения;
- список точечных `nft` argv без shell-склейки.

## Service plans Stage 13

Service plans имеют действия `install`, `start`, `stop`, `remove`. Они сохраняются через `.zap2/runtime/plans/` и подтверждаются обычным `--runtime-confirm`, потому что confirmation gate уже умеет привязывать owner decision к `planHash`.

В Stage 13 guarded execution доступен только для `install/remove`. `start/stop` остаются планами: они показывают будущие systemd-команды, но не исполняются adapter-ом. Это удерживает service mode отдельно от session mode и не превращает проект в скрытый автозапуск.

## Composite default plans

Stage 14 добавляет composite plans:

- `runtime-default-manual-local-default-start-workflow-plan`;
- `runtime-default-manual-local-default-stop-workflow-plan`.

Composite plan содержит child plans и их hashes. Execution разрешается только если подтверждён composite plan и сохранённые child plans совпадают с hashes внутри него. Это защищает от ситуации, когда владелец подтвердил один набор действий, а исполняется другой.
