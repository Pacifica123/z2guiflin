# Версионирование

## Текущая версия

```text
v0.7
Python package: 0.7.0
Development line: P04a evidence/ontology foundation toward v0.8
```

`v0.7` — последняя принятая продуктовая версия. P03f owner-host acceptance подтвердил runnable generation/build/parser/privilege/runtime lifecycle для pinned zapret2 `1.0.6@00f5aaa` и завершился `READY_FOR_USE_WITHIN_P03`. Текущий HEAD начинает P04a; `v0.8` не присваивается до завершения всего P04/RC4. Универсальная сетевая стратегия по-прежнему не является обещанием версии.

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

### P04a -> v0.8 candidate

P04a синхронизирует post-P03f baseline, фиксирует ontology/ActionContract foundation и замораживает REP/CLI/S-INSTALL decision evidence. Это ещё не `v0.8`: единый Plan materializer, dispatcher/legacy translator и 100% contract coverage относятся к следующим bounded P04 hyperpatches.

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
