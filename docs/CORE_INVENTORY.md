# Инвентаризация ядра — P03

Машиночитаемый снимок `core/zapret2/CORE_INVENTORY.json` описывает только filtered upstream tree P03. Он генерируется `tools/gui_checks/inventory_core.py` и не запускает upstream-код.

Сейчас в pinned upstream tree зафиксировано **244 файла**; `upstreamImportedFileCount = 244`, `projectLocalCoreFileCount = 0`. Служебные `UPSTREAM_IMPORT.json`, `UPSTREAM_IMPORT.md`, `CORE_INVENTORY.json`, `BUILD_MAP.json` и build artifacts в это число не входят.

Project-local runtime Lua и source transforms больше не лежат внутри upstream tree. Они находятся в `core/overlays/zapret2/` и входят в P03 generation receipt отдельно. `custom_funcs.lua` классифицирован как `LOCAL_OVERLAY`, а сохранение Stage-13 порядка NFQUEUE — как `SOURCE_TRANSFORM_OVERLAY`.

Ключевые build units остаются `nfqws2`, `ip2net`, `mdig`. Их Makefile описаны в `BUILD_MAP.json`, но поддерживаемый build path P03 использует `tools/core_generation_build.py`: exact upstream копируется в staging tree, verified source transforms применяются там, а готовые artifacts публикуются атомарно. Автоматические inventory checks не запускают `make`, sudo, installer scripts, firewall или сеть.

После осознанного изменения upstream snapshot metadata обновляется так:

```bash
python tools/gui_checks/inventory_core.py --write
python tools/gui_checks/inventory_core.py --check
```

Подробная provenance/compatibility модель описана в `docs/P03_ZAPRET2_GENERATION.md`.
