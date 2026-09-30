# P05 — initial re-forensics / discoverability-help-health UX

Статус текущего кандидата: **P05 реализован, RC5 ожидает owner acceptance**.

Исторический PRE после accepted v0.8: **implementation ещё не начата**. Измерения ниже относятся к этой исходной базе.

## Thesis

```text
product breadth
→ tested global action/concept discovery
+ compact contextual help
+ structured evidence errors
+ health projections
WITHOUT new semantic authority
```

P05 строится поверх уже принятых P04 `ActionContract`, P01 `EvidenceGraph/CapabilityVerdict` и P02 runtime resource state. Search/help/health являются проекциями этих контрактов и evidence, а не новым источником истины.

## Текущие измерения HEAD

Release evidence фиксирует текущую стартовую точку:

- 119 ActionContracts;
- 117/117 historical selectors contract-backed;
- keywords присутствуют у 119/119 contracts;
- concept links присутствуют только у части contracts;
- `deep_help` пока отсутствует;
- location/focus target покрытие минимально;
- отдельного global action/concept search index нет;
- page-local preset search уже существует и должен остаться отдельным локальным поиском;
- typed network evidence и runtime `next_safe_action` уже существуют и должны использоваться health projection без scalar promotion.

Это не список дефектов P04. Это frozen вход P05.

## Provisional execution shape

```text
ActionContract + concept metadata
→ deterministic projection index
→ normalized RU/EN/technical query
→ deterministic ranking + bounded typo fuzzy
→ focus resolver
→ invoke policy
→ compact/deep help
→ structured error envelope
→ runtime/network/app health projection
→ GUI/CLI projections
```

Каждый этап обязан быть derivation/projection. Если возникает manual registry, parallel privilege policy или отдельная truth model, P05 должен остановиться и пересобрать дизайн.

## Initial acceptance targets

- seeded RU/EN/technical queries находят ожидаемые action/concept IDs;
- bounded typo fuzzy не делает ranking недетерминированным;
- каждый advertised focus target разрешается;
- unsafe direct invoke mutating/privileged actions блокируется;
- non-obvious visible actions имеют help coverage;
- error fixtures покрывают как минимум nft conflict, stale PID, missing core, SOCKS/TLS EOF, unsupported transport и migration;
- health сохраняет stale/missing mandatory predicate как UNKNOWN/FAIL, а не green;
- VLESS symptom способен показать local success + TLS fail/unknown одновременно;
- page-local preset search остаётся distinct;
- search/help metadata не образуют третью semantic source.

## Manual novice journeys

P05 должен позволить пользователю без чтения stage-документов найти путь к ответу на вопросы типа:

- «как безопасно запустить?»;
- «где VLESS?»;
- «почему Discord не работает?»;
- «как откатить firewall?»;
- «что такое NFQUEUE и где посмотреть его состояние?».

## Scope discipline

P05 остаётся provisional roadmap node. Перед первым mutation patch обязателен новый PRE на принятом `v0.8` HEAD. Если global search, help/errors и health projection не помещаются в один coherent/reviewable transition, P05 нужно разделить на bounded hyperpatches; номера подэтапов не являются заранее обязательными.

## POST кандидата RC5

WITHOUT new semantic authority сохраняется: catalog/dispatcher/CLI authority не меняются; index/help являются вычисляемыми views. Все 119 действий имеют поиск и help; CLI-only action фокусируется на точной справке инспектора, а раздел служит маршрутом к существующему workflow. Настройки берутся из metadata рядом с реальными controls. Concepts связаны с canonical ontology.

Подтверждено: P01 mandatory capability predicates переиспользуются; P02 ownership и next_safe_action отображаются отдельно. Falsified: ни один исходный prerequisite не опровергнут. Новое ограничение: cached snapshot требует явного refresh; поиск не запускает probe/prepare/mutation. Исторические v0.8/P04 receipts не переписаны. Frozen PRE: `runtime/p05/pre-forensics.json`.

DAG: RC5 owner acceptance → new HEAD re-forensics → final SemVer decision → P06 productization → P07 qualification. Полный package-data/S-INSTALL и внешние network results остаются за границами P05.
