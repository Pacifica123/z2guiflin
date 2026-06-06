# NFQUEUE privilege order

`v0.3-beta_stage_13` вводит минимальный vendored-core patch для Linux `nfqws2` runtime.

## Почему понадобилось менять порядок

GUI sudo-askpass workflow уже выполнял сборку, создавал public runtime inputs для hostlist и Lua, применял owner-rules и запускал `nfqws2`. После этого процесс доходил до создания NFQUEUE, но завершался с ошибкой:

```text
nfq_create_queue(): Operation not permitted
```

Логи показывали, что hostlist и Lua уже доступны, а значит проблема была не в файлах, а в порядке privileged-действий. Upstream `nfqws2` сбрасывал права до вызова `nfq_create_queue()`. На некоторых системах post-drop capability set хватает для части netlink/raw-socket действий, но не хватает для создания очереди NFQUEUE.

## Что изменено

В `core/zapret2/nfq2/nfqws.c` для Linux `nfq_main()` теперь делает так:

1. если включён intercept mode, открыть NFQUEUE handle и создать queue как privileged process;
2. затем выполнить `droproot/dropcaps`;
3. затем проверить hostlist/Lua runtime inputs;
4. затем выполнить Lua init, daemon/pidfile и packet handling.

Иначе говоря, privileged operation стала ранней и явной, а дальнейшая работа всё ещё идёт после сброса прав.

## Что не меняется

- GUI по-прежнему использует graphical `sudo -A/SUDO_ASKPASS`;
- пароль не хранится в проекте;
- nftables owner-rules всё ещё применяются только через confirmed plan;
- при падении session start default workflow делает rollback owner-rules;
- hostlist и Lua init остаются public runtime copies под `/tmp/zap2-runtime-inputs/...`;
- bootstrap, service mode и upstream installer scripts не смешиваются с runtime workflow.

## Ограничение

Это vendored-core patch. При будущем обновлении `core/zapret2` из upstream его нужно будет осознанно пересмотреть и либо перенести заново, либо заменить upstream-совместимым решением.


## Дополнение Stage 14: номер очереди

Stage 13 изменил порядок открытия NFQUEUE, но пользовательский лог показал, что падение может сохраняться уже на другом уровне: fixed queue `200` слишком хрупка для частых devctl-workspace запусков. Stage 14 поэтому добавляет workspace-specific NFQUEUE policy: номер очереди больше не зашит в apply/session как глобальный `200`, а вычисляется общим resolver-ом.
