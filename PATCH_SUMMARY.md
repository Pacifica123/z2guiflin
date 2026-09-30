# Итог release/handoff patch — v0.8 promotion + P05 preparation

База: owner-accepted P04d/RC4 (`READY_FOR_USE_WITHIN_P04D`), post-P04d lineage `2fc0a34`. Этот patch не добавляет новый P04 engineering scope: он выполняет обязательный post-acceptance re-forensics, доказывает product transition, снимает prerelease `0.8.0rc4` в пользу `0.8.0` и компилирует следующий provisional DAG.

## Результат

- P04 считается закрытым;
- final product metadata: `v0.8` / `0.8.0`;
- owner acceptance записан отдельным provenance receipt без притворной переносимости host-local evidence;
- P04 frozen evidence остаётся неизменяемой историей;
- P05 подготовлен как projection-only discoverability/help/error/health UX поверх P04 ActionContracts + P01 typed evidence + P02 state;
- S-INSTALL package-data/writable-state separation остаётся productization/P06 scope;
- добавлен единый read-only acceptance `hyperpatch_acceptance.sh --v08-release`.

## Acceptance

Успешный marker этого patch:

```text
HYPERPATCH ACCEPTANCE: PASS
readiness: READY_FOR_P05
```

После него следующий mutation cycle обязан начать P05 с нового re-forensics принятого v0.8 HEAD, а не исполнять старый roadmap текст как authority.
