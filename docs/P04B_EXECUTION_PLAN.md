# P04b — resource-location contract и immutable execution Plan

База: owner-accepted P04a (`READY_FOR_USE_WITHIN_P04A`), продуктовая baseline остаётся `v0.7`.

P04b не меняет DPI-стратегии и не переписывает CLI. Его граница — устранить двойную execution authority до появления общего ActionContract dispatcher.

## 1. Resource-location contract

Исторический `discover_layout()` вычислял root через расположение Python-модуля. В checkout это работало, но обычный `site-packages` install мог молча получить несуществующий project root.

P04b вводит явный contract:

```text
explicit root
  > ZAP2_RESOURCE_ROOT
  > verified source-checkout fallback
  > fail closed
```

`source-checkout` fallback разрешён только если найден набор project sentinels. Установленный Python package без resource tree больше не трактуется как будто рядом существует полный checkout.

Это **не финальный S-INSTALL PASS**. В P04b ещё не выполнены:

- packaging всех project resources в install layout;
- отделение writable `.zap2` state от read-only resource tree;
- package/helper/service productization.

Контракт нужен сейчас, чтобы immutable Plan не кодировал случайный абсолютный путь текущего checkout.

## 2. Один normalized Plan

Новая модель `ImmutableExecutionPlan` содержит только исполнимую семантику:

```text
runtimeContextId
presetId
engine
buildTarget
runtimeArgs (ordered)
runtimeResource{kind, logicalPath, state, sha256}
```

Физический путь (`/home/.../project`, `/opt/...`, test temp dir) в hash не входит. File inputs связываются логическим resource path + SHA-256, поэтому перенос идентичного resource tree в другой каталог не меняет Plan hash, а изменение исполнимых байтов меняет его.

Authoring provenance (`presetPath`, legacy JSON projection) хранится вокруг Plan как materialization metadata и не является execution authority.

## 3. `runtimeArgs` теперь compatibility-only

Shipping corpus по-прежнему содержит 17 JSON-файлов с историческим `runtimeArgs`. P04b намеренно не делает массовый destructive rewrite этих файлов: они могут быть нужны старым readers/fixtures.

Правило loader теперь такое:

```text
presetPath exists
  -> parse presetPath
  -> canonical runtime argv
  -> materialize immutable Plan
  -> legacy runtimeArgs only compared as compatibility metadata
```

Если legacy `runtimeArgs` расходится с `presetPath`, execution **не** переключается на legacy значение и не меняет Plan. Loader сохраняет compatibility warning. Это демонтирует второй execution authority без потери обратной читаемости.

Frozen evidence подтверждает:

- shipping presets: 18;
- `presetPath`: 18/18;
- legacy `runtimeArgs` fields: 17;
- equivalent legacy projection -> identical Plan hash: 17/17;
- искусственный drift legacy `runtimeArgs` -> Plan hash unchanged.

## 4. runtimeContext / preset migration boundary

Новые canonical имена:

```text
profileId   -> runtimeContextId
strategyId  -> presetId
```

Сохранённый active-selection state теперь читает canonical или legacy форму. Если обе формы присутствуют и значения расходятся, loader fail-closed. Новая запись сохраняет обе формы с одинаковыми значениями на период compatibility window.

Canonical-only и legacy-only state, обозначающие один и тот же выбор, materialize одинаковый Plan hash.

## 5. Связь с P02/P03 runtime

P04b не обходит существующие PlanHash/confirmation/privilege границы. `GeneratedRuntimePlan` теперь содержит normalized execution Plan, а runtime payload сохраняет:

```text
normalizedExecutionPlan.planHash
runtimeContextId / presetId
legacy profileId / strategyId aliases
strategyRuntimeArgs = projection(normalizedExecutionPlan.runtimeArgs)
```

Session input staging, P02 artifact inventory и nft capture-port derivation берут execution argv из normalized Plan. P02 по-прежнему повторно связывает binary/input bytes перед bounded-root action.

## 6. Что остаётся P04c/P04d

P04b намеренно **не** делает:

- ActionContract handler registry authority;
- GUI/CLI canonical dispatcher;
- contradiction gate для flat legacy flags;
- 100% action coverage/generated metadata;
- полный S-INSTALL packaging.

Следующий узел после acceptance:

```text
P04c := executable ActionContract dispatcher
      + legacy CLI translator / contradiction gate
      + GUI projection
```

## Acceptance

Один read-only orchestration entrypoint:

```bash
bash meta_tools/hyperpatch_acceptance.sh --p04b
```

Он не запускает `nfqws2`, не меняет `nftables`/NFQUEUE и не требует root. PASS marker:

```text
READY_FOR_USE_WITHIN_P04B
```
