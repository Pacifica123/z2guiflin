# Порядок привилегий NFQUEUE

Stage 13 установил runtime-инвариант для Linux `nfqws2`: NFQUEUE handle/queue нужно создать **до** `droproot/dropcaps`, а hostlist/Lua validation и packet handling выполнять уже после сброса прав.

Причина была подтверждена пользовательским runtime evidence: при upstream-порядке процесс доходил до `nfq_create_queue()` после privilege drop и на части систем завершался `Operation not permitted`. Public runtime inputs решали доступ к hostlist/Lua, но не давали права на создание NFQUEUE.

## P02

Bounded root-owned executor запускает точный plan-bound `nfqws2` как root, затем передаёт `--uid=<owner>:<gid>`. Значит сам `nfqws2` всё ещё отвечает за privilege drop. P02 уменьшил root surface, но не отменил Stage-13 порядок операций внутри `nfqws2`.

## P03

Candidate `zapret2 1.0.6@00f5aaa` снова выполняет `droproot/dropcaps` раньше `nfq_init()/nfq_create_queue()`. Поэтому Stage-13 инвариант сохранён как явный `SOURCE_TRANSFORM_OVERLAY`, а не как скрытая правка vendored source.

- exact base остаётся в `core/zapret2/nfq2/nfqws.c`;
- effective build source находится в `core/overlays/zapret2/source/nfq2/nfqws.c`;
- transform описан и хеширован в `core/overlays/zapret2/OVERLAY_MANIFEST.json`;
- поддерживаемая сборка применяет его только в fresh staging tree через `tools/core_generation_build.py`.

Так upstream provenance остаётся точным, а project-local runtime behavior — видимым и проверяемым. Falsifier transform-а также зафиксирован: если на поддерживаемых owner hosts candidate upstream надёжно создаёт NFQUEUE после своего privilege drop, transform можно отдельно пересмотреть и удалить на основании нового evidence.

Stage 14 дополнительно убрал хрупкую фиксированную queue `200`: qnum вычисляется owner/workspace/profile policy и проверяется на занятость до apply.
