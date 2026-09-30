# v0.8 — закрытие P04 и handoff в P05

## Основание перехода

База этого решения — owner-accepted P04d/RC4. На целевой машине владельца `hyperpatch_acceptance.sh --p04d` завершился:

```text
HYPERPATCH ACCEPTANCE: PASS
readiness: READY_FOR_USE_WITHIN_P04D
```

Owner evidence зафиксирован отдельным receipt в `runtime/p04/p04d-owner-acceptance-receipt.json`. Receipt фиксирует факт принятия и provenance пути evidence на owner-host, но не притворяется переносимой копией этих host-local файлов.

По bump protocol проекта переход `0.7 -> 0.8` допускается только после принятого product-state transition и нового re-forensics. P04 выполнил именно такой переход:

- P04a зафиксировал post-P03f ontology и исходные REP/CLI/S-INSTALL falsifiers;
- P04b сделал `ImmutableExecutionPlan` единственной исполнимой materialization authority;
- P04c ввёл executable `ActionContract` dispatcher и общий contradiction gate;
- P04d закрыл все 117 historical selector destinations, 119/119 ActionContracts/handlers, generated metadata и canonical/legacy roundtrip;
- owner-host P04d acceptance подтверждён отдельно от deterministic implementation evidence.

Следовательно, **P04 закрыт**. prerelease marker `0.8.0rc4` больше не несёт полезной неопределённости: product version повышается до **`v0.8` / `0.8.0`**. Это не означает универсальную стратегию обхода DPI и не меняет environment-dependent границу сетевых результатов.

## Что остаётся вне v0.8

Promotion не закрывает задачи другой природы:

- полный S-INSTALL package-data bundle и separation writable `.zap2` state от immutable resources остаются для productization/P06;
- AUR/updater и финальная distribution lifecycle не входят в P04;
- конкретная стратегия по-прежнему может перестать работать после изменения DPI, маршрута, DNS или приложения;
- Discord Voice/UDP и прозрачный tunnel/VPN lane остаются отдельными capability-задачами.

Эти пункты не фальсифицируют продуктовый переход P04: v0.8 фиксирует единые Plan/ActionContract semantics и безопасную command authority, а не внешний сетевой результат.

## Re-forensics после P04d

На новом HEAD подтверждено:

- ActionContract catalog: 119 контрактов, 119 executable handlers;
- historical CLI closure: 117/117 selector destinations, legacy-only = 0;
- P04d generated bindings остаются воспроизводимыми;
- P03 generation identity остаётся отдельным обязательным regression predicate;
- глобального action/concept search index и palette ещё нет;
- текущая `action_projection_rows()` — компактная projection, а не поисковый индекс;
- rich contextual help ещё не закрыт: `deep_help` не заполнен, focus/location покрывают только малую часть действий;
- P01 `EvidenceGraph`/`CapabilityVerdict` и P02 runtime resource state уже существуют как зависимости для P05 health projection.

Frozen measurements находятся в `runtime/p04/v08-release-evidence.json`.

## Перекомпилированный DAG

```text
v0.8 accepted P04 closure
→ P05 discoverability/help/unified health UX
→ RC5 / version transition candidate (SemVer только после acceptance + re-forensics)
→ P06 docs/release/productization
→ P07 v1 qualification
```

Ни один будущий номер версии не считается заранее назначенным. После принятого P05 снова выполняется `new HEAD -> re-forensics -> assumptionsΔ -> DAG/version recompilation`.

## P05 — подготовленный контракт задачи

Исходный RA thesis сохраняется, потому что P04 устранил prerequisite instability:

> product breadth -> tested global action/concept discovery + compact contextual help + evidence errors + health projections; no new authority.

Зависимости P05 теперь имеют фактическую базу:

- **P04:** стабильные executable `ActionContract` и generated projection;
- **P01:** typed `EvidenceGraph` / `CapabilityVerdict` для network/app capability truth;
- **P02:** runtime ownership/resource state и `next_safe_action` для локального health.

P05 должен сделать global palette/search по actions/settings/concepts для RU/EN/technical terms, contextual help, structured errors и aggregate health, но всё это является **projection**, а не новой semantic authority.

### Инварианты P05

- search index выводится из ActionContracts/concepts и не становится третьим registry;
- search/invoke не обходит privilege, Plan или confirmation;
- mutating/privileged actions не получают unsafe direct invoke;
- help использует те же semantic IDs, что executable contracts;
- error envelope должен разделять `cause + evidence + nextAction`;
- aggregate health не повышает lower-level UNKNOWN/FAIL до зелёного статуса;
- historical docs не становятся default current help;
- существующий page-local preset search остаётся отдельным инструментом и не подменяется global palette.

### Falsifiers перед первым P05 hyperpatch

Первый P05 PRE обязан остановить/перекомпилировать scope, если обнаружится хотя бы одно:

1. для полезного поиска приходится вводить независимый ручной action registry;
2. focus target нельзя связать с GUI без дублирования semantic IDs;
3. invoke из palette требует обхода существующего dispatcher/confirmation;
4. health aggregation требует свести typed EvidenceGraph к одному scalar readiness;
5. search/help scope настолько велик, что перестаёт помещаться в один reviewable hyperpatch — тогда P05 делится, а не ослабляет acceptance.

## Acceptance этого release/handoff patch

```bash
bash meta_tools/hyperpatch_acceptance.sh --v08-release
```

Успешный marker:

```text
HYPERPATCH ACCEPTANCE: PASS
readiness: READY_FOR_P05
```

Этот PASS подтверждает promotion metadata, сохранение P04/P03 semantic evidence, structural gate и полный deterministic regression. Он не запускает root/network canary и не утверждает, что P05 уже реализован.
