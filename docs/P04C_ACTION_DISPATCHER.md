# P04c — executable ActionContract dispatcher и legacy CLI contradiction gate

База: owner-accepted P04b (`READY_FOR_USE_WITHIN_P04B`). Product baseline остаётся `v0.7` / `0.7.0`; P04c — development line toward `v0.8`, а не новый релиз.

## 1. Зачем нужен P04c

Post-P04b execution semantics уже материализуются в один `ImmutableExecutionPlan`, но CLI всё ещё имел 117 top-level selector destinations и исторический first-match dispatch. `argparse` мог принять несколько action selectors одновременно, после чего порядок `if` неявно определял, какой handler исполнится.

P04c вводит обязательную границу:

```text
argv
→ argparse
→ selector contradiction gate
→ canonical ActionContract
→ one dispatcher
→ handler
→ existing Plan/runtime boundary
```

Ни один handler мигрированного P04c slice не видит конкурирующие selector-флаги.

## 2. Canonical selector

Для contract-backed действий добавлена единая форма:

```bash
./run.sh --cli --action runtime.plan.status --profile default
./run.sh --cli --action default.workflow.status --profile default
./run.sh --cli --action privileged.executor.status
```

`--action` принимает только ID из `models/action_catalog.py`.

Legacy spellings остаются compatibility aliases. Например:

```bash
./run.sh --cli --runtime-plan status --profile default
```

переводится в тот же `runtime.plan.status` ActionContract и идёт через тот же dispatcher.

## 3. Contradiction gate покрывает весь legacy CLI

P04c фиксирует полный post-P04b inventory из 117 selector destinations. До любого legacy или canonical handler выполняется проверка ровно одного selector-а.

Примеры, которые теперь fail-closed:

```bash
./run.sh --cli --runtime-plan status --default-status
./run.sh --cli --list-presets --list-strategies
./run.sh --cli --action default.workflow.status --default-status
```

Даже если два spellings логически обозначают одно действие, одновременно использовать canonical и legacy selector нельзя: владелец должен выбрать одну форму invocation.

Обычные modifiers (`--profile`, `--confirm`, timeout/options конкретного action) selector-ами не считаются.

## 4. Что contract-backed в P04c

P04c мигрирует bounded runtime/default slice: 28 ActionContracts и 28 executable handlers. В него входят:

- runtime lifecycle contracts show/validate;
- runtime Plan start/stop/status;
- runtime logs;
- owner-rules plan/apply/revert/reconcile;
- runtime session start/status/stop;
- runtime nft/kernel status;
- default build dependency/plan/apply;
- default workflow plan/start/status/stop;
- bounded privileged executor status/install-plan;
- GUI-first overview.

Один legacy selector `runtime_plan` проецируется на три canonical contracts (`start`, `stop`, `status`), поэтому 28 contracts соответствуют 26 legacy selector destinations.

## 5. Что остаётся legacy-only

Из 117 исторических selector destinations 91 пока остаются legacy-only. P04c всё равно защищает их contradiction gate, но их metadata/handler ещё не перенесены в ActionContract authority.

Это намеренная граница hyperpatch. **P04d** должен закрыть 100% meaningful action coverage, migration/lint и projection roundtrip. До этого нельзя утверждать, что весь CLI уже ActionContract-backed.

## 6. GUI projection

`widgets/runtime_controls.py` больше не держит отдельные help-тексты для основных Default workflow actions. Tooltips `start/status/stop` берутся из тех же ActionContracts, которые использует CLI dispatcher.

Это первый реальный GUI projection из executable contract authority. Полная генерация navigation/help/search metadata остаётся P04d/P05.

## 7. Safety invariants

P04c не меняет P02/P03 privilege и lifecycle semantics:

- mutating contracts не становятся `safeInvoke`;
- `--confirm` остаётся обязательным там, где его требовал существующий workflow;
- bounded-root actions продолжают идти через root-owned executor;
- P03 generation identity и P04b immutable Plan остаются нижележащей authority;
- acceptance P04c read-only и не запускает network/root canary.

## 8. Frozen evidence

`runtime/p04/p04c-frozen-evidence.json` фиксирует:

- 117/117 actual legacy branch selectors covered by compatibility grammar;
- 28 valid ActionContracts / 28 matching handlers;
- 26 migrated legacy selector destinations;
- 91 remaining legacy-only selector destinations;
- canonical/legacy runtime plan output equality;
- contradiction rejection before handler invocation;
- GUI projection from canonical contracts.

## 9. Acceptance

```bash
bash meta_tools/hyperpatch_acceptance.sh --p04c
```

PASS marker:

```text
HYPERPATCH ACCEPTANCE: PASS
readiness: READY_FOR_USE_WITHIN_P04C
```

Acceptance is deterministic/read-only: frozen P04c evidence, preserved P03 generation identity, structural gate and complete pytest corpus in isolated project copies.

## 10. Recompiled DAG

```text
accepted P04c
→ P04d 100% meaningful ActionContract coverage
       + remaining legacy migration
       + lint/generated metadata
       + CLI/GUI projection roundtrip acceptance
→ RC4 / v0.8 candidate
→ P05 discoverability/help unified UX
```

S-INSTALL package-data bundling and writable-state separation remain open; P04c does not claim that separate issue solved.
