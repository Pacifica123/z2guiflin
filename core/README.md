# Область исходников ядра

`core/zapret2/` — byte-exact filtered snapshot `bol-van/zapret2` candidate `1.0.6@00f5aaa36de500971faf6db440dd7d8b25672281` для P03. Project-local Lua и C source transforms не должны добавляться внутрь этого дерева.

Project metadata внутри директории: `UPSTREAM_IMPORT.json`, `UPSTREAM_IMPORT.md`, `CORE_INVENTORY.json`, `BUILD_MAP.json`. Они исключены из upstream tree digest. Build artifacts также не являются частью pinned source digest и отдельно связываются build receipt.

Project-local generation bytes находятся в `core/overlays/zapret2/` и описываются `OVERLAY_MANIFEST.json`. Сборка выполняется через `python tools/core_generation_build.py`: exact upstream staging copy → verified source transforms → upstream make → atomic artifact publish. Прямой project build через `make` внутри canonical tree не используется, потому что он обошёл бы P03 source-transform contract.

Upstream license сохранена в `core/zapret2/docs/LICENSE.txt`. Подробнее: `docs/P03_ZAPRET2_GENERATION.md`.
