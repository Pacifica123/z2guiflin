# GUI toggle и runtime logs

`v0.3-beta_stage_7` переводит default workflow из набора отдельных GUI-кнопок в
основной режим одной кнопки `Включить Default` / `Выключить Default`.

## Что делает toggle

Если Default выключен, GUI выполняет стандартную цепочку владельца:

1. при отсутствии `nfqws2` проверяет build dependencies;
2. создаёт build-plan;
3. подтверждает build-plan;
4. запускает локальную сборку без `sudo`;
5. создаёт start-plan;
6. подтверждает start-plan;
7. вызывает `pkexec`/polkit для privileged start.

Если Default включён, GUI выполняет обратную цепочку:

1. создаёт stop-plan;
2. подтверждает stop-plan;
3. вызывает `pkexec`/polkit для privileged stop.

Приложение не принимает и не хранит пароль. Пароль или подтверждение показывает
системный графический polkit authentication agent.

## Почему start через GUI сохраняет root identity

Для `nfqws2` на Linux нужен `CAP_NET_ADMIN` при создании NFQUEUE. Терминальный
`sudo`-путь и GUI/pkexec-путь отличаются окружением: `pkexec` не передаёт
`SUDO_UID/SUDO_GID`. Поэтому GUI/pkexec start передаёт во внутренний runner:

```text
ZAP2_RUNTIME_DROP_IDENTITY=polkit-root
```

Это заставляет session runner передать `nfqws2` явный `--uid=0:0`, чтобы
процесс не терял `CAP_NET_ADMIN` до `nfq_create_queue()`. Это применяется только
к privileged GUI start. Stop и неприцивилегированные действия этот режим не
используют.

## Логи

Вкладка `Логи` читает `.zap2/runtime` и показывает:

- последние JSONL runtime events;
- tail `default.nfqws2.stderr.log`;
- tail `default.nfqws2.stdout.log`;
- tail debug-log, если он был явно включён через `ZAP2_RUNTIME_DEBUG=1`.

Вкладка логов read-only: она не запускает процессы, не применяет firewall-rules
и не управляет systemd/service mode.


## Runtime session inputs

GUI toggle использует тот же session runner, что и CLI. Перед privileged start runner создаёт public runtime-копию hostlist под `/tmp/zap2-runtime-inputs/...` и передаёт `nfqws2` абсолютный путь к этой копии. Это важно, потому что после `dropcaps()` процесс может потерять право проходить приватные родительские директории пользовательского workspace.

Целевое исправление ошибки:

```text
file_open_test: Permission denied
cannot access hostlist file '.../.zap2/runtime/session-inputs/default.hostlist-0.hosts'
```

## v0.3-beta_stage_10: Lua runtime inputs

Однокнопочный GUI toggle использует public runtime copies не только для hostlist, но и для Lua init-файлов. Это нужно для GUI/pkexec запуска: `nfqws2` после `dropcaps()` отказывается выполнять Lua как root и требует читаемые пути к Lua-файлам. Поэтому GUI start больше не передаёт `core/zapret2/lua/zapret-lib.lua` напрямую, а использует `/tmp/zap2-runtime-inputs/.../lua/zapret-lib.lua`.
