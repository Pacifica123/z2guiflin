# P04 — re-forensics, assumptions delta и перекомпиляция DAG

База: **owner-accepted post-P03f**, продуктовая версия `v0.7`.

P03f owner-host acceptance завершён с `HYPERPATCH ACCEPTANCE: PASS` и `READY_FOR_USE_WITHIN_P03`. P04 не переинтерпретирует этот PASS как доказательство универсального обхода DPI: он означает runnable readiness P03 на owner-host.

## Почему P04 разбит

Исходный P04 одновременно требовал: representation decision, единый immutable Plan, runtimeContext migration, ActionContract, GUI/CLI dispatcher, conflict grammar, metadata generation, lint/coverage и migration tests. Повторная форензика текущего HEAD показала, что попытка сделать это одним hyperpatch нарушила бы правило scope overflow и повысила бы риск self-confirming rewrite.

Поэтому текущий DAG перекомпилирован:

```text
P03f accepted / v0.7
  ↓
P04a  ACCEPTED: freeze evidence + version/docs sync + ontology/ActionContract foundation
  ↓
P04b  ACCEPTED: resource-location contract + normalized immutable Plan materializer
      + runtimeContext/preset compatibility migration
  ↓
P04c  ACCEPTED: executable ActionContract dispatcher + GUI projection
      + legacy CLI translator + contradiction gate
  ↓
P04d  CURRENT: 100% action coverage / migration / roundtrip / lint acceptance
  ↓
RC4 / v0.8 candidate (package 0.8.0rc4 until owner acceptance)
  ↓
P05
```

P05 по-прежнему ждёт завершения P04; search/help не должны строиться поверх нестабильной registry/dispatcher модели.

## P04a frozen evidence

Machine-readable fixture: `runtime/p04/p04a-frozen-evidence.json`.
Checker: `tools/gui_checks/check_p04a_re_forensics.py`.

Fixture связывает exact SHA-256 входов эксперимента с измеренными результатами. Если реализация меняет эти входы или результаты, checker требует новой re-forensics/semantic amendment вместо тихого переписывания критериев acceptance.

### REP experiment

Текущий shipping corpus проходит `source TXT -> normalized preset -> runtime argv` без execution-loss: порядок аргументов сохраняется точно. При этом `strategies/*.json` всё ещё содержит `runtimeArgs` рядом с `presetPath`; loader требует equality, но это две исполнимые репрезентации, которые не должны остаться двумя authorities в финальном P04.

Комментарии `.txt` не входят в execution argv: это information-loss, а не execution-loss. Поэтому P04a **не** делает вывод, что TXT обязан стать единственным canonical authoring format.

### CLI experiment

Legacy parser имеет большой flat-flag surface и current main использует последовательный first-match dispatch. Репрезентативная комбинация:

```text
--runtime-plan status --default-status
```

принимается argparse как валидная, хотя это два action selectors; затем первым срабатывает более ранний branch. Значит, до любого handler нужен explicit contradiction gate. P04a не выбирает заранее между typed subcommands и compatibility grammar: решение формы CLI остаётся за P04c после contract/Plan boundary.

### S-INSTALL shadow falsifier

`discover_layout()` по умолчанию выводит project root из расположения Python source (`Path(__file__).resolve().parents[2]`), а `pyproject.toml` устанавливает пакет из `gui/` без project resource bundle. Следовательно, supported outside-checkout resource resolution всё ещё **не доказан**.

Это не откладывается автоматически до P06: resource-location contract теперь dependency P04b, потому что Plan/ActionContract не должны навсегда кодировать repository-relative paths.

## P04b implemented boundary

Frozen evidence: `runtime/p04/p04b-frozen-evidence.json`. Checker: `tools/gui_checks/check_p04b_execution_plan.py`.

P04b establishes an explicit resource-root provenance contract (`root` → `ZAP2_RESOURCE_ROOT` → verified source checkout → fail-closed), then materializes runtime semantics into one location-independent `ImmutableExecutionPlan`. The Plan hash contains ordered argv and logical resource paths with SHA-256, not physical checkout/install paths.

Shipping `runtimeArgs` duplicates are not deleted yet because they remain compatibility data for older readers. When `presetPath` exists they are no longer execution authority: intentional drift is reported as a compatibility warning and cannot change Plan hash. Active-selection state reads `runtimeContextId/presetId` or legacy `profileId/strategyId`; disagreement is rejected.

S-INSTALL is only partially resolved: an external resource-root contract exists, but package-data bundling and writable-state separation remain open and must not be advertised as complete installation support.

## P04c implemented boundary

Frozen evidence: `runtime/p04/p04c-frozen-evidence.json`. Checker: `tools/gui_checks/check_p04c_action_dispatcher.py`.

P04c introduces canonical `--action <contract-id>` and an executable dispatcher for 28 runtime/default ActionContracts. Twenty-six legacy selector destinations translate to those contracts; `--runtime-plan` projects one selector destination into three canonical action IDs. The full post-P04b inventory of 117 top-level legacy selectors is checked before any handler, so contradictory migrated or unmigrated selectors fail closed instead of relying on first-match branch order.

GUI runtime controls consume ActionContract help metadata for Default workflow start/status/stop. This is a real shared projection, but not yet complete generated GUI/help/search metadata authority. Ninety-one selector destinations remain legacy-only and are explicitly P04d scope.

## Assumptions delta

Confirmed:

- P03 target-core generation/provenance semantics присутствуют в новой базе.
- На P04a shipping preset execution order round-tripped без потерь исполнения; P04b материализует эти semantics в immutable execution Plan.
- P04b resource-root contract отделяет semantic resource identity от physical checkout path.
- Legacy aliases можно вводить boundary-only без немедленного destructive storage rewrite; canonical/legacy disagreement fail-closed.

Falsified:

- Full S-INSTALL всё ещё нельзя считать решённым: external resource-root contract есть, package-data bundling и writable-state separation ещё нет.
- `runtimeArgs` нельзя считать независимым execution authority рядом с `presetPath`; на P04b это compatibility-only projection.
- Post-P04b legacy CLI first-match ambiguity была реальной; P04c закрывает её единым pre-handler contradiction gate.

Deferred by evidence:

- TXT vs structured canonical authoring source.
- Typed subcommands vs validated legacy compatibility grammar как канонический CLI surface.

## P04a historical acceptance

P04a acceptance являлся deterministic/read-only gate: он не запускает `nfqws2`, не меняет nftables и не требует повторного P03 network canary. Один orchestration entrypoint:

```bash
bash meta_tools/hyperpatch_acceptance.sh --p04a
```

PASS marker: `READY_FOR_USE_WITHIN_P04A`.

## P04b acceptance

P04b также проверяется read-only orchestration без root/network mutation:

```bash
bash meta_tools/hyperpatch_acceptance.sh --p04b
```

PASS marker: `READY_FOR_USE_WITHIN_P04B`. После него следующий bounded node — P04c.

## P04c acceptance

```bash
bash meta_tools/hyperpatch_acceptance.sh --p04c
```

PASS marker: `READY_FOR_USE_WITHIN_P04C`. После него следующий bounded node — P04d.


## P04d implemented boundary

P04d переводит все 117 historical selector destinations в ActionContracts и удаляет first-match action authority из `main()`. Catalog/dispatcher закрыт как 119/119, generated compatibility metadata проверяется byte-for-byte, а canonical `--operand` сохраняет параметры legacy selector-команд без второго registry. Frozen evidence: `runtime/p04/p04d-frozen-evidence.json`; acceptance: `bash meta_tools/hyperpatch_acceptance.sh --p04d`. До owner PASS это RC4 candidate, а не принятый final `v0.8`.


## Post-P04d owner acceptance / closure

P04d/RC4 принят владельцем: `HYPERPATCH ACCEPTANCE: PASS`, `READY_FOR_USE_WITHIN_P04D`. Исторические разделы выше сохраняют состояние предположений на соответствующем HEAD и не переписываются задним числом. Отдельный owner receipt находится в `runtime/p04/p04d-owner-acceptance-receipt.json`. После нового re-forensics product transition доказан и promotion выполнен как `v0.8` / `0.8.0`. P04 закрыт; новый DAG начинается с provisional P05. Текущий handoff: `V08_RELEASE_P05_HANDOFF.md`, initial P05 PRE: `P05_REFORENSICS.md`.
