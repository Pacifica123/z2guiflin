# Итог hyperpatch — P04c ActionContract dispatcher / CLI contradiction gate

База: owner-accepted P04b (`READY_FOR_USE_WITHIN_P04B`), post-P04b lineage `ac813de`. Product baseline остаётся `v0.7`; `v0.8` ещё не присваивается.

## Что делает P04c

- добавляет pure `ActionContract` catalog для bounded runtime/default workflow slice;
- добавляет canonical `--action <contract-id>` selector;
- переводит 26 legacy selector destinations в 28 canonical ActionContracts (включая три значения `--runtime-plan`);
- вводит единый pre-handler contradiction gate для всех 117 post-P04b legacy top-level selectors;
- migrated legacy aliases и canonical `--action` идут через один executable dispatcher;
- сохраняет одиночные пока ещё unmigrated legacy actions, но запрещает им конкурировать с другими selectors;
- GUI Default workflow tooltips проецируются из тех же ActionContracts;
- фиксирует P04c evidence в `runtime/p04/p04c-frozen-evidence.json`;
- добавляет deterministic checker и `hyperpatch_acceptance.sh --p04c`.

## Frozen evidence

- legacy selector inventory: 117/117 совпадает с actual top-level branch AST;
- ActionContracts: 28, handlers: 28, catalog/dispatcher closed;
- migrated legacy selector destinations: 26;
- remaining legacy-only selector destinations: 91;
- representative migrated/unmigrated/canonical+legacy contradictions fail before handler;
- canonical `runtime.plan.status` и legacy `--runtime-plan status` дают идентичный output hash;
- GUI start/status/stop projection использует canonical contract metadata.

## Что P04c намеренно НЕ делает

- не меняет P03 network/DPI semantics или P04b immutable Plan authority;
- не выполняет root/network canary;
- не заявляет 100% contract coverage: 91 selector destination ещё legacy-only;
- не завершает generated help/search/docs projections;
- не присваивает `v0.8` и не объявляет P04 завершённым;
- не заявляет полный S-INSTALL PASS.

## Следующий DAG

`P04d(100% meaningful ActionContract coverage + remaining migration + lint/generated metadata + projection roundtrip) -> RC4/v0.8 candidate -> P05`.
