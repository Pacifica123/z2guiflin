# ADR P04 — domain ontology и ActionContract boundary

Статус: **P04a/P04b/P04c accepted; P04d closes full ActionContract coverage and RC4 projections**.

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

`ActionContract` является декларацией **исполняемого** action и одновременно источником projection metadata. Видимый action без handler недопустим; internal/debug action должен быть помечен явно. P04c добавил bounded executable catalog/dispatcher и canonical `--action`; P04d расширяет authority на все 117 historical selectors. Итоговый catalog содержит 119 canonical actions и 119 handlers, remaining legacy-only selectors = 0.

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

P04a не выбирал TXT/JSON/новый IR «по вкусу». P04b оставляет authoring forms множественными, но фиксирует execution authority: `presetPath -> normalized semantics -> ImmutableExecutionPlan`. Legacy `runtimeArgs` при наличии `presetPath` является только compatibility projection; source provenance не входит в Plan hash.

## Safety projection

`safeInvoke=true` нельзя ставить на mutating/start/stop/launch action без отдельного prepare/confirm flow. Privilege class должна быть одной из `none | owner | bounded-root`.

## P04c CLI decision

CLI experiment подтвердил, что flat compatibility grammar можно оставить временно только при явном global contradiction gate. Поэтому canonical selector для contract-backed slice — `--action <contract-id>`, а legacy flags являются translator input. Canonical+legacy или несколько legacy action selectors одновременно reject pre-handler.
