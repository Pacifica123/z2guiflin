# Runtime session inputs

Начиная с `v0.3-beta_stage_9` session runner больше не передаёт `nfqws2` ни исходный абсолютный путь к `profiles/hostlists/default.hosts`, ни runtime-копию внутри `.zap2` как основной hostlist path.

Начиная с `v0.3-beta_stage_10` это же правило распространяется на Lua init-файлы: `--lua-init=@core/zapret2/lua/zapret-lib.lua` и `--lua-init=@core/zapret2/lua/zapret-antidpi.lua` переписываются на public runtime copies.

## Почему Stage 8 был недостаточен

В `v0.3-beta_stage_8` hostlist копировался в `.zap2/runtime/session-inputs/` и передавался как относительный путь. Это убрало зависимость от исходного файла профиля, но не решило проблему полностью: вся `.zap2`-директория всё равно лежит под пользовательским workspace, например внутри `/home/<owner>/...`.

`nfqws2` после открытия NFQUEUE и первичной загрузки данных выполняет `dropcaps()` и повторно проверяет доступ к hostlist. После сброса capabilities процесс может остаться `UID=0`, но уже без `CAP_DAC_OVERRIDE`; в таком состоянии он может потерять возможность проходить приватные родительские директории пользовательского home/workspace. Поэтому повторная проверка могла падать так:

```text
Loaded 35 hosts ...
Running as UID=0 GID=0
file_open_test: Permission denied
cannot access hostlist file '.../.zap2/runtime/session-inputs/default.hostlist-0.hosts'
```

## Текущий механизм

Перед запуском создаётся per-plan public runtime copy под tmp-like директорией:

```text
/tmp/zap2-runtime-inputs/default-<plan-hash-prefix>/default.hostlist-0.hosts
/tmp/zap2-runtime-inputs/default-<plan-hash-prefix>/lua/zapret-lib.lua
/tmp/zap2-runtime-inputs/default-<plan-hash-prefix>/lua/zapret-antidpi.lua
```

В args-файл `nfqws2` попадают абсолютные пути к этим public runtime copies:

```text
--lua-init=@/tmp/zap2-runtime-inputs/default-<hash>/lua/zapret-lib.lua
--lua-init=@/tmp/zap2-runtime-inputs/default-<hash>/lua/zapret-antidpi.lua
--hostlist=/tmp/zap2-runtime-inputs/default-<hash>/default.hostlist-0.hosts
```

Права выставляются так, чтобы процесс после `dropcaps()` мог пройти директории и прочитать hostlist:

```text
directories: 0755
hostlist:    0644
lua files:   0644
```

## Что это даёт

1. GUI/pkexec start не зависит от прав исходного hostlist-файла.
2. Lua init не зависит от traversal по `core/zapret2/lua/...` внутри приватного workspace.
3. Повторный `file_open_test` после `dropcaps()` больше не зависит от traversal по `/home/<owner>/...`.
4. Источник `profiles/hostlists/default.hosts` и vendored Lua остаются owner-maintained.
5. Runtime session работает с копиями конкретного confirmed plan.
6. Stop делает best-effort cleanup public runtime copies.

## Ограничения

- hostlist и Lua init-файлы не считаются секретом в текущем single-owner workflow;
- механизм не запускает service mode и не смешивается с bootstrap;
- после изменения hostlist нужно заново подготовить и подтвердить start workflow;
- если start упал до cleanup, public copies могут остаться для диагностики и будут перезаписаны следующим запуском того же plan hash.
