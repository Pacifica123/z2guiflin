# Итог hyperpatch — P04b resource-location / immutable execution Plan

База: owner-accepted P04a (`READY_FOR_USE_WITHIN_P04A`), post-P04a HEAD `3fd28c6` lineage. Product baseline остаётся `v0.7`; `v0.8` ещё не присваивается.

## Что делает P04b

- вводит explicit resource-location contract: caller root → `ZAP2_RESOURCE_ROOT` → verified source-checkout → fail-closed;
- убирает ложное предположение, что `Path(__file__).parents[...]` является install layout;
- добавляет location-independent `ImmutableExecutionPlan` с ordered argv и logical resource SHA-256;
- встраивает normalized Plan в runtime start payload и сохраняет его hash;
- переводит runtime session input staging, P02 artifact inventory и nft port derivation на argv normalized Plan;
- демонтирует `runtimeArgs` как вторую execution authority: при наличии `presetPath` legacy field только compatibility metadata; drift даёт warning, но не меняет Plan;
- добавляет canonical aliases `runtimeContextId` / `presetId` в active-selection state и fail-closed проверку противоречащих legacy aliases;
- фиксирует P04b evidence в `runtime/p04/p04b-frozen-evidence.json`;
- добавляет deterministic checker и `hyperpatch_acceptance.sh --p04b` с полным regression в изолированных worker-копиях.

## Frozen evidence

- 18 shipping presets / 18 `presetPath`;
- 17 legacy `runtimeArgs` projections дают тот же Plan hash;
- intentional legacy drift не изменяет execution Plan;
- одинаковый resource tree в двух разных каталогах даёт одинаковый Plan payload/hash;
- canonical-only и legacy-only active selection дают одинаковый Plan hash;
- conflicting canonical/legacy aliases отклоняются;
- default normalized Plan resources готовы;
- final installed package bundle и writable-state separation **не** объявлены готовыми.

## Что P04b намеренно НЕ делает

- не меняет network/DPI semantics P03;
- не выполняет root/network canary;
- не удаляет legacy fields массовым storage rewrite;
- не вводит ActionContract dispatcher/CLI conflict gate — это P04c;
- не присваивает `v0.8` и не объявляет P04 завершённым;
- не заявляет полный S-INSTALL PASS.

## Следующий DAG

`P04c(ActionContract dispatcher + legacy CLI translator/conflict gate + GUI projection) -> P04d(coverage/migration/lint/roundtrip acceptance) -> RC4/v0.8 candidate -> P05`.
