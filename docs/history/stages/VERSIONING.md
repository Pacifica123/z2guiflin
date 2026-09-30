# Версионирование

Текущее состояние P05: **0.9.0rc5 / v0.9 RC5 candidate**. Реализованы global discovery/help, structured error envelopes и separate health projections. Последний принятый релиз остаётся v0.8; принятие RC5 на owner-host ещё не выполнено. Общая проверка: `bash meta_tools/hyperpatch_acceptance.sh --p05`. После acceptance: re-forensics → решение о final 0.9.0 → P06 → P07. Детали: `docs/P05_DISCOVERABILITY.md`.

Ниже сохранён контекст принятого v0.8 и предыдущих этапов.

## Текущая версия

```text
v0.8 accepted
Python package: 0.8.0
Development line: P05 discoverability/help/unified health UX preparation
```

`v0.8` — последняя принятая продуктовая версия. P04a–P04d завершили переход от раздвоенной representation/first-match CLI semantics к location-independent immutable Plan и полному executable ActionContract authority; owner-host P04d acceptance завершился `READY_FOR_USE_WITHIN_P04D`. Универсальная сетевая стратегия по-прежнему не является обещанием версии. P05 является следующим provisional roadmap node, а не заранее присвоенной версией.

## Формат

Используется схема:

```text
MAJOR.MINOR.PATCH
```

- `MAJOR` — несовместимая смена архитектуры или формата данных.
- `MINOR` — новая законченная продуктовая возможность.
- `PATCH` — исправление без смены основной модели.

Суффиксы `alpha`, `beta` и `rc` применяются только к реально незавершённому будущему релизу. Внутренние stage ID не должны заменять версию продукта.

## История

### v0.3-stable

Первая доказанная цепочка:

```text
Blockcheck -> AVAILABLE -> generated strategy -> selection -> Default workflow -> рабочий YouTube
```

### v0.4

Добавлены и сведены в единый продукт:

- service-aware Blockcheck и проверка покрытия;
- Discord endpoint/DNS/pre-TLS наблюдения;
- матрица стратегий;
- универсальный HAR workbench;
- расширенная модель пресетов и профилей;
- owner-confirmed runtime с `nftables`/NFQUEUE;
- экспериментальная SOCKS5/VLESS ветка;
- launch composer;
- обновлённый GUI shell и темы.

Релиз принят без требования универсального пресета. Подробности: `V04_RELEASE.md`.


### v0.5

Принят P01: network truth / VLESS / Vesktop переведены от scalar readiness к typed EvidenceGraph/CapabilityVerdict.

### v0.6

Принят P02: lifecycle/state ownership и привилегии сведены к bounded root-owned executor, immutable PlanHash/confirmation и fail-closed reconciliation.

### v0.7

Принят P03/P03f: pinned zapret2 `1.0.6@00f5aaa`, LuaCompat 6, explicit overlays/source transform, whole-generation receipt и bounded drop-identity recovery. Owner-host `hyperpatch_acceptance.sh --p03` завершён с `READY_FOR_USE_WITHIN_P03`.

### v0.8 — P04 ActionContract/Plan normalization

P04a синхронизировал post-P03f baseline и зафиксировал ontology/REP/CLI/S-INSTALL evidence. P04b добавил explicit resource-root contract и location-independent immutable execution Plan. P04c ввёл canonical `--action`, bounded executable dispatcher и global contradiction gate. P04d закрыл 117/117 legacy selector destinations, 119/119 ActionContract handlers, generated metadata/projection и roundtrip/lint acceptance. После owner-host `READY_FOR_USE_WITHIN_P04D` и post-acceptance re-forensics transition принят как `v0.8` / `0.8.0`.

## Исторические stage ID

Строки вида:

```text
v0.4-alpha_stage7o2d
v0.4-alpha_stage7p5
v0.4-alpha_stage8f-r3
```

остаются идентификаторами конкретных реализаций и форматов отчётов. Их не нужно массово менять в сохранённых схемах, fixture и runtime reports, пока не вводится отдельная миграция.

## Правило будущих релизов

Релиз определяется возможностями приложения, которые проект способен контролировать и проверить.

Нельзя блокировать релиз только потому, что:

- стратегия перестала работать после изменения DPI;
- другой провайдер даёт иной результат;
- комбинация профилей оказалась несовместимой;
- внешний tunnel upstream недоступен.

Вместо этого должны быть проверяемые диагностика, лог, статус и честно описанная граница.
