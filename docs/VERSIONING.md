# Версионирование

## Текущая версия

```text
v0.6
Python package: 0.6.0
Development line: P03 candidate toward v0.7
```

`v0.6` — последняя принятая продуктовая версия: P01 закрепил typed network truth/evidence, P02 — owned lifecycle и bounded privilege boundary. Текущий HEAD содержит P03-кандидат перехода `0.6 -> 0.7`; финальный bump до `v0.7` разрешён только после owner-host acceptance P03. Универсальная сетeвая стратегия по-прежнему не является обещанием версии.

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

### P03 candidate -> v0.7

Pinned zapret2 `1.0.6@00f5aaa`, LuaCompat 6, explicit overlays/source transform и whole-generation receipt уже реализованы. Версия `v0.7` не считается присвоенной, пока `hyperpatch_acceptance.sh --p03` не завершится `READY_FOR_USE_WITHIN_P03` на owner-host.

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
