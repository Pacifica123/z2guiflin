# P04 — re-forensics, assumptions delta и перекомпиляция DAG

База: **owner-accepted post-P03f**, продуктовая версия `v0.7`.

P03f owner-host acceptance завершён с `HYPERPATCH ACCEPTANCE: PASS` и `READY_FOR_USE_WITHIN_P03`. P04 не переинтерпретирует этот PASS как доказательство универсального обхода DPI: он означает runnable readiness P03 на owner-host.

## Почему P04 разбит

Исходный P04 одновременно требовал: representation decision, единый immutable Plan, runtimeContext migration, ActionContract, GUI/CLI dispatcher, conflict grammar, metadata generation, lint/coverage и migration tests. Повторная форензика текущего HEAD показала, что попытка сделать это одним hyperpatch нарушила бы правило scope overflow и повысила бы риск self-confirming rewrite.

Поэтому текущий DAG перекомпилирован:

```text
P03f accepted / v0.7
  ↓
P04a  freeze evidence + version/docs sync + ontology/ActionContract foundation
  ↓
P04b  resource-location contract + normalized immutable Plan materializer
      + runtimeContext/preset compatibility migration
  ↓
P04c  executable ActionContract dispatcher + GUI projection
      + legacy CLI translator + contradiction gate
  ↓
P04d  100% action coverage / migration / roundtrip / lint acceptance
  ↓
RC4 / v0.8 candidate
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

## Assumptions delta

Confirmed:

- P03 target-core generation/provenance semantics присутствуют в новой базе.
- Shipping preset execution order round-trips без потерь исполнения.
- Legacy aliases можно вводить boundary-only без немедленного destructive storage rewrite.

Falsified:

- S-INSTALL нельзя считать уже решённым.
- Current legacy CLI не отвергает противоречивые action selectors до handler.

Deferred by evidence:

- TXT vs structured canonical authoring source.
- Typed subcommands vs validated legacy compatibility grammar как канонический CLI surface.

## Acceptance текущего hyperpatch

P04a acceptance является deterministic/read-only gate: он не запускает `nfqws2`, не меняет nftables и не требует повторного P03 network canary. Один orchestration entrypoint:

```bash
bash meta_tools/hyperpatch_acceptance.sh --p04a
```

PASS marker: `READY_FOR_USE_WITHIN_P04A`.
