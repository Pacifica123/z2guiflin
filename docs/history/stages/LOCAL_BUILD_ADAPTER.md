# Адаптер локальной сборки

P03 сохраняет typed `LocalBuildPlan`, но меняет execution path: canonical `core/zapret2` должен оставаться exact pinned upstream, поэтому поддерживаемая сборка идёт через `python tools/core_generation_build.py`.

Для target `nfqws2` план запускает:

```bash
python tools/core_generation_build.py nfqws2
```

Аналогично доступны `all`, `ip2net`, `mdig`, `clean`. Команда запускается без sudo и не меняет firewall/services.

Build adapter сначала проверяет whole-generation identity, затем создаёт fresh staging copy upstream tree, накладывает зарегистрированные `SOURCE_TRANSFORM_OVERLAY` из `core/overlays/zapret2/`, запускает upstream `make` в staging tree и только после успеха атомарно копирует ожидаемые artifacts в `core/zapret2/...`. Failed build не изменяет pinned C source и не должен публиковать частично построенный binary.

GUI/CLI по-прежнему показывают typed plan до исполнения. Default build требует owner confirmation. Build dependency preflight остаётся отдельным и сообщает отсутствующие compiler/dev libraries.

Read-only plan:

```bash
PYTHONPATH=gui python -m zap2_gui.app --build-plan --build-target nfqws2
```

Детерминированные tests могут проверять plan и transform identity, но native compilation остаётся owner/UTS action. Подробнее: `docs/P03_ZAPRET2_GENERATION.md`.
