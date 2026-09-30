# Итог hyperpatch — P04a re-forensics / version sync / ontology foundation

База: owner-accepted post-P03f HEAD (`17b2b8b` archive lineage), acceptance marker `READY_FOR_USE_WITHIN_P03`.

## Почему P04 разбит

Повторная форензика показала scope overflow исходного P04. Вместо одной большой переписи зафиксирован bounded DAG P04a→P04b→P04c→P04d. Это сохраняет RA-инвариант: новый HEAD сначала меняет assumptions/evidence, затем перекомпилирует оставшуюся работу.

## Что делает P04a

- повышает принятую продуктовую baseline `v0.6 -> v0.7` после завершённого P03f owner-host acceptance;
- переводит development line на `P04a ... toward v0.8`, не присваивая `v0.8` преждевременно;
- добавляет canonical domain ontology и тип `ActionContract` с validation invariants;
- добавляет compatibility-only aliases `runtime_context_id` / `preset_id`, не выполняя destructive storage migration;
- замораживает decision evidence в `runtime/p04/p04a-frozen-evidence.json`;
- добавляет deterministic checker `tools/gui_checks/check_p04a_re_forensics.py`;
- фиксирует REP experiment: shipping preset execution roundtrip должен оставаться exact, а `presetPath + runtimeArgs` признаются временной duplicate execution representation;
- фиксирует CLI experiment: representative contradictory selectors принимаются legacy argparse и требуют pre-handler conflict gate;
- фиксирует S-INSTALL: repository-relative resource discovery пока не поддерживает outside-checkout contract и переносится в dependency P04b, а не откладывается молча до P06;
- расширяет `meta_tools/hyperpatch_acceptance.sh` режимом `--p04a`, который выполняет весь read-only acceptance одним orchestration command и упаковывает evidence.

## Что P04a намеренно НЕ делает

- не выбирает TXT/JSON/новый IR как canonical authoring source без fidelity evidence;
- не переписывает 163-option legacy CLI сразу;
- не объявляет ActionContract registry authority, пока handlers не мигрированы;
- не меняет nftables/NFQUEUE/runtime execution semantics;
- не доказывает censorship-resistance конкретной стратегии.

## Следующий DAG

`P04b(resource location + immutable Plan materializer) -> P04c(ActionContract dispatcher + CLI translator/conflict gate) -> P04d(coverage/migration/lint) -> RC4/v0.8 candidate -> P05`.
