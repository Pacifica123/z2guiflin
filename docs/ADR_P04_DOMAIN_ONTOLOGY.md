# ADR P04 — domain ontology и ActionContract boundary

Статус: **accepted for P04a foundation; execution migration not yet complete**.

## Решение

P04 использует стабильные понятия:

```text
runtimeContext
preset
trafficProfile
desyncAction
tunnelConnection
backend/core
runtimeResource
operation/action
Plan
probe
Evidence / Verdict / Capability
```

Глаголы действия должны называть эффект: `inspect/list/show`, `plan`, `validate`, `prepare`, `confirm`, `apply`, `revert`, `start`, `stop`, `reconcile`, `probe`, `launch`, `import`, `export`. Generic `run` остаётся только compatibility-термином там, где старый интерфейс ещё не мигрирован.

## Compatibility boundary

Старые имена не переписываются вслепую:

- `WorkspaceProfile.profile_id` остаётся читаемым, но канонический смысл — `runtimeContext`; P04a добавляет property `runtime_context_id`.
- `strategy_id` в workspace selection остаётся legacy storage/API field; канонический исполнимый объект — `preset`, поэтому добавлен `preset_id` alias.
- `profile` внутри `.txt` preset означает только `trafficProfile` (`--new` block), а не runtime context.

Миграция storage IDs должна быть детерминированной и не менять итоговый Plan hash там, где P04 обещает semantic equivalence.

## ActionContract

`ActionContract` является декларацией **исполняемого** action и одновременно источником projection metadata. Видимый action без handler недопустим; internal/debug action должен быть помечен явно. В P04a добавлен тип и validation invariants, но legacy 163-option CLI **ещё не объявлен migrated**.

```text
ActionContract
  id / label / aliases / keywords / shortHelp
  conceptLinks / effect / preconditions / privilege / capability
  handler / location / focusTarget / safeInvoke / deepHelp / legacyAliases
```

Metadata-only registry, существующий отдельно от handler/dispatcher, не считается ActionContract authority.

## Plan authority

Целевой инвариант P04 остаётся:

```text
many source/import representations
→ normalized semantics
→ exactly one immutable Plan(hash)
→ execution
```

P04a не выбирает TXT/JSON/новый IR «по вкусу». Выбор authoring/canonical representation разрешён только после roundtrip/loss evidence. Исполнимый порядок аргументов уже доказан как значимый и должен сохраняться.

## Safety projection

`safeInvoke=true` нельзя ставить на mutating/start/stop/launch action без отдельного prepare/confirm flow. Privilege class должна быть одной из `none | owner | bounded-root`.
