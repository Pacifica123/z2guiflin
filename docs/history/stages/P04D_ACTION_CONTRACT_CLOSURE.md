# P04d — ActionContract closure / RC4

База: owner-accepted P04c (`READY_FOR_USE_WITHIN_P04C`). Последняя принятая продуктовая версия остаётся `v0.7`; этот HEAD маркируется как **`0.8.0rc4` candidate**, пока владелец не выполнит `hyperpatch_acceptance.sh --p04d`.

## Цель

P04d закрывает последний structural debt P04: legacy flat CLI больше не имеет собственных action authorities. Каждый исторический top-level selector переводится в canonical `ActionContract` до исполнения.

```text
argv
→ argparse
→ global contradiction gate
→ ActionContract
→ canonical dispatcher
→ handler
→ P04b ImmutableExecutionPlan/runtime authority (где применимо)
```

## Coverage

- historical selector destinations: **117**;
- contract-backed selector destinations: **117/117**;
- remaining legacy-only selectors: **0**;
- canonical ActionContracts: **119** (один `runtime_plan` selector проецируется на start/stop/status);
- executable dispatcher handlers: **119**.

`main()` больше не содержит first-match action branches. Проверенные старые command bodies сохранены внутри selector-scoped `dispatch_legacy_compat()`: туда можно попасть только после выбора ActionContract, и функция дополнительно требует ровно один ожидаемый selector. Поэтому порядок исторических `if` больше не определяет action.

## Canonical operands

Legacy selectors, которые исторически принимали значение (`--show-preset ID`, `--har-analyze FILE`, `--service-plan ACTION`), имеют canonical форму через повторяемый operand:

```bash
./run.sh --cli --action preset.show --operand manual-local
./run.sh --cli --action preset.traffic-profile.show --operand manual-local --operand PROFILE_ID
```

Operand arity и legacy choices зафиксированы в generated compatibility metadata. Неверная arity/choice завершается fail-closed до command body.

## Generated metadata и projections

`meta_tools/generate_p04d_action_bindings.py` детерминированно строит frozen compatibility metadata из parser surface. Acceptance требует byte-for-byte совпадения с `models/action_bindings_generated.py`.

`action_projection_rows()` генерируется только из `ActionContract` catalog и является общим metadata projection для CLI/help/GUI tooling. Отдельный второй registry с label/help не вводится. Текущие Default workflow tooltips по-прежнему читают те же contracts напрямую.

## Что проверяет P04d acceptance

- 117/117 selectors contract-backed;
- zero legacy-only selectors;
- zero legacy action branches в `main()`;
- compatibility body содержит frozen 117-selector implementation inventory;
- 119 contracts ↔ 119 executable handlers;
- generated metadata воспроизводимо;
- parser roundtrip для всех 119 canonical actions;
- representative canonical/legacy execution parity;
- contradiction gate до handler;
- generated projection совпадает с catalog;
- P03 generation identity сохранена;
- полный pytest corpus проходит в четырёх isolated workers без мутации live checkout.

Команда:

```bash
bash meta_tools/hyperpatch_acceptance.sh --p04d
```

PASS marker:

```text
READY_FOR_USE_WITHIN_P04D
```

## Что P04d не утверждает

P04d не доказывает универсальную работоспособность обхода DPI и не повторяет network/root canary P03. Также остаются отдельными задачами полный S-INSTALL package-data bundle и separation writable `.zap2` state от immutable resources. P05 может строить search/help/capability UX уже поверх стабильного ActionContract projection.


Acceptance evidence нормализует абсолютный checkout root и environment-resolved Python executable перед хэшированием representative stdout/stderr; сам legacy/canonical output сравнивается до нормализации. Это сохраняет relocation-invariant P04b и не скрывает semantic drift.
