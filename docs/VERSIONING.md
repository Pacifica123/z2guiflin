# Версионирование

## Текущая версия

```text
v0.7 accepted baseline / v0.8 RC4 candidate
Python package: 0.8.0rc4
Development line: P04d/RC4 ActionContract closure toward v0.8
```

`v0.7` — последняя принятая продуктовая версия. P03f owner-host acceptance подтвердил runnable generation/build/parser/privilege/runtime lifecycle для pinned zapret2 `1.0.6@00f5aaa` и завершился `READY_FOR_USE_WITHIN_P03`. P04a, P04b и P04c приняты (`READY_FOR_USE_WITHIN_P04A/B/C`); текущий HEAD реализует P04d и поэтому использует prerelease package version `0.8.0rc4`. Финальный `v0.8` не считается принятой версией до owner acceptance P04d/RC4. Универсальная сетевая стратегия по-прежнему не является обещанием версии.

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

### P04a/P04b/P04c/P04d -> v0.8 candidate

P04a синхронизировал post-P03f baseline и зафиксировал ontology/REP/CLI/S-INSTALL evidence. P04b добавил explicit resource-root contract и location-independent immutable execution Plan. P04c ввёл canonical `--action`, bounded executable dispatcher и global contradiction gate. P04d закрывает 117/117 legacy selector destinations, 119/119 ActionContract handlers, generated metadata/projection и roundtrip/lint acceptance. До owner acceptance это RC4 candidate (`0.8.0rc4`), а не принятый финальный `v0.8`.

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
