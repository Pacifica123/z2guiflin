# Итог hyperpatch — P04d ActionContract closure / RC4 candidate

База: owner-accepted P04c (`READY_FOR_USE_WITHIN_P04C`), post-P04c lineage `43fda92`. Последняя принятая версия остаётся `v0.7`; patch маркирует prerelease package `0.8.0rc4` до owner acceptance.

## Что делает P04d

- переводит все 117 historical top-level selector destinations в canonical ActionContracts;
- закрывает catalog/dispatcher как 119 ActionContracts / 119 executable handlers;
- удаляет first-match action authority из `main()`;
- сохраняет зрелые legacy command bodies только как selector-scoped compatibility executor после contract selection;
- добавляет repeatable canonical `--operand` для действий с selector value;
- генерирует/freeze compatibility metadata из parser surface и проверяет byte-for-byte regeneration;
- генерирует единый ActionContract projection для CLI/help/GUI tooling;
- добавляет all-contract parse/materialization roundtrip и representative execution parity;
- добавляет P04d frozen evidence и `hyperpatch_acceptance.sh --p04d`;
- синхронизирует product metadata как RC4 candidate (`0.8.0rc4`), не объявляя final v0.8 до owner PASS.

## Acceptance target

`HYPERPATCH ACCEPTANCE: PASS` + `READY_FOR_USE_WITHIN_P04D`. После этого P04 architecture считается закрытой и RC4 eligible for v0.8 promotion; P05 может строиться поверх стабильного ActionContract projection.

## Не входит

- универсальная гарантия обхода DPI;
- повтор network/root canary P03;
- полный S-INSTALL package-data bundle / writable-state separation;
- P05 search/help UX.
