# P03 — поколение zapret2 1.0.6

P03 переводит проект с legacy-снимка примерно `0.9.5.3` (точный старый upstream commit исторически не восстановлен) на точно зафиксированный candidate `bol-van/zapret2`:

- commit: `00f5aaa36de500971faf6db440dd7d8b25672281`;
- version: `1.0.6`;
- source archive SHA-256: `769df14fa4463fbe9744a2aab97e7f1bfe1a2f77a669981f4e6372d7b86d71a9`;
- filtered upstream files: `244`;
- filtered tree SHA-256: `fd472f723743909d3f4b281ed8be3a8f9327f5bb091be677bc5f9e5f174e7d22`;
- Lua compatibility: `6/6`.

## Что считается одним поколением

Runtime принимает только целую связку `pinned upstream source + upstream Lua + project overlays/source transforms + shipping preset compatibility receipt + compiled binary`.

`gui/zap2_gui/adapters/core_generation.py` вычисляет identity этой связки, а `core_provenance.py` связывает её с build receipt. Отсутствующий, старый или несовпадающий receipt делает поколение неготовым к запуску. Default-start выполняет этот preflight до применения nft owner-rules, поэтому `MIXED_GENERATION` блокируется до firewall mutation.

## Upstream и project-local код разделены

`core/zapret2/` остаётся byte-exact filtered upstream tree. Project-local части вынесены в `core/overlays/zapret2/` и описаны `OVERLAY_MANIFEST.json`.

Первый overlay — `lua/custom_funcs.lua`. Он сохраняет `hostfakesplit_multi`, используемый shipping community presets, и классифицирован как `LOCAL_OVERLAY`. В candidate upstream есть базовый `hostfakesplit`, но нет `hostfakesplit_multi` с требуемой совместимостью вызова.

Второй overlay — source transform `nfqueue-open-before-droproot-v1`. Candidate 1.0.6 в Linux `nfq_main()` выполняет `droproot/dropcaps` до `nfq_init()/nfq_create_queue()`. Это противоречит подтверждённому Stage-13 runtime contract: на части систем создание NFQUEUE после privilege drop возвращало `EPERM`. P02 bounded executor запускает дочерний `nfqws2` как root и передаёт `--uid=<owner>`, поэтому данный порядок остаётся релевантным.

Transform хранит полную effective-версию `nfq2/nfqws.c` вне upstream tree и связывает base source SHA-256 `0d26c5321292e617d710ff3a9eb01ad0b0b869618790a8e7a687816b813081f2` с effective source SHA-256 `08d01e374c46584908b12872be029da4f2d7de93e41926abfd19b88f2953367b`.

Он переносит создание/bind NFQUEUE до privilege drop, но hostlist/Lua validation и packet handling остаются после сброса прав.

## Сборка без изменения pinned tree

Прямой `make` в `core/zapret2` больше не является поддерживаемым project build path. `local_build.py` формирует команду через `python tools/core_generation_build.py`.

Build adapter проверяет P03 generation identity, создаёт fresh staging copy exact upstream, проверяет base/effective hashes source transforms, накладывает transforms только в staging tree, запускает upstream `make` там и только после успешной сборки атомарно публикует ожидаемые binaries обратно в canonical output paths.

Неудачная сборка не переписывает pinned C source и не публикует частично готовый artifact. Build receipt дополнительно фиксирует generation hashes, transform digest, adapter hash, toolchain/flags и binary hash.

## Shipping corpus

`runtime/preset-compatibility-receipt.json` классифицирует все 18/18 shipping strategies: 9 `equivalent`, 9 `equivalent-local-overlay-relocation`, ноль `changed-transformable`, `changed-unsupported` и `unknown`.

`send:delay` и переименование `WRITEABLE→WRITABLE` текущим shipping corpus не используются. `hostfakesplit_multi` фактически вызывается восемью shipping strategies; девять strategy variants загружают compatibility overlay.

Статическая классификация не заменяет native parser/runtime evidence. После clean build на owner/UTS host нужно повторить `nfqws2 --dry-run` и L3 canary, особенно NFQUEUE privilege-order сценарий.

Для Linux parser-preflight служебный `--qnum` добавляет project runtime-обвязка, а не shipping strategy. В zapret2 1.0.6 `--dry-run` при включённом interception всё равно требует номер очереди, хотя до `nfq_main()` и создания NFQUEUE не доходит. Поэтому `--strategy-parser-preflight` использует тот же owner/workspace queue selection, что и реальный runtime, и остаётся read-only.

## Детерминированная проверка P03

Без сборки, sudo, nft или сети:

```bash
PYTHONPATH=gui python tools/gui_checks/check_p03_core_generation.py
python tools/gui_checks/inventory_core.py --check
```

Checker подтверждает exact candidate identity, overlay/transform hashes, 100% corpus classification, Lua compat и то, что supported build path не обходит staged generation adapter.

## Граница rollback

Поколение откатывается только целиком. Неделимая единица P03: `upstream receipt + overlays/source transforms + LuaCompat + build receipt + binary + shipping manifest + preset compatibility receipt`. Частичная комбинация поколений не является rollback и должна завершаться `MIXED_GENERATION` до nft mutation.

P03 не вводит отдельный updater, хранящий старый upstream внутри рабочего дерева. Поэтому clean whole-generation rollback — это возврат к принятому post-P02 project snapshot целиком и использование его собственного build/runtime evidence. Неудачная пересборка внутри P03 безопаснее: staged build не публикует новый artifact до успешного `make`, поэтому предыдущий canonical binary не заменяется частично.
