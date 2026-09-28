# Итог патча — P03 zapret2 semantic generation migration

База: принятый post-P02 snapshot, HEAD `f7d9125`.
План: `P03_UPSTREAM_ZAPRET2_MIGRATION.md` из planning-архива. Перед merge выполнена повторная форензика текущего P02 HEAD; старые предположения не переносились автоматически.

## Зафиксированное поколение upstream

- Candidate: `bol-van/zapret2` commit `00f5aaa36de500971faf6db440dd7d8b25672281`, version `1.0.6`, `LUA_COMPAT_VER=6`.
- Присланный candidate archive SHA-256: `769df14fa4463fbe9744a2aab97e7f1bfe1a2f77a669981f4e6372d7b86d71a9`.
- Candidate archive: 253 файла; deterministic filter исключает 9 GitHub CI / prebuilt Windows artifacts; canonical filtered upstream: 244 файла.
- Filtered candidate tree SHA-256: `fd472f723743909d3f4b281ed8be3a8f9327f5bb091be677bc5f9e5f174e7d22`.
- Legacy filtered tree SHA-256: `39ffba3acc527e47f87030b1068fd14550b8101cc0e08ee3a203a505a21daeb6`; содержимое соответствует примерно `0.9.5.3`/Lua compat 5. Точный старый upstream commit не выдумывается и остаётся `historically_unrecoverable`.
- После применения filter-policy path inventory совпадает 244↔244: 201 byte-identical и 43 changed files.

## Что реализовано

- `core/zapret2/` заменён на byte-exact filtered candidate. Project metadata не считается upstream payload и проверяется отдельно.
- Project-local Lua вынесен из upstream tree в `core/overlays/zapret2/lua/custom_funcs.lua`; `hostfakesplit_multi` классифицирован как `LOCAL_OVERLAY`.
- Shipping strategy references переведены на новый overlay path. Исторические raw/imported Windows TXT источники не переписывались как будто это новый canonical corpus.
- Добавлен `core/overlays/zapret2/OVERLAY_MANIFEST.json`, связывающий exact upstream commit/version, Lua overlay и source transforms.
- Во время re-forensics обнаружен неочевидный P03 blocker: exact candidate снова делает `droproot/dropcaps` до `nfq_init()/nfq_create_queue()`, тогда как принятый Stage-13 контракт открывал NFQUEUE до privilege drop. P02 bounded executor этот контракт не отменяет.
- Чтобы не загрязнять pinned upstream, Stage-13 изменение оформлено как `SOURCE_TRANSFORM_OVERLAY` `nfqueue-open-before-droproot-v1`. Canonical `core/zapret2/nfq2/nfqws.c` остаётся exact candidate; effective source лежит вне upstream tree и имеет отдельный base/effective SHA-256.
- Добавлен `tools/core_generation_build.py`: fresh staging copy exact candidate → проверка base hashes → применение зарегистрированных transforms только в staging → upstream `make` → атомарная публикация ожидаемых binaries только после successful build. Поддерживаемый запуск идёт через текущий Python-интерпретатор (`python tools/core_generation_build.py ...` / `sys.executable`), поэтому devctl-патч не зависит от сохранения executable-bit в ZIP. Неуспешная сборка не меняет canonical C source и не публикует частичный artifact.
- `local_build.py` и default build workflow используют staged generation adapter вместо прямого `make` в `core/zapret2`.
- Добавлен immutable `runtime/shipping-strategy-manifest.json`. Generation identity связывает только 18 встроенных shipping strategies; пользовательские/imported workspace presets не могут ошибочно превратить core generation в `MIXED_GENERATION`.
- Добавлен `runtime/preset-compatibility-receipt.json` с 100% классификацией shipping corpus и targeted migration fixtures.
- `core_generation.py` вычисляет exact generation identity: upstream tree + Lua compat + overlay/source-transform bytes + immutable shipping corpus + compatibility receipt.
- `core_provenance.py` переведён на generation build receipt schema 2. Receipt связывает source/Lua/generation/transform/build-adapter/toolchain/flags/binary hashes.
- Missing/legacy/tampered build receipt или несовпадение любого поколения даёт fail-closed `MIXED_GENERATION`/not-runtime-ready.
- Default-start выполняет generation/provenance preflight до owner-rules apply; negative test подтверждает, что при generation mismatch `nft -f` не вызывается.
- `meta_tools/uts_prepare.sh --p03` запускает generation, staged-build, inventory/default-build/default-workflow/security regression.

## Semantic corpus evidence

Все 18/18 shipping strategies классифицированы:

- 9 — `equivalent`;
- 9 — `equivalent-local-overlay-relocation`;
- 0 — `changed-transformable`;
- 0 — `changed-unsupported`;
- 0 — `unknown`.

Нормализованная old/new semantic representation совпадает. Candidate raw shipping corpus SHA-256: `a90c879e4076cacab7d9087bda9985b4e895a4b4990cbd973c79a93ea0b62b2a`; legacy raw corpus SHA-256: `6664dadee380d6ccac2da764f25980bbb3b28a684905988aa03335e543ffa3e5`.

Из materially changed Lua/options:

- `send:delay` shipping corpus не использует;
- `WRITEABLE→WRITABLE` shipping corpus не использует;
- `hostfakesplit_multi` загружается через compatibility overlay в 9 variants и фактически вызывается 8 shipping strategies;
- NFQUEUE privilege-order имеет falsifiable before/after fixture: canonical candidate доказывает `droproot < nfq_init`, effective transformed source — `nfq_init < droproot`.

## Проверки, выполненные до упаковки

- `tools/gui_checks/check_project_tree.py`: PASS.
- `tools/gui_checks/inventory_core.py --check`: PASS.
- `tools/gui_checks/check_p03_core_generation.py`: PASS — candidate `1.0.6@00f5aaa`, 244 files, 18/18 shipping classification, overlay/source-transform/build-path contracts.
- `tools/gui_checks/check_default_build_workflow.py`: PASS.
- Focused P03/default/security regression: PASS.
- Staged build adapter regression: PASS. Fake successful build доказывает transform only-in-staging + atomic publish; forced build failure оставляет canonical candidate source и предыдущий binary неизменными.
- Полный repository regression после финальных P03 изменений: 82 test-файла, `485 tests collected`; все тесты пройдены в трёх непересекающихся группах с exit code `0`.
- Negative generation fixtures проверяют как минимум missing receipt, tampered Lua overlay, tampered source transform, tampered compatibility receipt и tampered binary.

## Native owner/UTS gate — не повышен до PASS

В текущей patch-среде реальная clean native сборка `nfqws2`, candidate parser dry-run и L3 NFQUEUE canary не выполнялись: dependency preflight честно сообщает отсутствие development headers для `libnetfilter_queue`, `libnfnetlink`, `libmnl` и Lua. `make`, C compiler, `pkg-config` и zlib доступны.

Это означает: deterministic/static/staged P03 implementation готова, но финальный P03 RC/owner acceptance требует на целевой Arch/EndeavourOS машине установить build deps, выполнить clean staged build, записать generation build receipt, повторить native corpus/parser dry-run и L3 canary для NFQUEUE privilege-order. До этого данный post-архив следует считать P03 candidate, а не owner-accepted RC.

## Rollback boundary

Rollback unit P03 неделим: `{upstreamReceipt, overlays/sourceTransforms, LuaCompat, buildReceipt, binary, shippingManifest, presetCompatibilityReceipt}`. Runtime не поддерживает частичное переключение этих частей: любое смешение блокируется как `MIXED_GENERATION` до nft mutation.

P03 не добавляет сетевой updater и не притворяется, что может восстановить старое поколение без его bytes. Whole-generation rollback выполняется заменой project snapshot на уже принятый post-P02 snapshot целиком. Build-level rollback безопасен отдельно: failed staged build не публикует новый binary и сохраняет предыдущий canonical artifact. После snapshot rollback требуется использовать build receipt того поколения; перенос P03 receipt/binary/overlay в P02 snapshot является запрещённой partial combination.
